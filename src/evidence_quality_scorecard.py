from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_EVIDENCE_QUALITY_JSON = Path("data/projects/demo/evidence_quality_scorecard.json")
DEFAULT_EVIDENCE_QUALITY_CSV = Path("data/projects/demo/evidence_quality_scorecard.csv")
DEFAULT_EVIDENCE_QUALITY_MD = Path("docs/evidence_quality_scorecard.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]
PENDING_STATUSES = {"", "pending_review", "unreviewed", "needs_follow_up", "blocked", "deferred"}


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


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


def _parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_days(value: object, now: datetime) -> int:
    stamp = _parse_time(value)
    if stamp is None:
        return 0
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return max(0, int((now - stamp).total_seconds() // 86400))


def _flag_text(flags: list[str]) -> str:
    return ";".join(flag for flag in flags if flag)


def _next_action(row: dict) -> str:
    flags = set(str(row.get("quality_flags") or "").split(";"))
    if "contradiction_heavy_evidence" in flags:
        return "Resolve contradiction or keep candidate in watch/defer before local priority movement."
    if "stale_review_row" in flags:
        return "Refresh the local review row and reviewer note before using the decision packet."
    if "thin_mmp_sar_evidence" in flags:
        return "Keep the candidate reviewable and avoid treating thin MMP/SAR support as confirmed evidence."
    if "missing_baseline_context" in flags:
        return "Rebuild candidate baseline compare before pinning or exporting local decisions."
    return "Evidence quality is clear for local review context."


def build_evidence_quality_scorecard(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    stale_days: int = 7,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    drawer = _read_json(project_dir / "candidate_evidence_drawer.json")
    board = _read_json(project_dir / "candidate_review_board.json")
    qa = _read_json(project_dir / "candidate_decision_qa.json")
    baseline = _read_json(project_dir / "candidate_baseline_compare.json")
    candidates = _read_csv_rows(project_dir / "candidates.csv")
    source_rows = list(drawer.get("rows") or []) or candidates
    board_by_id = _by_candidate(board)
    qa_by_id = _by_candidate(qa)
    baseline_by_id = _by_candidate(baseline)
    now = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    for source in source_rows:
        candidate_id = str(source.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        board_row = board_by_id.get(candidate_id, {})
        qa_row = qa_by_id.get(candidate_id, {})
        baseline_row = baseline_by_id.get(candidate_id, {})
        evidence_depth = _float(source.get("evidence_depth_score"), 0.0)
        mmp_count = _float(source.get("mmp_example_count"), 0.0)
        sar_count = _float(source.get("sar_example_count"), 0.0)
        review_status = str(
            board_row.get("local_review_status")
            or source.get("board_status")
            or source.get("review_status")
            or ""
        ).strip()
        risk_bucket = str(source.get("risk_bucket") or board_row.get("risk_bucket") or qa_row.get("risk_bucket") or "").strip()
        review_bucket = str(source.get("review_bucket") or board_row.get("review_bucket") or "").strip()
        qa_bucket = str(qa_row.get("qa_bucket") or "").strip()
        searchable = " ".join(
            [
                risk_bucket,
                review_bucket,
                qa_bucket,
                str(source.get("evidence_context_summary") or ""),
                str(source.get("drawer_summary") or ""),
                str(source.get("decision_rationale") or ""),
            ]
        ).lower()
        thin = evidence_depth < 3 or mmp_count <= 0 or sar_count <= 0 or (mmp_count + sar_count) < 2
        contradiction = (
            bool(risk_bucket and risk_bucket not in {"clear", "unknown"})
            or "contradiction" in searchable
            or "conflict" in searchable
            or "risk_review" in searchable
        )
        age = _age_days(board_row.get("reviewed_at") or board_row.get("created_at") or board.get("created_at"), now)
        stale = review_status in PENDING_STATUSES and age >= int(stale_days)
        baseline_status = str(baseline_row.get("status") or source.get("baseline_status") or "").strip()
        missing_baseline = not baseline_status or baseline.get("status") in {"missing_baseline", ""}
        qa_attention = bool(qa_bucket and qa_bucket != "clear")
        penalties = (
            (30 if thin else 0)
            + (25 if contradiction else 0)
            + (20 if stale else 0)
            + (15 if missing_baseline else 0)
            + (10 if qa_attention else 0)
        )
        quality_score = max(0, 100 - penalties)
        flags = [
            "thin_mmp_sar_evidence" if thin else "",
            "contradiction_heavy_evidence" if contradiction else "",
            "stale_review_row" if stale else "",
            "missing_baseline_context" if missing_baseline else "",
            "decision_qa_attention" if qa_attention else "",
        ]
        bucket = "attention_required" if contradiction or stale or quality_score < 60 else "watch" if thin or missing_baseline or qa_attention else "clear"
        row = {
            "candidate_id": candidate_id,
            "quality_bucket": bucket,
            "quality_score": quality_score,
            "quality_flags": _flag_text(flags),
            "site_class": source.get("site_class") or board_row.get("site_class", ""),
            "score": source.get("score", ""),
            "review_status": review_status,
            "reviewer": board_row.get("reviewer") or qa_row.get("reviewer") or "",
            "review_age_days": age,
            "risk_bucket": risk_bucket,
            "review_bucket": review_bucket,
            "qa_bucket": qa_bucket,
            "baseline_status": baseline_status,
            "baseline_movement": source.get("baseline_movement") or baseline_row.get("status", ""),
            "evidence_depth_score": evidence_depth,
            "mmp_example_count": mmp_count,
            "sar_example_count": sar_count,
            "thin_mmp_sar_evidence": thin,
            "contradiction_heavy_evidence": contradiction,
            "stale_review_row": stale,
            "missing_baseline_context": missing_baseline,
            "next_action": "",
        }
        row["next_action"] = _next_action(row)
        rows.append(row)
    counts = Counter(str(row.get("quality_bucket") or "") for row in rows)
    flag_counts = Counter(flag for row in rows for flag in str(row.get("quality_flags") or "").split(";") if flag)
    cards = [
        {
            "card_id": "thin_mmp_sar_evidence",
            "label": "Thin MMP/SAR evidence",
            "status": "needs_attention" if flag_counts.get("thin_mmp_sar_evidence") else "ready",
            "value": flag_counts.get("thin_mmp_sar_evidence", 0),
            "details": "Rows with low evidence depth or missing MMP/SAR examples.",
        },
        {
            "card_id": "contradiction_heavy_evidence",
            "label": "Contradiction-heavy evidence",
            "status": "needs_attention" if flag_counts.get("contradiction_heavy_evidence") else "ready",
            "value": flag_counts.get("contradiction_heavy_evidence", 0),
            "details": "Rows carrying non-clear risk, contradiction, or conflict language.",
        },
        {
            "card_id": "stale_review_rows",
            "label": "Stale review rows",
            "status": "needs_attention" if flag_counts.get("stale_review_row") else "ready",
            "value": flag_counts.get("stale_review_row", 0),
            "details": f"Pending-like review rows at or above {int(stale_days)} days.",
        },
        {
            "card_id": "missing_baseline_context",
            "label": "Missing baseline context",
            "status": "needs_attention" if flag_counts.get("missing_baseline_context") else "ready",
            "value": flag_counts.get("missing_baseline_context", 0),
            "details": "Rows without candidate baseline compare context.",
        },
    ]
    return {
        "created_at": now.isoformat(),
        "status": "ready" if rows else "missing_evidence_drawer",
        "mode": "candidate_evidence_quality_scorecard",
        "project_name": project_name,
        "row_count": len(rows),
        "attention_count": counts.get("attention_required", 0),
        "watch_count": counts.get("watch", 0),
        "clear_count": counts.get("clear", 0),
        "quality_bucket_counts": dict(counts.most_common()),
        "flag_counts": dict(flag_counts.most_common()),
        "cards": cards,
        "rows": rows,
        "real_experiment_feedback_used": False,
        "recommended_next_actions": [
            "Use non-clear scorecard rows to focus manual candidate evidence review.",
            "Rebuild baseline compare and evidence drawer before pinning a new candidate baseline.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_evidence_quality_scorecard_markdown(report: dict) -> str:
    lines = [
        "# Evidence Quality Scorecard",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Attention / watch / clear: `{report.get('attention_count')}` / `{report.get('watch_count')}` / `{report.get('clear_count')}`",
        "",
        "| ID | Bucket | Score | Flags | Site | Review | Baseline | Next Action |",
        "| --- | --- | ---: | --- | --- | --- | --- | --- |",
    ]
    for row in (report.get("rows") or [])[:120]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("quality_bucket") or ""),
                    str(row.get("quality_score") or ""),
                    str(row.get("quality_flags") or "").replace("|", "/"),
                    str(row.get("site_class") or ""),
                    str(row.get("review_status") or ""),
                    str(row.get("baseline_status") or ""),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_evidence_quality_scorecard(
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
        "quality_bucket",
        "quality_score",
        "quality_flags",
        "site_class",
        "score",
        "review_status",
        "reviewer",
        "review_age_days",
        "risk_bucket",
        "review_bucket",
        "qa_bucket",
        "baseline_status",
        "baseline_movement",
        "evidence_depth_score",
        "mmp_example_count",
        "sar_example_count",
        "thin_mmp_sar_evidence",
        "contradiction_heavy_evidence",
        "stale_review_row",
        "missing_baseline_context",
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
        md_file.write_text(render_evidence_quality_scorecard_markdown(report), encoding="utf-8")
