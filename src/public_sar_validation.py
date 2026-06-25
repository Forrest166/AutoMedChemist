from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .project_evidence_expansion_plan import DEFAULT_PROJECT_EVIDENCE_EXPANSION_PLAN_PATH, load_project_evidence_expansion_plan


DEFAULT_PUBLIC_SAR_VALIDATION_REPORT_PATH = Path("data/projects/demo/public_sar_validation_report.json")
DEFAULT_PUBLIC_SAR_VALIDATION_CSV_PATH = Path("data/projects/demo/public_sar_validation_report.csv")


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _norm(value: object) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _endpoint_matches(signal_endpoint: object, active_endpoints: set[str]) -> bool:
    endpoint = _norm(signal_endpoint)
    if not endpoint or endpoint in {"all", "unspecified"}:
        return True
    return endpoint in active_endpoints or any(endpoint in item or item in endpoint for item in active_endpoints)


def _family_matches(signal_family: object, active_families: set[str]) -> bool:
    family = _norm(signal_family)
    return not family or family in {"all", "unspecified"} or family in active_families


def _score(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _signal_lookup(pack: dict) -> dict[str, dict]:
    lookup = {}
    for signal in pack.get("top_public_signals") or []:
        if signal.get("signal_id"):
            lookup[str(signal.get("signal_id"))] = dict(signal)
        if signal.get("signal_key"):
            lookup[str(signal.get("signal_key"))] = dict(signal)
    return lookup


def _latest_next_design_queue_path(root_path: Path, project_name: str | None) -> Path | None:
    queue_dir = root_path / "data/projects/closed_loop"
    candidates = []
    if project_name:
        candidates.append(queue_dir / f"next_design_queue_{project_name}.json")
    candidates.extend(path for path in queue_dir.glob("next_design_queue*.json") if "decision" not in path.stem)
    existing = [path for path in candidates if path.exists() and path.is_file()]
    return max(existing, key=lambda path: path.stat().st_mtime) if existing else None


def _queue_rows(payload: dict) -> list[dict]:
    for key in ["queue", "queue_rows", "rows", "top_rows"]:
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(row) for row in value if isinstance(row, dict)]
    return []


def _candidate_id(row: dict) -> str:
    return str(row.get("queue_id") or row.get("candidate_id") or row.get("smiles") or "")


def _tokens(value: object) -> set[str]:
    raw = _norm(value)
    if not raw:
        return set()
    pieces = {raw}
    for sep in ["->", "|", ":", ";", ",", "+", "-", "_"]:
        split = [part for part in raw.split(sep) if part]
        if len(split) > 1:
            pieces.update(split)
    return {piece for piece in pieces if len(piece) >= 3}


def _operator_matches(signal_operator: object, row_enumeration: object) -> bool:
    operator = _norm(signal_operator)
    enumeration = _norm(row_enumeration)
    if not operator or not enumeration:
        return False
    if operator == enumeration:
        return True
    aliases = {
        "ring_network_replacement": {"scaffold_replacement", "ring_rgroup_joint_recommendation"},
        "rgroup_network_replacement": {"substituent_scan", "ring_rgroup_joint_recommendation"},
        "functional_group_replacement": {"functional_group_replacement"},
    }
    return any(alias == enumeration or alias in enumeration for alias in aliases.get(operator, set()))


def _row_endpoint_matches(signal_endpoint: object, row: dict) -> bool:
    endpoints = {
        _norm(row.get("endpoint_group")),
        _norm(row.get("analog_series_primary_endpoint")),
        _norm(row.get("evidence_endpoint_group")),
    }
    return _endpoint_matches(signal_endpoint, {item for item in endpoints if item})


def _candidate_link_rows(signal: dict, queue_rows: list[dict], *, limit: int = 6) -> list[dict]:
    signal_id = str(signal.get("source_signal_id") or signal.get("signal_id") or "")
    signal_key = str(signal.get("signal_key") or "")
    signal_operator = signal.get("operator")
    signal_tokens = _tokens(signal_key) | _tokens(signal.get("basis"))
    matches = []
    for row in queue_rows:
        basis_parts = []
        row_tokens = set()
        for key in [
            "public_strategy_signal_id",
            "public_strategy_signal_basis",
            "functional_rule_id",
            "replacement_label",
            "analog_series_key",
            "queue_analog_series_delta_key",
            "enumeration_type",
        ]:
            row_tokens.update(_tokens(row.get(key)))
        if signal_id and signal_id == str(row.get("public_strategy_signal_id") or ""):
            basis_parts.append("exact_public_signal_id")
        if signal_key and (
            signal_key == str(row.get("functional_rule_id") or "")
            or signal_key == str(row.get("replacement_label") or "")
            or _norm(signal_key) in _norm(row.get("public_strategy_signal_basis"))
        ):
            basis_parts.append("exact_signal_key")
        if signal_tokens and row_tokens and signal_tokens.intersection(row_tokens):
            basis_parts.append("shared_signal_tokens")
        if _operator_matches(signal_operator, row.get("enumeration_type")):
            basis_parts.append("operator_match")
        if _row_endpoint_matches(signal.get("endpoint_group"), row):
            basis_parts.append("endpoint_match")
        strong = {"exact_public_signal_id", "exact_signal_key", "shared_signal_tokens"}
        if strong.intersection(basis_parts) or {"operator_match", "endpoint_match"}.issubset(set(basis_parts)):
            matches.append(
                {
                    "queue_id": row.get("queue_id"),
                    "candidate_id": row.get("candidate_id"),
                    "smiles": row.get("smiles"),
                    "endpoint_group": row.get("endpoint_group"),
                    "enumeration_type": row.get("enumeration_type"),
                    "replacement_label": row.get("replacement_label"),
                    "analog_series_key": row.get("analog_series_key"),
                    "queue_rank": row.get("queue_rank"),
                    "queue_priority_score": row.get("queue_priority_score"),
                    "link_basis": ";".join(dict.fromkeys(basis_parts)),
                }
            )
    matches.sort(key=lambda row: (_int_like(row.get("queue_rank"), 9999), str(row.get("queue_id") or "")))
    return matches[:limit]


def _int_like(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _analog_link_rows(signal: dict, analog_rows: list[dict], *, limit: int = 6) -> list[dict]:
    signal_tokens = _tokens(signal.get("signal_key")) | _tokens(signal.get("basis"))
    matches = []
    for row in analog_rows:
        series_key = str(row.get("series_key") or "")
        row_tokens = _tokens(series_key) | _tokens(row.get("recommendation")) | _tokens(row.get("series_delta_action"))
        basis_parts = []
        if signal_tokens and row_tokens and signal_tokens.intersection(row_tokens):
            basis_parts.append("shared_signal_tokens")
        if _operator_matches(signal.get("operator"), series_key):
            basis_parts.append("operator_series_match")
        if _endpoint_matches(signal.get("endpoint_group"), {_norm(row.get("endpoint_group"))} if row.get("endpoint_group") else set()):
            basis_parts.append("endpoint_match")
        if _family_matches(signal.get("target_family"), {_norm(row.get("target_family"))} if row.get("target_family") else set()):
            basis_parts.append("family_match")
        if basis_parts and ("shared_signal_tokens" in basis_parts or "operator_series_match" in basis_parts):
            matches.append(
                {
                    "series_key": row.get("series_key"),
                    "candidate_count": row.get("candidate_count"),
                    "endpoint_group": row.get("endpoint_group"),
                    "target_family": row.get("target_family"),
                    "recommendation": row.get("recommendation"),
                    "link_basis": ";".join(dict.fromkeys(basis_parts)),
                }
            )
    matches.sort(key=lambda row: _int_like(row.get("candidate_count"), 0), reverse=True)
    return matches[:limit]


def _examples(rows: list[dict], keys: list[str], *, limit: int = 3) -> str:
    values = []
    for row in rows[:limit]:
        label = "/".join(str(row.get(key) or "") for key in keys if row.get(key))
        if label:
            values.append(label)
    return "; ".join(values)


def build_public_sar_validation_report(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    plan_path: str | Path = DEFAULT_PROJECT_EVIDENCE_EXPANSION_PLAN_PATH,
    max_reference_rows: int = 40,
) -> dict:
    root_path = Path(root)
    pack = _read_json(root_path / "data/projects/demo/project_evidence_pack.json")
    plan_file = root_path / plan_path if not Path(plan_path).is_absolute() else Path(plan_path)
    plan = load_project_evidence_expansion_plan(plan_file)
    active_endpoints = {_norm(row.get("endpoint_group")) for row in pack.get("context_summary") or [] if row.get("endpoint_group")}
    active_endpoints.update(_norm(row.get("endpoint_group")) for row in pack.get("endpoint_family_residual_rows") or [] if row.get("endpoint_group"))
    active_families = {_norm(row.get("target_family")) for row in pack.get("context_summary") or [] if row.get("target_family")}
    active_families.update(_norm(row.get("target_family")) for row in pack.get("endpoint_family_residual_rows") or [] if row.get("target_family"))
    signal_lookup = _signal_lookup(pack)
    queue_path = _latest_next_design_queue_path(root_path, project_name)
    queue_payload = _read_json(queue_path) if queue_path else {}
    queue = _queue_rows(queue_payload)
    analog_rows = [dict(row) for row in pack.get("analog_series_rows") or [] if isinstance(row, dict)]
    tasks = [row for row in plan.get("tasks") or [] if row.get("task_type") == "public_sar_validation"]
    if not tasks:
        tasks = [
            {
                "task_id": f"PUBLIC-SAR-{index:03d}",
                "source_signal_id": signal.get("signal_id"),
                "signal_key": signal.get("signal_key"),
                "endpoint_group": signal.get("endpoint_group"),
                "target_family": signal.get("target_family"),
                "public_evidence_score": signal.get("public_evidence_score"),
                "public_evidence_count": signal.get("public_evidence_count"),
                "evidence_source": signal.get("source_names"),
            }
            for index, signal in enumerate((pack.get("top_public_signals") or [])[:max_reference_rows], start=1)
        ]
    rows = []
    for task in tasks[:max_reference_rows]:
        signal = signal_lookup.get(str(task.get("source_signal_id") or "")) or signal_lookup.get(str(task.get("signal_key") or ""))
        merged = {**(signal or {}), **dict(task)}
        endpoint_match = _endpoint_matches(merged.get("endpoint_group"), active_endpoints)
        family_match = _family_matches(merged.get("target_family"), active_families)
        active_match = bool(endpoint_match and family_match)
        score = _score(merged.get("public_evidence_score"))
        evidence_count = int(float(merged.get("public_evidence_count") or 0))
        contradiction_count = int(float(merged.get("contradiction_count") or 0))
        support_count = int(float(merged.get("support_count") or 0))
        candidate_links = _candidate_link_rows(merged, queue)
        analog_links = _analog_link_rows(merged, analog_rows)
        candidate_link_count = len(candidate_links)
        analog_series_link_count = len(analog_links)
        transform_link_count = sum(
            1
            for row in candidate_links
            if str(row.get("enumeration_type") or "") in {"functional_group_replacement", "substituent_scan", "scaffold_replacement"}
        )
        if candidate_link_count:
            evidence_link_status = "candidate_linked"
        elif analog_series_link_count:
            evidence_link_status = "analog_series_linked"
        elif active_match:
            evidence_link_status = "context_only"
        else:
            evidence_link_status = "reference_only"
        if active_match and score >= 70 and evidence_count:
            validation_status = "mapped_to_active_project_context"
            recommendation = "close_as_project_context_mapped_evidence"
        elif score >= 70 and evidence_count:
            validation_status = "reference_only_out_of_scope"
            recommendation = "close_as_reference_only_evidence"
        else:
            validation_status = "needs_manual_sar_review"
            recommendation = "review_before_using_as_project_prior"
        rows.append(
            {
                "task_id": task.get("task_id"),
                "source_signal_id": merged.get("source_signal_id") or merged.get("signal_id"),
                "signal_key": merged.get("signal_key"),
                "validation_status": validation_status,
                "execution_recommendation": recommendation,
                "active_context_match": active_match,
                "endpoint_match": endpoint_match,
                "family_match": family_match,
                "endpoint_group": merged.get("endpoint_group"),
                "target_family": merged.get("target_family"),
                "source_names": merged.get("source_names") or merged.get("evidence_source"),
                "public_evidence_score": score,
                "public_evidence_count": evidence_count,
                "support_count": support_count,
                "contradiction_count": contradiction_count,
                "basis": merged.get("basis"),
                "operator": merged.get("operator"),
                "evidence_link_status": evidence_link_status,
                "candidate_link_count": candidate_link_count,
                "transform_link_count": transform_link_count,
                "analog_series_link_count": analog_series_link_count,
                "candidate_examples": _examples(candidate_links, ["queue_id", "candidate_id", "replacement_label"]),
                "analog_series_examples": _examples(analog_links, ["series_key"]),
                "candidate_links": candidate_links,
                "analog_series_links": analog_links,
            }
        )
    status_counts = Counter(row["validation_status"] for row in rows)
    link_status_counts = Counter(row["evidence_link_status"] for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "project_name": project_name,
        "queue_path": str(queue_path) if queue_path else None,
        "queue_row_count": len(queue),
        "analog_series_row_count": len(analog_rows),
        "row_count": len(rows),
        "active_context_match_count": sum(1 for row in rows if row.get("active_context_match")),
        "candidate_linked_count": sum(1 for row in rows if row.get("candidate_link_count")),
        "analog_series_linked_count": sum(1 for row in rows if row.get("analog_series_link_count")),
        "contradiction_linked_count": sum(1 for row in rows if int(row.get("contradiction_count") or 0)),
        "reference_only_count": status_counts.get("reference_only_out_of_scope", 0),
        "manual_review_count": status_counts.get("needs_manual_sar_review", 0),
        "validation_status_counts": dict(status_counts.most_common()),
        "evidence_link_status_counts": dict(link_status_counts.most_common()),
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "rows": rows,
        "recommended_next_actions": [
            "Close mapped public SAR tasks as evidence mapping, not as measured project outcomes.",
            "Prefer candidate-linked and analog-series-linked signals when choosing next manual SAR review targets.",
            "Keep out-of-scope public signals as reference-only priors until project overlap exists.",
            "Do not use procurement/vendor data for this validation workflow.",
        ],
    }


def write_public_sar_validation_report(
    report: dict,
    output_path: str | Path = DEFAULT_PUBLIC_SAR_VALIDATION_REPORT_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_PUBLIC_SAR_VALIDATION_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    rows = [dict(row) for row in report.get("rows") or []]
    fieldnames = [
        "task_id",
        "source_signal_id",
        "signal_key",
        "validation_status",
        "execution_recommendation",
        "active_context_match",
        "endpoint_match",
        "family_match",
        "endpoint_group",
        "target_family",
        "source_names",
        "public_evidence_score",
        "public_evidence_count",
        "support_count",
        "contradiction_count",
        "basis",
        "operator",
        "evidence_link_status",
        "candidate_link_count",
        "transform_link_count",
        "analog_series_link_count",
        "candidate_examples",
        "analog_series_examples",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
