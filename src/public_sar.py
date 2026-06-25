from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .database import initialize_database
from .target_context import normalize_endpoint_group, normalize_target_family


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")
DEFAULT_REPORT_PATH = Path("data/substituents/public_strategy_signal_report.json")


def _float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _signal_id(*parts: object) -> str:
    digest = hashlib.sha1("|".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()[:14].upper()
    return f"PSAR-{digest}"


def _judgment_score(judgment: str | None, confidence: float | None, uncertainty: float | None, delta: float | None) -> float:
    base = {"supported": 82.0, "contradicted": 32.0, "inconclusive": 55.0}.get(str(judgment or ""), 55.0)
    if confidence is not None:
        base = base * 0.78 + float(confidence) * 0.22
    if uncertainty is not None:
        base -= float(uncertainty) * 8.0
    if delta is not None:
        base += max(-8.0, min(8.0, float(delta) * 5.0))
    return round(max(0.0, min(100.0, base)), 2)


def _endpoint_from_standard_type(standard_type: str | None) -> str:
    return normalize_endpoint_group(None, assay_type=standard_type) or "potency"


def _add_signal(groups: dict[tuple[str, str, str, str], dict], row: dict) -> None:
    key = (
        str(row.get("signal_scope") or "operator"),
        str(row.get("signal_key") or row.get("operator") or "unspecified"),
        str(row.get("target_family") or "unspecified"),
        str(row.get("endpoint_group") or "unspecified"),
    )
    item = groups.setdefault(
        key,
        {
            "signal_scope": key[0],
            "signal_key": key[1],
            "target_family": key[2],
            "endpoint_group": key[3],
            "operator": row.get("operator") or "unspecified",
            "support_count": 0,
            "contradiction_count": 0,
            "inconclusive_count": 0,
            "public_evidence_count": 0,
            "scores": [],
            "source_names": set(),
            "example_ids": [],
            "basis_parts": [],
        },
    )
    judgment = str(row.get("judgment") or "inconclusive")
    if judgment == "supported":
        item["support_count"] += 1
    elif judgment == "contradicted":
        item["contradiction_count"] += 1
    else:
        item["inconclusive_count"] += 1
    item["public_evidence_count"] += _int(row.get("evidence_count"), 1)
    if row.get("public_evidence_score") is not None:
        item["scores"].append(float(row["public_evidence_score"]))
    if row.get("source_name"):
        item["source_names"].add(str(row["source_name"]))
    if row.get("example_id") and len(item["example_ids"]) < 10:
        item["example_ids"].append(str(row["example_id"]))
    if row.get("basis") and len(item["basis_parts"]) < 8:
        item["basis_parts"].append(str(row["basis"]))


def _activity_signals(conn: sqlite3.Connection, groups: dict[tuple[str, str, str, str], dict]) -> None:
    try:
        rows = conn.execute("SELECT * FROM transform_activity_summary").fetchall()
    except sqlite3.Error:
        return
    for raw in rows:
        row = dict(raw)
        payload = {}
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except json.JSONDecodeError:
            payload = {}
        families = payload.get("target_family_summaries") or []
        if not families:
            families = [
                {
                    "target_family_normalized": "unspecified",
                    "standard_type": "IC50",
                    "delta_pchembl": row.get("mean_family_delta_pchembl") or row.get("mean_delta_pchembl"),
                    "replicate_count": row.get("replicate_count"),
                    "assay_confidence_score": row.get("assay_confidence_score"),
                    "uncertainty_score": row.get("uncertainty_score"),
                }
            ]
        for family in families:
            target_family = normalize_target_family(
                family.get("target_family_normalized") or family.get("target_family")
            ) or "unspecified"
            endpoint = _endpoint_from_standard_type(family.get("standard_type"))
            score = _judgment_score(
                row.get("rule_activity_judgment"),
                family.get("assay_confidence_score") or row.get("assay_confidence_score"),
                family.get("uncertainty_score") or row.get("uncertainty_score"),
                family.get("delta_pchembl") or row.get("mean_family_delta_pchembl") or row.get("mean_delta_pchembl"),
            )
            base = {
                "operator": "functional_group_replacement",
                "target_family": target_family,
                "endpoint_group": endpoint,
                "judgment": row.get("rule_activity_judgment") or "inconclusive",
                "public_evidence_score": score,
                "evidence_count": family.get("replicate_count") or row.get("replicate_count") or row.get("target_summary_count") or 1,
                "source_name": "ChEMBL transform activity",
                "example_id": row.get("summary_id") or row.get("transform_id"),
                "basis": f"{row.get('replacement_label') or row.get('rule_id')}:{row.get('rule_activity_judgment') or 'inconclusive'}",
            }
            if row.get("rule_id"):
                _add_signal(groups, {**base, "signal_scope": "functional_rule", "signal_key": row.get("rule_id")})
            _add_signal(groups, {**base, "signal_scope": "operator", "signal_key": "functional_group_replacement"})


def _mmp_property_endpoint(row: dict) -> list[tuple[str, str, float, str]]:
    endpoints: list[tuple[str, str, float, str]] = []
    dlogp = _float(row.get("mean_delta_clogp"), 0.0)
    dtpsa = _float(row.get("mean_delta_tpsa"), 0.0)
    dmw = _float(row.get("mean_delta_fragment_mw"), 0.0)
    if dlogp <= -0.35 or dtpsa >= 12.0:
        score = 64.0 + min(18.0, abs(dlogp) * 8.0 + max(dtpsa, 0.0) * 0.25)
        endpoints.append(("solubility", "property_shift_support", score, "supported"))
    elif dlogp >= 0.35 or dtpsa <= -12.0:
        score = 36.0 - min(14.0, abs(dlogp) * 6.0 + abs(min(dtpsa, 0.0)) * 0.2)
        endpoints.append(("solubility", "property_shift_contradiction", score, "contradicted"))
    if dtpsa <= -12.0 and dlogp <= 1.0:
        score = 62.0 + min(16.0, abs(dtpsa) * 0.25)
        endpoints.append(("permeability", "lower_tpsa_shift", score, "supported"))
    elif dtpsa >= 12.0 or dlogp >= 1.0:
        score = 40.0 - min(12.0, max(dtpsa, 0.0) * 0.2 + max(dlogp, 0.0) * 4.0)
        endpoints.append(("permeability", "property_shift_contradiction", score, "contradicted"))
    if dmw <= -10.0 or dlogp <= -0.75:
        score = 60.0 + min(16.0, abs(dmw) * 0.2 + abs(dlogp) * 5.0)
        endpoints.append(("metabolic_stability", "soft_spot_or_lipophilicity_shift", score, "supported"))
    elif dmw >= 10.0 or dlogp >= 0.75:
        score = 38.0 - min(12.0, max(dmw, 0.0) * 0.12 + max(dlogp, 0.0) * 4.0)
        endpoints.append(("metabolic_stability", "lipophilicity_or_size_shift_contradiction", score, "contradicted"))
    return endpoints


def _mmp_signals(conn: sqlite3.Connection, groups: dict[tuple[str, str, str, str], dict]) -> None:
    try:
        rows = conn.execute("SELECT * FROM mmp_transform_evidence").fetchall()
    except sqlite3.Error:
        return
    for raw in rows:
        row = dict(raw)
        source = row.get("variable_from_smiles")
        target = row.get("variable_to_smiles")
        if not source or not target:
            continue
        pair_key = f"{source}->{target}"
        for endpoint, basis_label, score, judgment in _mmp_property_endpoint(row):
            base = {
                "operator": "rgroup_network_replacement",
                "target_family": "unspecified",
                "endpoint_group": endpoint,
                "judgment": judgment,
                "public_evidence_score": round(max(0.0, min(100.0, score)), 2),
                "evidence_count": row.get("example_count") or row.get("pair_count") or 1,
                "source_name": row.get("source_name") or "public MMP",
                "example_id": row.get("transform_id"),
                "basis": basis_label,
            }
            _add_signal(groups, {**base, "signal_scope": "replacement_pair", "signal_key": pair_key})
            _add_signal(groups, {**base, "signal_scope": "operator", "signal_key": "rgroup_network_replacement"})


def _ring_signals(conn: sqlite3.Connection, groups: dict[tuple[str, str, str, str], dict]) -> None:
    try:
        rows = conn.execute("SELECT * FROM ring_replacement").fetchall()
    except sqlite3.Error:
        return
    for raw in rows:
        row = dict(raw)
        evidence_count = _int(row.get("evidence_count"), 0)
        activity_delta = _float(row.get("activity_delta"), 0.0)
        if evidence_count <= 0:
            continue
        score = 58.0 + min(28.0, evidence_count ** 0.5) + max(-14.0, min(10.0, activity_delta * 12.0))
        judgment = "supported" if activity_delta >= -0.2 else "contradicted" if activity_delta <= -0.5 else "inconclusive"
        base = {
            "operator": "ring_network_replacement",
            "target_family": "unspecified",
            "endpoint_group": "potency",
            "judgment": judgment,
            "public_evidence_score": round(max(0.0, min(100.0, score)), 2),
            "evidence_count": evidence_count,
            "source_name": row.get("source_name") or "public ring replacement",
            "example_id": row.get("replacement_id"),
            "basis": "ring_replacement_activity_delta",
        }
        pair_key = f"{row.get('query_canonical_smiles') or row.get('query_smiles')}->{row.get('replacement_canonical_smiles') or row.get('replacement_smiles')}"
        _add_signal(groups, {**base, "signal_scope": "replacement_pair", "signal_key": pair_key})
        _add_signal(groups, {**base, "signal_scope": "operator", "signal_key": "ring_network_replacement"})


def _finalize_signal(item: dict) -> dict:
    scores = item.pop("scores", [])
    source_names = sorted(item.pop("source_names", set()))
    example_ids = item.pop("example_ids", [])
    basis_parts = item.pop("basis_parts", [])
    support = int(item.get("support_count") or 0)
    contradiction = int(item.get("contradiction_count") or 0)
    if scores:
        score = round(sum(scores) / len(scores), 2)
    elif support > contradiction:
        score = 76.0
    elif contradiction > support:
        score = 34.0
    else:
        score = 55.0
    if contradiction and support:
        score -= min(12.0, 3.0 * min(support, contradiction))
    signal = {
        **item,
        "signal_id": _signal_id(
            item.get("signal_scope"),
            item.get("signal_key"),
            item.get("target_family"),
            item.get("endpoint_group"),
        ),
        "public_evidence_score": round(max(0.0, min(100.0, score)), 2),
        "source_names": ";".join(source_names),
        "source_count": len(source_names),
        "example_ids": ";".join(example_ids[:10]),
        "basis": ";".join(dict.fromkeys(basis_parts[:8])),
    }
    return signal


def build_public_strategy_signal_report(*, db_path: str | Path = DEFAULT_DB_PATH) -> dict:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    groups: dict[tuple[str, str, str, str], dict] = {}
    try:
        _activity_signals(conn, groups)
        _mmp_signals(conn, groups)
        _ring_signals(conn, groups)
    finally:
        conn.close()
    signals = [_finalize_signal(item) for item in groups.values()]
    signals.sort(
        key=lambda row: (
            row.get("public_evidence_score") or 0,
            row.get("public_evidence_count") or 0,
            row.get("signal_scope") or "",
        ),
        reverse=True,
    )
    endpoint_counts = defaultdict(int)
    operator_counts = defaultdict(int)
    judgment_counts = defaultdict(int)
    for signal in signals:
        endpoint_counts[str(signal.get("endpoint_group") or "unspecified")] += 1
        operator_counts[str(signal.get("operator") or "unspecified")] += 1
        if int(signal.get("contradiction_count") or 0) > int(signal.get("support_count") or 0):
            judgment_counts["contradicted"] += 1
        elif int(signal.get("support_count") or 0):
            judgment_counts["supported"] += 1
        else:
            judgment_counts["inconclusive"] += 1
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(Path(db_path).resolve()),
        "signal_count": len(signals),
        "endpoint_signal_counts": dict(sorted(endpoint_counts.items())),
        "operator_signal_counts": dict(sorted(operator_counts.items())),
        "judgment_signal_counts": dict(sorted(judgment_counts.items())),
        "contradiction_signal_count": sum(1 for signal in signals if int(signal.get("contradiction_count") or 0)),
        "net_contradicted_signal_count": judgment_counts.get("contradicted", 0),
        "signals": signals,
        "recommended_next_actions": [
            "Use functional_rule signals for ChEMBL-backed transform priors when exact rule IDs match.",
            "Use replacement_pair and operator fallback signals for public MMP and ring-network candidates.",
            "Treat contradiction_count as a first-class review signal before relying on public priors.",
            "Review high-scoring public signals with low project feedback before promoting them into fixed project priors.",
        ],
    }


def write_public_strategy_signal_report(report: dict, output_path: str | Path = DEFAULT_REPORT_PATH) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def public_strategy_signal_lookup(report: dict | None) -> dict[tuple[str, str, str, str], dict]:
    lookup = {}
    for signal in (report or {}).get("signals") or []:
        key = (
            str(signal.get("signal_scope") or "operator"),
            str(signal.get("signal_key") or signal.get("operator") or "unspecified"),
            str(signal.get("target_family") or "unspecified"),
            str(signal.get("endpoint_group") or "unspecified"),
        )
        lookup[key] = signal
    return lookup


def load_public_strategy_signal_report(path: str | Path = DEFAULT_REPORT_PATH) -> dict:
    report_path = Path(path)
    if not report_path.exists():
        return {}
    return json.loads(report_path.read_text(encoding="utf-8"))


def _context_family(target_context: dict | None, row: dict) -> str:
    context = target_context or {}
    return (
        normalize_target_family(context.get("target_family") or context.get("target_family_raw"))
        or normalize_target_family(row.get("evidence_target_family_normalized") or row.get("evidence_target_family"))
        or "unspecified"
    )


def _context_endpoint(target_context: dict | None, row: dict) -> str:
    context = target_context or {}
    return (
        normalize_endpoint_group(
            context.get("endpoint_group") or context.get("endpoint"),
            assay_type=context.get("assay_type") or context.get("standard_type"),
            assay_name=context.get("assay_name"),
        )
        or normalize_endpoint_group(row.get("endpoint_gate_endpoint") or row.get("evidence_endpoint_group"))
        or "unspecified"
    )


def _candidate_signal_keys(row: dict, target_context: dict | None) -> list[tuple[str, str, str, str]]:
    family = _context_family(target_context, row)
    endpoint = _context_endpoint(target_context, row)
    operator = str(row.get("enumeration_type") or "unspecified")
    keys: list[tuple[str, str, str, str]] = []
    if row.get("functional_rule_id"):
        rule_id = str(row["functional_rule_id"])
        keys.extend(
            [
                ("functional_rule", rule_id, family, endpoint),
                ("functional_rule", rule_id, "unspecified", endpoint),
                ("functional_rule", rule_id, family, "unspecified"),
                ("functional_rule", rule_id, "unspecified", "unspecified"),
            ]
        )
    if row.get("replacement_label"):
        pair = str(row["replacement_label"])
        keys.extend(
            [
                ("replacement_pair", pair, family, endpoint),
                ("replacement_pair", pair, "unspecified", endpoint),
                ("replacement_pair", pair, family, "unspecified"),
                ("replacement_pair", pair, "unspecified", "unspecified"),
            ]
        )
    keys.extend(
        [
            ("operator", operator, family, endpoint),
            ("operator", operator, "unspecified", endpoint),
            ("operator", operator, family, "unspecified"),
            ("operator", operator, "unspecified", "unspecified"),
        ]
    )
    return keys


def public_strategy_signal_for_candidate(
    row: dict,
    lookup: dict[tuple[str, str, str, str], dict],
    *,
    target_context: dict | None = None,
) -> dict:
    matched_key = None
    signal = None
    for key in _candidate_signal_keys(row, target_context):
        if key in lookup:
            matched_key = key
            signal = lookup[key]
            break
    if not signal:
        return {
            "public_strategy_signal_score": None,
            "public_strategy_signal_basis": "no_public_strategy_signal",
            "public_strategy_signal_scope": None,
            "public_strategy_signal_count": 0,
            "public_strategy_signal_support_count": 0,
            "public_strategy_signal_contradiction_count": 0,
            "public_strategy_signal_sources": "",
        }
    return {
        "public_strategy_signal_score": signal.get("public_evidence_score"),
        "public_strategy_signal_basis": ":".join(matched_key or ()),
        "public_strategy_signal_scope": signal.get("signal_scope"),
        "public_strategy_signal_id": signal.get("signal_id"),
        "public_strategy_signal_count": signal.get("public_evidence_count"),
        "public_strategy_signal_support_count": signal.get("support_count"),
        "public_strategy_signal_contradiction_count": signal.get("contradiction_count"),
        "public_strategy_signal_sources": signal.get("source_names"),
        "public_strategy_signal_examples": signal.get("example_ids"),
    }


def annotate_public_strategy_signal(
    rows: list[dict],
    *,
    report: dict | None = None,
    report_path: str | Path = DEFAULT_REPORT_PATH,
    db_path: str | Path = DEFAULT_DB_PATH,
    target_context: dict | None = None,
) -> list[dict]:
    if not rows:
        return rows
    if report is None:
        report = load_public_strategy_signal_report(report_path)
    if not report:
        report = build_public_strategy_signal_report(db_path=db_path)
    lookup = public_strategy_signal_lookup(report)
    if not lookup:
        return [
            {
                **row,
                "public_strategy_signal_score": None,
                "public_strategy_signal_basis": "no_public_strategy_report",
                "public_strategy_signal_scope": None,
                "public_strategy_signal_count": 0,
                "public_strategy_signal_support_count": 0,
                "public_strategy_signal_contradiction_count": 0,
                "public_strategy_signal_sources": "",
            }
            for row in rows
        ]
    return [
        {
            **row,
            **public_strategy_signal_for_candidate(row, lookup, target_context=target_context),
        }
        for row in rows
    ]
