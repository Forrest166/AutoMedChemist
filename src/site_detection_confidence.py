from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SITE_DETECTION_CONFIDENCE_JSON = Path("data/projects/demo/site_detection_confidence.json")
DEFAULT_SITE_DETECTION_CONFIDENCE_CSV = Path("data/projects/demo/site_detection_confidence.csv")
DEFAULT_SITE_DETECTION_CONFIDENCE_MD = Path("docs/site_detection_confidence.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]

SITE_CLASS_ALIASES = {
    "methoxy_soft_spot": "methoxy_position",
    "terminal_tail": "alkyl_terminal",
}


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _norm_site(value: object) -> str:
    text = str(value or "").strip()
    return SITE_CLASS_ALIASES.get(text, text)


def _split(value: object) -> list[str]:
    return [part.strip() for part in str(value or "").replace(",", ";").split(";") if part.strip()]


def _score_site_class(site_class: str, rows: list[dict], coverage: dict) -> dict[str, Any]:
    class_rows = [row for row in rows if _norm_site(row.get("target_site_class")) == site_class]
    pass_rows = [row for row in class_rows if row.get("status") == "pass"]
    fail_rows = [row for row in class_rows if row.get("status") != "pass"]
    by_type = Counter(str(row.get("case_type") or "") for row in pass_rows)
    false_positive_rows = [row for row in pass_rows if str(row.get("case_type") or "") == "negative"]
    boundary_rows = [row for row in pass_rows if str(row.get("case_type") or "") == "boundary"]
    tier_counts = Counter(str(row.get("tier") or "unspecified") for row in class_rows)
    coverage_row = coverage.get(site_class, {})
    coverage_ok = str(coverage_row.get("status") or "") == "pass"
    score = 30
    score += min(25, by_type.get("positive", 0) * 25)
    score += min(20, len(false_positive_rows) * 20)
    score += min(20, len(boundary_rows) * 20)
    score += 5 if coverage_ok else -25
    score -= min(30, len(fail_rows) * 15)
    score = max(0, min(100, score))
    status = "high_confidence" if score >= 85 else "review" if score >= 65 else "low_confidence"
    false_positive_tier = "none"
    if false_positive_rows:
        false_positive_tier = ";".join(sorted({str(row.get("tier") or "unspecified") for row in false_positive_rows}))
    return {
        "row_type": "site_class_confidence",
        "key": site_class,
        "target_site_class": site_class,
        "candidate_id": "",
        "status": status,
        "confidence_score": score,
        "rule_hit_count": by_type.get("positive", 0),
        "boundary_protection_count": len(boundary_rows),
        "false_positive_guard_count": len(false_positive_rows),
        "false_positive_tier": false_positive_tier,
        "coverage_status": coverage_row.get("status") or "missing",
        "details": (
            f"positive={by_type.get('positive', 0)}; negative={by_type.get('negative', 0)}; "
            f"boundary={by_type.get('boundary', 0)}; failures={len(fail_rows)}; tiers={dict(tier_counts)}"
        ),
        "next_action": "Use directly for parser confidence." if status == "high_confidence" else "Add more boundary or false-positive cases before relying on this site class.",
        "export_scope": "local_site_detection_confidence",
        "procurement_allowed": False,
        "feedback_import_allowed": False,
    }


def _sample_confidence_rows(samples: list[dict], site_confidence: dict[str, dict]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sample in samples:
        detected = [_norm_site(item) for item in _split(sample.get("detected_site_types"))]
        declared = _norm_site(sample.get("declared_site_class"))
        candidates = detected or ([declared] if declared else [])
        best = max((site_confidence.get(item, {}) for item in candidates), key=lambda item: int(item.get("confidence_score") or 0), default={})
        score = int(best.get("confidence_score") or 0)
        alignment = str(sample.get("site_class_alignment") or "")
        if alignment == "declared_not_detected":
            score = max(0, score - 20)
        elif alignment == "aligned":
            score = min(100, score + 5)
        status = "aligned_high_confidence" if score >= 85 and alignment in {"aligned", "not_declared"} else "review"
        rows.append(
            {
                "row_type": "project_sample_confidence",
                "key": sample.get("sample_id") or sample.get("candidate_id") or "",
                "target_site_class": declared or ";".join(detected),
                "candidate_id": sample.get("candidate_id") or "",
                "status": status,
                "confidence_score": score,
                "rule_hit_count": 1 if detected else 0,
                "boundary_protection_count": best.get("boundary_protection_count", 0),
                "false_positive_guard_count": best.get("false_positive_guard_count", 0),
                "false_positive_tier": best.get("false_positive_tier", ""),
                "coverage_status": best.get("coverage_status", ""),
                "details": f"declared={declared or '-'}; detected={';'.join(detected) or '-'}; alignment={alignment or '-'}",
                "next_action": "Review declared-vs-detected mismatch before using the candidate site class." if alignment == "declared_not_detected" else "Use as local parser grounding only.",
                "export_scope": "local_site_detection_confidence",
                "procurement_allowed": False,
                "feedback_import_allowed": False,
            }
        )
    return rows


def build_site_detection_confidence(*, root: str | Path = ".", project_name: str = "demo") -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    regression = _read_json(project_dir / "site_detection_regression_report.json")
    rows = [dict(row) for row in regression.get("rows") or [] if isinstance(row, dict)]
    coverage_rows = {
        _norm_site(row.get("target_site_class")): dict(row)
        for row in regression.get("coverage_rows") or []
        if isinstance(row, dict)
    }
    site_classes = sorted({_norm_site(row.get("target_site_class")) for row in rows if row.get("target_site_class")})
    site_confidence_rows = [_score_site_class(site_class, rows, coverage_rows) for site_class in site_classes]
    site_confidence = {row["target_site_class"]: row for row in site_confidence_rows}
    sample_rows = _sample_confidence_rows([dict(row) for row in regression.get("project_sample_rows") or []], site_confidence)
    out_rows = site_confidence_rows + sample_rows
    status_counts = Counter(str(row.get("status") or "unknown") for row in out_rows)
    low_count = sum(1 for row in out_rows if int(row.get("confidence_score") or 0) < 65)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if out_rows and regression.get("status") == "pass" else "review_required",
        "mode": "site_detection_confidence",
        "project_name": project_name,
        "row_count": len(out_rows),
        "site_class_count": len(site_confidence_rows),
        "project_sample_count": len(sample_rows),
        "low_confidence_count": low_count,
        "status_counts": dict(status_counts.most_common()),
        "rows": out_rows,
        "recommended_next_actions": [
            "Add regression examples where confidence is below 65 or declared project samples do not align.",
            "Treat this as parser confidence only; it is not experimental feedback and does not trigger execution.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_site_detection_confidence_markdown(report: dict) -> str:
    lines = [
        "# Site Detection Confidence",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows / low confidence: `{report.get('row_count')}` / `{report.get('low_confidence_count')}`",
        "",
        "| Type | Key | Status | Score | Rule Hits | Boundary | False Positive | Details |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("row_type") or ""),
                    str(row.get("key") or ""),
                    str(row.get("status") or ""),
                    str(row.get("confidence_score") or 0),
                    str(row.get("rule_hit_count") or 0),
                    str(row.get("boundary_protection_count") or 0),
                    str(row.get("false_positive_guard_count") or 0),
                    str(row.get("details") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_site_detection_confidence(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_SITE_DETECTION_CONFIDENCE_JSON,
    csv_path: str | Path | None = DEFAULT_SITE_DETECTION_CONFIDENCE_CSV,
    markdown_path: str | Path | None = DEFAULT_SITE_DETECTION_CONFIDENCE_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "row_type",
        "key",
        "target_site_class",
        "candidate_id",
        "status",
        "confidence_score",
        "rule_hit_count",
        "boundary_protection_count",
        "false_positive_guard_count",
        "false_positive_tier",
        "coverage_status",
        "details",
        "next_action",
        "export_scope",
        "procurement_allowed",
        "feedback_import_allowed",
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
        md_file.write_text(render_site_detection_confidence_markdown(report), encoding="utf-8")
