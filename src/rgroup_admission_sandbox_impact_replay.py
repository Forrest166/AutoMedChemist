from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_JSON = Path("data/substituents/rgroup_admission_sandbox_impact_replay.json")
DEFAULT_CSV = Path("data/substituents/rgroup_admission_sandbox_impact_replay.csv")
DEFAULT_MD = Path("docs/rgroup_admission_sandbox_impact_replay.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import", "production_scoring_write"]


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _split(value: object) -> list[str]:
    return [part.strip() for part in str(value or "").replace(";", ",").split(",") if part.strip()]


def _replacement_source_map(ledger: dict) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in ledger.get("rows") or []:
        source = str(row.get("source_dataset") or "").strip()
        for key in ["replacement_id", "substituent_id", "record_id"]:
            replacement_id = str(row.get(key) or "").strip()
            if replacement_id and source:
                mapping[replacement_id] = source
    return mapping


def _signoff_by_review_id(signoff: dict) -> dict[str, dict]:
    return {
        str(row.get("review_id") or ""): dict(row)
        for row in signoff.get("rows") or []
        if row.get("review_id")
    }


def _source_matches_sandbox(source: str, candidate_ids: set[str], replacement_source: dict[str, str], sandbox_rows: list[dict]) -> list[dict]:
    matches: list[dict] = []
    for row in sandbox_rows:
        candidate_id = str(row.get("candidate_id") or "").strip()
        replacement_ids = _split(row.get("matched_replacement_ids"))
        replacement_match = any(replacement_source.get(replacement_id) == source for replacement_id in replacement_ids)
        if (candidate_ids and candidate_id in candidate_ids) or replacement_match:
            matches.append(dict(row))
    return matches


def _replay_status(source_matches: list[dict], signoff_rows: list[dict], sandbox_status: str) -> str:
    if sandbox_status in {"", "missing"}:
        return "sandbox_missing"
    if not source_matches:
        return "no_sandbox_match"
    decisions = {str(row.get("operator_decision") or "").lower() for row in signoff_rows}
    if "" in decisions or not decisions:
        return "needs_operator_review"
    if decisions <= {"approved"}:
        return "sandbox_replayed"
    if decisions & {"deferred", "rejected"}:
        return "holdout_reviewed"
    return "sandbox_replayed"


def build_rgroup_admission_sandbox_impact_replay(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    feed_dir = root_path / "data" / "substituents"
    admission = _read_json(feed_dir / "rgroup_staging_admission_scorecard.json")
    sandbox = _read_json(project_dir / "staged_feed_sandbox_scoring.json")
    delta = _read_json(project_dir / "sandbox_score_delta_review_packet.json")
    signoff = _read_json(project_dir / "sandbox_score_delta_signoff_ledger.json")
    ledger = _read_json(feed_dir / "rgroup_feed_digestion_ledger.json")

    sandbox_rows = [dict(row) for row in sandbox.get("rows") or []]
    delta_rows = [dict(row) for row in delta.get("rows") or []]
    delta_by_candidate = {str(row.get("candidate_id") or ""): dict(row) for row in delta_rows}
    signoff_by_id = _signoff_by_review_id(signoff)
    replacement_source = _replacement_source_map(ledger)
    rows: list[dict[str, Any]] = []

    for rank, source_row in enumerate(admission.get("rows") or [], start=1):
        source = str(source_row.get("source_dataset") or "").strip()
        candidate_ids = set(_split(source_row.get("impacted_candidate_ids")))
        matched_sandbox_rows = _source_matches_sandbox(source, candidate_ids, replacement_source, sandbox_rows)
        matched_delta_rows = []
        signoff_rows = []
        for sandbox_row in matched_sandbox_rows:
            candidate_id = str(sandbox_row.get("candidate_id") or "")
            delta_row = delta_by_candidate.get(candidate_id, {})
            if delta_row:
                matched_delta_rows.append(delta_row)
                signoff_row = signoff_by_id.get(str(delta_row.get("review_id") or ""), {})
                if signoff_row:
                    signoff_rows.append(signoff_row)
        max_score_delta = max([abs(_float(row.get("score_delta") or row.get("sandbox_score_delta_preview"))) for row in matched_delta_rows or matched_sandbox_rows] or [0.0])
        max_rank_delta = max([abs(_float(row.get("rank_delta") or row.get("sandbox_rank_delta_preview"))) for row in matched_delta_rows or matched_sandbox_rows] or [0.0])
        decisions = Counter(str(row.get("operator_decision") or "").lower() or "pending" for row in signoff_rows)
        replay_status = _replay_status(matched_sandbox_rows, signoff_rows, str(sandbox.get("status") or "missing"))
        rows.append(
            {
                "replay_id": f"RGSR-{rank:04d}",
                "source_dataset": source,
                "admission_rank": source_row.get("rank") or rank,
                "admission_bucket": source_row.get("admission_bucket") or "",
                "admission_score": source_row.get("admission_score") or "",
                "replay_status": replay_status,
                "impacted_candidate_count": len(candidate_ids) or int(source_row.get("candidate_impacted_row_count") or 0),
                "matched_sandbox_row_count": len(matched_sandbox_rows),
                "matched_delta_review_count": len(matched_delta_rows),
                "max_abs_score_delta": round(max_score_delta, 3),
                "max_abs_rank_delta": round(max_rank_delta, 3),
                "signoff_decisions": dict(decisions.most_common()),
                "rollback_ready": True,
                "rollback_plan": f"Remove staged rows bound to {source}, rebuild sandbox score-delta packet, and compare this replay snapshot.",
                "explanation": (
                    f"{source} has {len(matched_sandbox_rows)} sandbox matches; max score delta={round(max_score_delta, 3)}; "
                    f"max rank delta={round(max_rank_delta, 3)}; status={replay_status}."
                ),
                "production_scoring_write_allowed": False,
                "promotion_allowed": False,
                "next_action": (
                    "Review source in sandbox and collect operator signoff before any promotion discussion."
                    if replay_status in {"needs_operator_review", "no_sandbox_match", "sandbox_missing"}
                    else "Keep replay packet with the admission scorecard for reversible local review."
                ),
            }
        )

    status_counts = Counter(str(row.get("replay_status") or "unknown") for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "mode": "rgroup_admission_sandbox_impact_replay",
        "project_name": project_name,
        "row_count": len(rows),
        "source_count": len(rows),
        "sandbox_status": sandbox.get("status") or "missing",
        "delta_review_status": delta.get("status") or "missing",
        "rollback_ready_count": sum(1 for row in rows if row.get("rollback_ready") is True),
        "needs_operator_review_count": status_counts.get("needs_operator_review", 0),
        "replay_status_counts": dict(status_counts.most_common()),
        "production_scoring_write_allowed": False,
        "promotion_allowed": False,
        "rows": rows,
        "recommended_next_actions": [
            "Use replay rows to explain why an admitted source is or is not ready for sandbox signoff.",
            "Treat rollback_plan as a local reversible review instruction, not a production write.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_rgroup_admission_sandbox_impact_replay_markdown(report: dict) -> str:
    lines = [
        "# R-group Admission Sandbox Impact Replay",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Sources: `{report.get('source_count')}`",
        f"- Production scoring writes allowed: `{report.get('production_scoring_write_allowed')}`",
        "",
        "| Source | Bucket | Status | Sandbox Rows | Max Score Delta | Max Rank Delta | Rollback | Next Action |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("source_dataset") or ""),
                    str(row.get("admission_bucket") or ""),
                    str(row.get("replay_status") or ""),
                    str(row.get("matched_sandbox_row_count") or 0),
                    str(row.get("max_abs_score_delta") or 0),
                    str(row.get("max_abs_rank_delta") or 0),
                    "ready" if row.get("rollback_ready") else "missing",
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_rgroup_admission_sandbox_impact_replay(
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
        "replay_id",
        "source_dataset",
        "admission_rank",
        "admission_bucket",
        "admission_score",
        "replay_status",
        "impacted_candidate_count",
        "matched_sandbox_row_count",
        "matched_delta_review_count",
        "max_abs_score_delta",
        "max_abs_rank_delta",
        "signoff_decisions",
        "rollback_ready",
        "rollback_plan",
        "explanation",
        "production_scoring_write_allowed",
        "promotion_allowed",
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
        md_file.write_text(render_rgroup_admission_sandbox_impact_replay_markdown(report), encoding="utf-8")
