from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_JSON = Path("data/projects/demo/site_detection_calibration_queue.json")
DEFAULT_CSV = Path("data/projects/demo/site_detection_calibration_queue.csv")
DEFAULT_MD = Path("docs/site_detection_calibration_queue.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _int(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _required_example_type(row: dict) -> str:
    if str(row.get("row_type") or "") == "project_sample_confidence":
        details = str(row.get("details") or "")
        if "declared_not_detected" in details:
            return "declared_vs_detected_mismatch"
        return "project_sample_boundary"
    if _int(row.get("rule_hit_count")) <= 0:
        return "positive_rule_hit"
    if _int(row.get("boundary_protection_count")) <= 0:
        return "boundary_case"
    if _int(row.get("false_positive_guard_count")) <= 0:
        return "negative_false_positive_guard"
    return "paired_boundary_and_negative"


def _priority(row: dict) -> str:
    score = _int(row.get("confidence_score"))
    details = str(row.get("details") or "")
    if score < 65 or "declared_not_detected" in details:
        return "high"
    if score < 85:
        return "medium"
    return "low"


def _status(row: dict) -> str:
    score = _int(row.get("confidence_score"))
    details = str(row.get("details") or "")
    if "declared_not_detected" in details:
        return "needs_mismatch_review"
    if score < 65:
        return "needs_low_confidence_examples"
    if score < 85:
        return "needs_boundary_examples"
    return "watch"


def build_site_detection_calibration_queue(*, root: str | Path = ".", project_name: str = "demo") -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    confidence = _read_json(project_dir / "site_detection_confidence.json")
    rows: list[dict[str, Any]] = []
    for index, source in enumerate(confidence.get("rows") or [], start=1):
        source = dict(source)
        score = _int(source.get("confidence_score"))
        status = str(source.get("status") or "")
        if status in {"high_confidence", "aligned_high_confidence"} and score >= 85:
            continue
        queue_status = _status(source)
        calibration_id = f"SDCQ-{index:04d}"
        rows.append(
            {
                "calibration_id": calibration_id,
                "row_type": source.get("row_type") or "",
                "key": source.get("key") or "",
                "target_site_class": source.get("target_site_class") or "",
                "candidate_id": source.get("candidate_id") or "",
                "source_status": status,
                "confidence_score": score,
                "calibration_status": queue_status,
                "priority": _priority(source),
                "required_example_type": _required_example_type(source),
                "local_review_status": "open",
                "rule_hit_count": source.get("rule_hit_count") or 0,
                "boundary_protection_count": source.get("boundary_protection_count") or 0,
                "false_positive_guard_count": source.get("false_positive_guard_count") or 0,
                "source_details": source.get("details") or "",
                "suggested_action": (
                    "Add a declared-vs-detected fixture and review parser alignment."
                    if queue_status == "needs_mismatch_review"
                    else "Add positive, boundary, and negative examples until the confidence row reaches high confidence."
                    if queue_status == "needs_low_confidence_examples"
                    else "Add boundary or false-positive fixtures before using this site class without manual review."
                ),
                "production_scoring_write_allowed": False,
                "feedback_import_allowed": False,
                "scope_note": "Local parser calibration only; this does not import real experiment feedback.",
            }
        )

    priority_counts = Counter(str(row.get("priority") or "unknown") for row in rows)
    status_counts = Counter(str(row.get("calibration_status") or "unknown") for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "mode": "site_detection_calibration_queue",
        "project_name": project_name,
        "row_count": len(rows),
        "queue_count": len(rows),
        "low_confidence_count": sum(1 for row in rows if _int(row.get("confidence_score")) < 65),
        "mismatch_review_count": status_counts.get("needs_mismatch_review", 0),
        "site_class_count": len({row.get("target_site_class") for row in rows if row.get("target_site_class")}),
        "project_sample_review_count": sum(1 for row in rows if row.get("row_type") == "project_sample_confidence"),
        "priority_counts": dict(priority_counts.most_common()),
        "calibration_status_counts": dict(status_counts.most_common()),
        "rows": rows,
        "recommended_next_actions": [
            "Use high-priority rows as the manual calibration set for the next site parser iteration.",
            "Keep this queue local and fixture-based; do not treat it as real experimental feedback.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_site_detection_calibration_queue_markdown(report: dict) -> str:
    lines = [
        "# Site Detection Calibration Queue",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Queue rows: `{report.get('queue_count')}`",
        f"- Low confidence: `{report.get('low_confidence_count')}`",
        "",
        "| ID | Type | Key | Site | Score | Priority | Needed Example | Action |",
        "| --- | --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("calibration_id") or ""),
                    str(row.get("row_type") or ""),
                    str(row.get("key") or ""),
                    str(row.get("target_site_class") or ""),
                    str(row.get("confidence_score") or 0),
                    str(row.get("priority") or ""),
                    str(row.get("required_example_type") or ""),
                    str(row.get("suggested_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_site_detection_calibration_queue(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_JSON,
    csv_path: str | Path | None = DEFAULT_CSV,
    markdown_path: str | Path | None = DEFAULT_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "calibration_id",
        "row_type",
        "key",
        "target_site_class",
        "candidate_id",
        "source_status",
        "confidence_score",
        "calibration_status",
        "priority",
        "required_example_type",
        "local_review_status",
        "rule_hit_count",
        "boundary_protection_count",
        "false_positive_guard_count",
        "source_details",
        "suggested_action",
        "production_scoring_write_allowed",
        "feedback_import_allowed",
        "scope_note",
    ]
    if csv_path:
        csv_file = Path(csv_path)
        csv_file.parent.mkdir(parents=True, exist_ok=True)
        with csv_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in report.get("rows") or []:
                writer.writerow({field: row.get(field, "") for field in fields})
    if markdown_path:
        md_file = Path(markdown_path)
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(render_site_detection_calibration_queue_markdown(report), encoding="utf-8")
