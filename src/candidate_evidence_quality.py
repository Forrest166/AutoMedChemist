from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_EVIDENCE_QUALITY_JSON = Path("data/projects/demo/candidate_evidence_quality.json")
DEFAULT_EVIDENCE_QUALITY_CSV = Path("data/projects/demo/candidate_evidence_quality.csv")
DEFAULT_EVIDENCE_QUALITY_MD = Path("docs/candidate_evidence_quality.md")
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


def _by_candidate(report: dict) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for row in report.get("rows") or []:
        candidate_id = str(row.get("candidate_id") or "").strip()
        if candidate_id:
            rows[candidate_id] = dict(row)
    return rows


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


def _contains_contradiction(row: dict) -> bool:
    haystack = " ".join(str(value or "").lower() for value in row.values())
    markers = ["contradiction", "conflict", "cliff", "liability", "risk=", "risk_bucket"]
    return any(marker in haystack for marker in markers)


def _baseline_context_status(row: dict) -> str:
    keys = ["baseline_status", "baseline_movement", "score_delta", "rank_delta", "changed_fields"]
    return "present" if any(str(row.get(key) or "").strip() for key in keys) else "missing"


def _quality_bucket(drawer_row: dict, qa_row: dict, board_row: dict) -> tuple[str, str, str]:
    evidence_depth = _float(drawer_row.get("evidence_depth_score"))
    mmp_count = _int(drawer_row.get("mmp_example_count"))
    sar_count = _int(drawer_row.get("sar_example_count"))
    qa_bucket = str(qa_row.get("qa_bucket") or "").strip()
    risk_bucket = str(drawer_row.get("risk_bucket") or qa_row.get("risk_bucket") or board_row.get("risk_bucket") or "").strip()
    board_status = str(drawer_row.get("board_status") or qa_row.get("board_status") or board_row.get("local_review_status") or "").strip()
    pending_age = _int(qa_row.get("pending_age_days"))
    baseline_status = _baseline_context_status(drawer_row)
    if evidence_depth < 3 or (mmp_count + sar_count) == 0:
        return "thin_mmp_sar_evidence", f"depth={evidence_depth}; mmp={mmp_count}; sar={sar_count}", "Add or inspect MMP/SAR context before relying on this row."
    if risk_bucket and risk_bucket != "clear":
        return "contradiction_heavy_evidence", f"risk_bucket={risk_bucket}", "Resolve or document non-clear risk context before handoff."
    if _contains_contradiction(drawer_row):
        return "contradiction_heavy_evidence", "text marker indicates contradiction/conflict/cliff", "Inspect contradictory evidence in the drawer."
    if qa_bucket and qa_bucket != "clear":
        return "qa_attention_required", f"qa_bucket={qa_bucket}", "Clear the decision QA bucket before discussion handoff."
    if pending_age >= 7 or board_status in {"pending_review", "unreviewed", "needs_follow_up", "blocked"}:
        return "stale_review_row", f"board_status={board_status or '-'}; pending_age_days={pending_age}", "Refresh local review status or assign a reviewer."
    if baseline_status == "missing":
        return "missing_baseline_context", "no baseline movement, score delta, rank delta, or changed fields", "Run baseline compare before pinning or accepting movement."
    return "clear", "evidence, QA, review, and baseline context are aligned", "No evidence-quality action required."


def build_candidate_evidence_quality(*, root: str | Path = ".", project_name: str = "demo") -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    drawer = _read_json(project_dir / "candidate_evidence_drawer.json")
    qa = _read_json(project_dir / "candidate_decision_qa.json")
    board = _read_json(project_dir / "candidate_review_board.json")
    qa_by_id = _by_candidate(qa)
    board_by_id = _by_candidate(board)
    rows = []
    for drawer_row in drawer.get("rows") or []:
        candidate_id = str(drawer_row.get("candidate_id") or "").strip()
        qa_row = qa_by_id.get(candidate_id, {})
        board_row = board_by_id.get(candidate_id, {})
        bucket, reason, next_action = _quality_bucket(drawer_row, qa_row, board_row)
        rows.append(
            {
                "candidate_id": candidate_id,
                "local_decision": drawer_row.get("local_decision", ""),
                "score": drawer_row.get("score", ""),
                "site_class": drawer_row.get("site_class") or qa_row.get("site_class") or board_row.get("site_class", ""),
                "quality_bucket": bucket,
                "quality_reason": reason,
                "evidence_depth_score": drawer_row.get("evidence_depth_score", ""),
                "mmp_example_count": drawer_row.get("mmp_example_count", ""),
                "sar_example_count": drawer_row.get("sar_example_count", ""),
                "risk_bucket": drawer_row.get("risk_bucket") or qa_row.get("risk_bucket") or board_row.get("risk_bucket", ""),
                "qa_bucket": qa_row.get("qa_bucket", ""),
                "pending_age_days": qa_row.get("pending_age_days", ""),
                "baseline_context_status": _baseline_context_status(drawer_row),
                "board_status": drawer_row.get("board_status") or board_row.get("local_review_status", ""),
                "next_action": next_action,
            }
        )
    counts = Counter(str(row.get("quality_bucket") or "") for row in rows)
    attention_count = sum(count for bucket, count in counts.items() if bucket != "clear")
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "missing_evidence_drawer",
        "mode": "candidate_evidence_quality_scorecard",
        "project_name": project_name,
        "row_count": len(rows),
        "attention_count": attention_count,
        "quality_bucket_counts": dict(counts.most_common()),
        "linked_decision_qa_rows": len(qa_by_id),
        "linked_review_board_rows": len(board_by_id),
        "rows": rows,
        "recommended_next_actions": [
            "Review non-clear quality buckets before using a candidate in discussion handoff.",
            "Use this scorecard as a local evidence-governance prompt only.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_candidate_evidence_quality_markdown(report: dict) -> str:
    lines = [
        "# Candidate Evidence Quality",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Attention rows: `{report.get('attention_count')}`",
        "",
        "| ID | Quality | Reason | Depth | QA | Baseline | Next Action |",
        "| --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for row in (report.get("rows") or [])[:120]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("quality_bucket") or ""),
                    str(row.get("quality_reason") or "").replace("|", "/"),
                    str(row.get("evidence_depth_score") or ""),
                    str(row.get("qa_bucket") or ""),
                    str(row.get("baseline_context_status") or ""),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_candidate_evidence_quality(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_EVIDENCE_QUALITY_JSON,
    csv_path: str | Path | None = DEFAULT_EVIDENCE_QUALITY_CSV,
    markdown_path: str | Path | None = DEFAULT_EVIDENCE_QUALITY_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "candidate_id",
        "local_decision",
        "score",
        "site_class",
        "quality_bucket",
        "quality_reason",
        "evidence_depth_score",
        "mmp_example_count",
        "sar_example_count",
        "risk_bucket",
        "qa_bucket",
        "pending_age_days",
        "baseline_context_status",
        "board_status",
        "next_action",
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
        md_file.write_text(render_candidate_evidence_quality_markdown(report), encoding="utf-8")
