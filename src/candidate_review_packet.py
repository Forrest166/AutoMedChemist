from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REVIEW_PACKET_JSON = Path("data/projects/demo/candidate_review_packet.json")
DEFAULT_REVIEW_PACKET_CSV = Path("data/projects/demo/candidate_review_packet.csv")
DEFAULT_REVIEW_PACKET_MD = Path("docs/candidate_review_packet.md")


def _resolve(root: Path, path: str | Path) -> Path:
    item = Path(path)
    return item if item.is_absolute() else root / item


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _review_bucket(row: dict) -> tuple[str, str]:
    why_review = str(row.get("why_review") or "")
    if _truthy(row.get("site_class_requires_review")) or row.get("site_class_governance_action"):
        return "site_class_governance_review", "site-class policy requires local review"
    if why_review and not why_review.lower().startswith("no immediate"):
        return "evidence_or_risk_review", "candidate explanation flags review"
    if str(row.get("mmp_contradiction_flags") or "").strip():
        return "mmp_contradiction_review", "public MMP contradiction flag present"
    if _float(row.get("risk_score")) < 70:
        return "risk_review", "risk score below review threshold"
    if str(row.get("mmp_precedent_strength") or "").lower() == "high" or str(row.get("sar_neighborhood_strength") or "").lower() == "high":
        return "strong_local_evidence", "high public MMP or local SAR support"
    return "standard_review", "standard local candidate review"


def _review_status(bucket: str) -> str:
    if bucket in {"site_class_governance_review", "evidence_or_risk_review", "mmp_contradiction_review", "risk_review"}:
        return "pending_review"
    if bucket == "strong_local_evidence":
        return "evidence_supported"
    return "informational"


def _applicable_contexts(row: dict) -> str:
    contexts = []
    for field in ["direction", "site_class", "site_type", "site_class_endpoint_groups", "replacement_class"]:
        value = str(row.get(field) or "").strip()
        if value:
            contexts.append(f"{field}={value}")
    return "; ".join(contexts)


def _blocked_contexts(row: dict, bucket: str) -> str:
    blocked = []
    if row.get("site_class_governance_action"):
        blocked.append(f"requires {row.get('site_class_governance_action')}")
    if row.get("mmp_contradiction_flags"):
        blocked.append(f"MMP contradiction: {row.get('mmp_contradiction_flags')}")
    if _float(row.get("risk_score")) < 70:
        blocked.append("low risk_score requires review before prioritization")
    if bucket == "standard_review":
        return ""
    return "; ".join(blocked) or "manual local review required before prioritization"


def _row_payload(row: dict) -> dict[str, Any]:
    bucket, bucket_reason = _review_bucket(row)
    evidence_strength = (
        f"MMP={row.get('mmp_precedent_strength') or '-'}({row.get('mmp_precedent_count') or 0}); "
        f"SAR={row.get('sar_neighborhood_strength') or '-'}({row.get('sar_neighborhood_count') or 0}); "
        f"confidence={row.get('evidence_confidence_bucket') or row.get('evidence_confidence_calibration_score') or '-'}"
    )
    return {
        "candidate_id": row.get("candidate_id"),
        "rank": row.get("rank"),
        "score": row.get("score"),
        "smiles": row.get("smiles"),
        "site_class": row.get("site_class") or row.get("site_type"),
        "direction": row.get("direction"),
        "replacement_label": row.get("replacement_label"),
        "enumeration_type": row.get("enumeration_type"),
        "review_bucket": bucket,
        "review_bucket_reason": bucket_reason,
        "review_status": _review_status(bucket),
        "applicable_contexts": _applicable_contexts(row),
        "blocked_contexts": _blocked_contexts(row, bucket),
        "evidence_strength": evidence_strength,
        "risk_score": row.get("risk_score"),
        "site_class_governance_action": row.get("site_class_governance_action"),
        "mmp_contradiction_flags": row.get("mmp_contradiction_flags"),
        "candidate_explanation_summary": row.get("candidate_explanation_summary"),
        "why_recommended": row.get("why_recommended"),
        "why_review": row.get("why_review"),
        "proposed_review_action": (
            "resolve local governance flag"
            if bucket in {"site_class_governance_review", "mmp_contradiction_review"}
            else "confirm local SAR rationale"
            if bucket == "strong_local_evidence"
            else "review local evidence packet"
        ),
    }


def build_candidate_review_packet(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    candidates_csv: str | Path | None = None,
    max_rows: int = 80,
) -> dict[str, Any]:
    root_path = Path(root)
    csv_path = _resolve(root_path, candidates_csv or Path("data/projects") / project_name / "candidates.csv")
    source_rows = _read_csv_rows(csv_path)
    if not source_rows:
        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "missing_candidates",
            "project_name": project_name,
            "candidates_csv": str(csv_path),
            "row_count": 0,
            "rows": [],
            "summary_rows": [],
            "recommended_next_actions": ["Generate candidates before building a review packet."],
            "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
        }
    sorted_rows = sorted(source_rows, key=lambda row: (_float(row.get("rank"), 10_000), -_float(row.get("score"))))
    packet_rows = [_row_payload(row) for row in sorted_rows[: max(1, int(max_rows))]]
    by_bucket: dict[str, list[dict]] = defaultdict(list)
    by_site: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    for row in packet_rows:
        by_bucket[str(row["review_bucket"])].append(row)
        by_site[str(row.get("site_class") or "unknown")] += 1
        by_status[str(row["review_status"])] += 1
    summary_rows = []
    for bucket, items in sorted(by_bucket.items(), key=lambda item: (-len(item[1]), item[0])):
        summary_rows.append(
            {
                "review_bucket": bucket,
                "row_count": len(items),
                "top_candidate_ids": ";".join(str(row.get("candidate_id") or "") for row in items[:5]),
                "dominant_site_classes": ";".join(site for site, _count in Counter(str(row.get("site_class") or "unknown") for row in items).most_common(4)),
                "max_score": max([_float(row.get("score")) for row in items] or [0.0]),
            }
        )
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "review_ready",
        "mode": "non_experimental_candidate_review_packet",
        "project_name": project_name,
        "candidates_csv": str(csv_path),
        "row_count": len(packet_rows),
        "review_required_count": sum(1 for row in packet_rows if row.get("review_status") == "pending_review"),
        "bucket_counts": dict(Counter(row["review_bucket"] for row in packet_rows).most_common()),
        "site_class_counts": dict(by_site.most_common()),
        "review_status_counts": dict(by_status.most_common()),
        "summary_rows": summary_rows,
        "rows": packet_rows,
        "recommended_next_actions": [
            "Review pending rows by site class, contradiction flag, and local evidence strength.",
            "Use evidence-supported rows as ranked local design candidates after human review.",
            "Keep review actions inside local SAR/profile/governance workflows only.",
        ],
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }


def render_candidate_review_packet_markdown(report: dict) -> str:
    lines = [
        "# Candidate Review Packet",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Project: `{report.get('project_name')}`",
        f"- Rows: `{report.get('row_count')}`",
        f"- Pending review: `{report.get('review_required_count')}`",
        "",
        "## Buckets",
        "",
        "| Bucket | Rows | Top IDs | Dominant Site Classes | Max Score |",
        "| --- | ---: | --- | --- | ---: |",
    ]
    for row in report.get("summary_rows") or []:
        lines.append(
            f"| `{row.get('review_bucket')}` | {row.get('row_count')} | {row.get('top_candidate_ids')} | {row.get('dominant_site_classes')} | {row.get('max_score')} |"
        )
    lines.extend(["", "## Rows", "", "| ID | Score | Site | Review Status | Evidence | Action |", "| --- | ---: | --- | --- | --- | --- |"])
    for row in (report.get("rows") or [])[:40]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("score") or ""),
                    str(row.get("site_class") or ""),
                    str(row.get("review_status") or ""),
                    str(row.get("evidence_strength") or "").replace("|", "/"),
                    str(row.get("proposed_review_action") or ""),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_candidate_review_packet(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_REVIEW_PACKET_JSON,
    csv_path: str | Path | None = DEFAULT_REVIEW_PACKET_CSV,
    markdown_path: str | Path | None = DEFAULT_REVIEW_PACKET_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path:
        fields = [
            "candidate_id",
            "rank",
            "score",
            "smiles",
            "site_class",
            "direction",
            "replacement_label",
            "enumeration_type",
            "review_bucket",
            "review_bucket_reason",
            "review_status",
            "applicable_contexts",
            "blocked_contexts",
            "evidence_strength",
            "risk_score",
            "site_class_governance_action",
            "mmp_contradiction_flags",
            "candidate_explanation_summary",
            "why_recommended",
            "why_review",
            "proposed_review_action",
        ]
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
        md_file.write_text(render_candidate_review_packet_markdown(report), encoding="utf-8")
