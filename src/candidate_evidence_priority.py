from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_CANDIDATE_EVIDENCE_PRIORITY_PATH = Path("data/projects/demo/candidate_evidence_priority_report.json")
DEFAULT_CANDIDATE_EVIDENCE_PRIORITY_CSV_PATH = Path("data/projects/demo/candidate_evidence_priority_report.csv")


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


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
        rows = payload.get(key)
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def _row_key(*parts: object) -> str:
    basis = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:14].upper()


def _identity_keys(row: dict) -> set[str]:
    keys = set()
    for field in ["queue_id", "candidate_id", "smiles", "candidate_key"]:
        value = str(row.get(field) or "").strip()
        if value:
            keys.add(f"{field}:{value}")
    return keys


def _candidate_key(row: dict) -> str:
    return (
        str(row.get("queue_id") or "").strip()
        or str(row.get("candidate_id") or "").strip()
        or str(row.get("candidate_key") or "").strip()
        or str(row.get("smiles") or "").strip()
        or _row_key(row.get("replacement_label"), row.get("enumeration_type"))
    )


def _find_existing_row_key(rows_by_key: dict[str, dict], material: dict) -> str | None:
    material_candidate_ids = {
        str(material.get("candidate_candidate_id") or "").strip(),
        str(material.get("base_candidate_id") or "").strip(),
    } - {""}
    material_smiles = str(material.get("candidate_key") or "").strip()
    for key, row in rows_by_key.items():
        if str(row.get("candidate_id") or "").strip() in material_candidate_ids:
            return key
        if material_smiles and str(row.get("smiles") or "").strip() == material_smiles:
            return key
    return None


def _build_public_sar_links(report: dict) -> dict[str, list[dict]]:
    links: dict[str, list[dict]] = defaultdict(list)
    for validation in report.get("rows") or []:
        base = {
            "task_id": validation.get("task_id"),
            "source_signal_id": validation.get("source_signal_id"),
            "signal_key": validation.get("signal_key"),
            "validation_status": validation.get("validation_status"),
            "evidence_link_status": validation.get("evidence_link_status"),
            "public_evidence_score": validation.get("public_evidence_score"),
            "public_evidence_count": validation.get("public_evidence_count"),
            "support_count": validation.get("support_count"),
            "contradiction_count": validation.get("contradiction_count"),
            "endpoint_group": validation.get("endpoint_group"),
            "target_family": validation.get("target_family"),
        }
        for link in validation.get("candidate_links") or []:
            item = {**base, **dict(link)}
            for key in _identity_keys(item):
                links[key].append(item)
    return links


def _build_material_links(report: dict) -> dict[str, list[dict]]:
    links: dict[str, list[dict]] = defaultdict(list)
    for row in report.get("candidate_diff_rows") or []:
        item = dict(row)
        item["material_change_review_status"] = report.get("status")
        for key in _identity_keys(item):
            links[key].append(item)
        for field in ["base_candidate_id", "candidate_candidate_id"]:
            value = str(item.get(field) or "").strip()
            if value:
                links[f"candidate_id:{value}"].append(item)
    return links


def _best_series(row: dict, series_lookup: dict[str, dict]) -> dict:
    key = str(row.get("analog_series_key") or row.get("series_key") or "").strip()
    if key and key in series_lookup:
        return series_lookup[key]
    return {}


def _unique_by(items: list[dict], field: str) -> list[dict]:
    seen = set()
    result = []
    for item in items:
        key = str(item.get(field) or json.dumps(item, sort_keys=True, default=str))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _merge_links(row: dict, link_lookup: dict[str, list[dict]]) -> list[dict]:
    links = []
    for key in _identity_keys(row):
        links.extend(link_lookup.get(key) or [])
    return links


def _priority_tier(score: float) -> str:
    if score >= 28:
        return "high"
    if score >= 16:
        return "medium"
    return "watch"


def build_candidate_evidence_priority_report(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    queue_path: str | Path | None = None,
    public_sar_validation_path: str | Path = "data/projects/demo/public_sar_validation_report.json",
    material_review_path: str | Path = "data/projects/demo/profile_ab_material_change_review.json",
    analog_series_path: str | Path = "data/projects/demo/analog_series_report.json",
) -> dict:
    root_path = Path(root)
    resolved_queue_path = Path(queue_path) if queue_path else _latest_next_design_queue_path(root_path, project_name)
    if resolved_queue_path and not resolved_queue_path.is_absolute():
        resolved_queue_path = root_path / resolved_queue_path
    sar_path = Path(public_sar_validation_path)
    material_path = Path(material_review_path)
    analog_path = Path(analog_series_path)
    sar_report = _read_json(sar_path if sar_path.is_absolute() else root_path / sar_path)
    material_review = _read_json(material_path if material_path.is_absolute() else root_path / material_path)
    analog_report = _read_json(analog_path if analog_path.is_absolute() else root_path / analog_path)
    queue = _queue_rows(_read_json(resolved_queue_path)) if resolved_queue_path else []
    sar_links = _build_public_sar_links(sar_report)
    material_links = _build_material_links(material_review)
    series_lookup = {str(row.get("series_key") or ""): dict(row) for row in analog_report.get("series") or []}

    rows_by_key: dict[str, dict] = {}
    for queue_row in queue:
        key = _candidate_key(queue_row)
        rows_by_key[key] = {
            "row_source": "next_design_queue",
            "queue_id": queue_row.get("queue_id"),
            "queue_rank": queue_row.get("queue_rank"),
            "queue_priority_score": queue_row.get("queue_priority_score"),
            "candidate_id": queue_row.get("candidate_id"),
            "candidate_key": queue_row.get("smiles"),
            "smiles": queue_row.get("smiles"),
            "endpoint_group": queue_row.get("endpoint_group"),
            "enumeration_type": queue_row.get("enumeration_type"),
            "replacement_label": queue_row.get("replacement_label"),
            "analog_series_key": queue_row.get("analog_series_key"),
            "queue_decision": queue_row.get("queue_decision"),
            "recommendation_action": queue_row.get("recommendation_action"),
        }
    for material in material_review.get("candidate_diff_rows") or []:
        if _find_existing_row_key(rows_by_key, material):
            continue
        key = str(material.get("candidate_candidate_id") or material.get("base_candidate_id") or material.get("candidate_key") or "")
        if key and key not in rows_by_key:
            rows_by_key[key] = {
                "row_source": "material_ab_review",
                "queue_id": "",
                "queue_rank": "",
                "queue_priority_score": 0,
                "candidate_id": material.get("candidate_candidate_id") or material.get("base_candidate_id"),
                "candidate_key": material.get("candidate_key"),
                "smiles": material.get("candidate_key"),
                "endpoint_group": "",
                "enumeration_type": material.get("enumeration_type"),
                "replacement_label": material.get("replacement_label"),
                "analog_series_key": "",
                "queue_decision": "",
                "recommendation_action": "review_material_profile_ab_change",
            }

    rows = []
    for row in rows_by_key.values():
        sar_items = _unique_by(_merge_links(row, sar_links), "task_id")
        material_items = _unique_by(_merge_links(row, material_links), "candidate_key")
        series = _best_series(row, series_lookup)
        sar_scores = [_float(item.get("public_evidence_score")) for item in sar_items if item.get("public_evidence_score") not in {None, ""}]
        contradiction_count = sum(_int(item.get("contradiction_count")) for item in sar_items)
        support_count = sum(_int(item.get("support_count")) for item in sar_items)
        material_abs_delta = max((abs(_float(item.get("score_delta"))) for item in material_items), default=0.0)
        material_abs_rank_delta = max((abs(_int(item.get("rank_delta"))) for item in material_items), default=0)
        sufficiency_score = _float(series.get("evidence_sufficiency_score"), 0.0) if series else None
        sufficiency_gap = _float(series.get("evidence_sufficiency_gap"), 0.0) if series else 0.0
        score = _float(row.get("queue_priority_score"))
        score += min(9.0, len(sar_items) * 1.5)
        if sar_scores:
            score += min(8.0, max(sar_scores) / 14.0)
        score += min(10.0, material_abs_delta + material_abs_rank_delta * 0.25)
        score += min(8.0, sufficiency_gap / 12.5)
        if contradiction_count:
            score += min(8.0, contradiction_count * 2.0)
        score = round(score, 2)
        evidence_flags = []
        if sar_items:
            evidence_flags.append("public_sar_linked")
        if material_items:
            evidence_flags.append("material_ab_linked")
        if series:
            evidence_flags.append(str(series.get("evidence_sufficiency_status") or "series_linked"))
        if contradiction_count:
            evidence_flags.append("public_sar_contradiction")
        rows.append(
            {
                **row,
                "public_sar_link_count": len(sar_items),
                "public_sar_max_score": round(max(sar_scores), 2) if sar_scores else None,
                "public_sar_support_count": support_count,
                "public_sar_contradiction_count": contradiction_count,
                "public_sar_signal_examples": "; ".join(
                    dict.fromkeys(str(item.get("source_signal_id") or item.get("signal_key") or "") for item in sar_items if item)
                ),
                "material_ab_diff_count": len(material_items),
                "material_ab_max_abs_score_delta": round(material_abs_delta, 4),
                "material_ab_max_abs_rank_delta": material_abs_rank_delta,
                "material_ab_memberships": ";".join(sorted({str(item.get("membership") or "") for item in material_items if item.get("membership")})),
                "evidence_sufficiency_score": sufficiency_score,
                "evidence_sufficiency_status": series.get("evidence_sufficiency_status") if series else "",
                "next_evidence_action": series.get("next_evidence_action") if series else "",
                "candidate_evidence_priority_score": score,
                "candidate_evidence_priority_tier": _priority_tier(score),
                "evidence_flags": ";".join(evidence_flags),
            }
        )
    rows.sort(
        key=lambda row: (
            {"high": 0, "medium": 1, "watch": 2}.get(str(row.get("candidate_evidence_priority_tier")), 9),
            -_float(row.get("candidate_evidence_priority_score")),
            _int(row.get("queue_rank"), 9999),
            str(row.get("candidate_id") or ""),
        )
    )
    tier_counts = Counter(str(row.get("candidate_evidence_priority_tier") or "unknown") for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "project_name": project_name,
        "queue_path": str(resolved_queue_path) if resolved_queue_path else None,
        "row_count": len(rows),
        "high_priority_count": tier_counts.get("high", 0),
        "medium_priority_count": tier_counts.get("medium", 0),
        "sar_linked_count": sum(1 for row in rows if row.get("public_sar_link_count")),
        "material_diff_linked_count": sum(1 for row in rows if row.get("material_ab_diff_count")),
        "sufficiency_gap_count": sum(1 for row in rows if str(row.get("evidence_sufficiency_status") or "").startswith("needs")),
        "contradiction_linked_count": sum(1 for row in rows if row.get("public_sar_contradiction_count")),
        "priority_tier_counts": dict(tier_counts.most_common()),
        "rows": rows,
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "recommended_next_actions": [
            "Review high-priority candidates where public SAR, material A/B movement, or sufficiency gaps overlap.",
            "Use sufficiency-driven actions to choose the next measured endpoint before expanding a series.",
            "Do not mix vendor/procurement availability into this evidence priority view.",
        ],
    }


def write_candidate_evidence_priority_report(
    report: dict,
    output_path: str | Path = DEFAULT_CANDIDATE_EVIDENCE_PRIORITY_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_CANDIDATE_EVIDENCE_PRIORITY_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    rows = [dict(row) for row in report.get("rows") or []]
    fieldnames = [
        "candidate_evidence_priority_tier",
        "candidate_evidence_priority_score",
        "row_source",
        "queue_id",
        "queue_rank",
        "queue_priority_score",
        "candidate_id",
        "smiles",
        "endpoint_group",
        "enumeration_type",
        "replacement_label",
        "analog_series_key",
        "public_sar_link_count",
        "public_sar_max_score",
        "public_sar_support_count",
        "public_sar_contradiction_count",
        "material_ab_diff_count",
        "material_ab_max_abs_score_delta",
        "material_ab_max_abs_rank_delta",
        "material_ab_memberships",
        "evidence_sufficiency_score",
        "evidence_sufficiency_status",
        "next_evidence_action",
        "evidence_flags",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
