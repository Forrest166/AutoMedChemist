from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASELINE_WHATIF_JSON = Path("data/projects/demo/baseline_whatif_board.json")
DEFAULT_BASELINE_WHATIF_CSV = Path("data/projects/demo/baseline_whatif_board.csv")
DEFAULT_BASELINE_WHATIF_MD = Path("docs/baseline_whatif_board.md")
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


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


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


def _by_candidate(report: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in report.get("rows") or []:
        if isinstance(row, dict) and row.get("candidate_id"):
            out[str(row.get("candidate_id"))] = dict(row)
    return out


def _scenario_score(candidate: dict, scenario_id: str, refs: dict[str, dict[str, dict]]) -> tuple[float, str, str]:
    candidate_id = str(candidate.get("candidate_id") or "")
    current_score = _float(candidate.get("score"))
    if scenario_id == "current":
        return current_score, "current", "Current candidate score."
    if scenario_id == "active_baseline":
        row = refs["lineage"].get(candidate_id, {})
        score = _float(row.get("base_score"), current_score)
        return score, str(row.get("lineage_status") or row.get("status") or "stable"), row.get("rationale") or "Score under active baseline context."
    if scenario_id == "candidate_baseline":
        row = refs["candidate_baseline"].get(candidate_id, {})
        score = _float(row.get("base_score") or row.get("head_score"), current_score)
        return score, str(row.get("status") or "stable"), row.get("changed_fields") or "Named candidate baseline context."
    if scenario_id == "evidence_policy_active":
        row = refs["policy"].get(candidate_id, {})
        score = _float(row.get("active_score"), current_score + _float(row.get("score_delta"), 0.0))
        return score, "policy_delta" if row else "unchanged", row.get("value_driver_flags") or row.get("next_evidence_action") or "Active evidence-value policy context."
    if scenario_id == "profile_rollback":
        row = refs["profile"].get(candidate_id, {})
        delta = _float(row.get("rollback_score_delta_change"), _float(row.get("head_rollback_score_delta"), 0.0) - _float(row.get("base_rollback_score_delta"), 0.0))
        return current_score + delta, str(row.get("status") or "unchanged"), row.get("head_rollback_action") or row.get("base_rollback_action") or "Profile rollback snapshot context."
    return current_score, "unknown", ""


def build_baseline_whatif_board(*, root: str | Path = ".", project_name: str = "demo", max_candidates: int = 120) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    candidate_rows = _read_csv(project_dir / "candidates.csv")[:max_candidates]
    refs = {
        "lineage": _by_candidate(_read_json(project_dir / "baseline_lineage_compare.json")),
        "candidate_baseline": _by_candidate(_read_json(project_dir / "candidate_baseline_compare.json")),
        "policy": _by_candidate(_read_json(project_dir / "evidence_value_policy_active_compare.json")),
        "profile": _by_candidate(_read_json(project_dir / "profile_rollback_snapshot_compare.json")),
    }
    scenario_defs = [
        ("current", "Current ranking"),
        ("active_baseline", "Active baseline"),
        ("candidate_baseline", "Candidate baseline"),
        ("evidence_policy_active", "Evidence policy"),
        ("profile_rollback", "Profile rollback"),
    ]
    scenario_scores: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidate_rows:
        candidate_id = str(candidate.get("candidate_id") or "")
        if not candidate_id:
            continue
        for scenario_id, scenario_label in scenario_defs:
            score, movement_status, reason = _scenario_score(candidate, scenario_id, refs)
            scenario_scores[scenario_id].append(
                {
                    "candidate_id": candidate_id,
                    "scenario_id": scenario_id,
                    "scenario_label": scenario_label,
                    "whatif_score": round(score, 3),
                    "movement_status": movement_status,
                    "movement_reason": reason,
                    "site_class": candidate.get("site_class") or candidate.get("site_type") or "",
                    "smiles": candidate.get("smiles") or "",
                }
            )
    current_rank = {
        row["candidate_id"]: idx
        for idx, row in enumerate(sorted(scenario_scores.get("current", []), key=lambda item: _float(item.get("whatif_score")), reverse=True), start=1)
    }
    current_score = {row["candidate_id"]: _float(row.get("whatif_score")) for row in scenario_scores.get("current", [])}
    rows: list[dict[str, Any]] = []
    for scenario_id, scenario_label in scenario_defs:
        ranked = sorted(scenario_scores.get(scenario_id, []), key=lambda item: _float(item.get("whatif_score")), reverse=True)
        for rank, row in enumerate(ranked, start=1):
            candidate_id = row["candidate_id"]
            base_rank = current_rank.get(candidate_id, rank)
            score_delta = round(_float(row.get("whatif_score")) - current_score.get(candidate_id, 0.0), 3)
            review_required = scenario_id != "current" and (rank != base_rank or abs(score_delta) >= 0.25 or row.get("movement_status") not in {"stable", "unchanged", "current"})
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "scenario_id": scenario_id,
                    "scenario_label": scenario_label,
                    "current_rank": base_rank,
                    "whatif_rank": rank,
                    "rank_delta": rank - base_rank,
                    "current_score": round(current_score.get(candidate_id, 0.0), 3),
                    "whatif_score": row.get("whatif_score"),
                    "score_delta": score_delta,
                    "movement_status": row.get("movement_status"),
                    "movement_reason": str(row.get("movement_reason") or "")[:240],
                    "site_class": row.get("site_class", ""),
                    "smiles": row.get("smiles", ""),
                    "review_required": review_required,
                    "source_artifact": str(project_dir / ("baseline_lineage_compare.json" if scenario_id == "active_baseline" else "candidate_baseline_compare.json" if scenario_id == "candidate_baseline" else "evidence_value_policy_active_compare.json" if scenario_id == "evidence_policy_active" else "profile_rollback_snapshot_compare.json" if scenario_id == "profile_rollback" else "candidates.csv")),
                    "next_action": "Inspect movement before changing local ranking context." if review_required else "No material what-if movement.",
                    "export_scope": "local_baseline_whatif_board",
                    "procurement_allowed": False,
                    "feedback_import_allowed": False,
                }
            )
    scenario_counts = Counter(row["scenario_id"] for row in rows)
    review_count = sum(1 for row in rows if row.get("review_required"))
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "missing_candidates",
        "mode": "baseline_whatif_board",
        "project_name": project_name,
        "row_count": len(rows),
        "candidate_count": len({row.get("candidate_id") for row in rows}),
        "scenario_count": len(scenario_defs),
        "review_required_count": review_count,
        "scenario_counts": dict(scenario_counts.most_common()),
        "rows": rows,
        "recommended_next_actions": [
            "Use scenario_id filters in the native UI to compare active baseline, candidate baseline, policy, and profile movement.",
            "Treat review_required rows as local explanation tasks before changing rank context.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_baseline_whatif_board_markdown(report: dict) -> str:
    lines = [
        "# Baseline What-If Board",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows / review required: `{report.get('row_count')}` / `{report.get('review_required_count')}`",
        "",
        "| Scenario | Candidate | Current Rank | What-If Rank | dRank | Current | What-If | dScore | Status | Reason |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in (report.get("rows") or [])[:160]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("scenario_label") or row.get("scenario_id") or ""),
                    str(row.get("candidate_id") or ""),
                    str(row.get("current_rank") or ""),
                    str(row.get("whatif_rank") or ""),
                    str(row.get("rank_delta") or 0),
                    str(row.get("current_score") or 0),
                    str(row.get("whatif_score") or 0),
                    str(row.get("score_delta") or 0),
                    str(row.get("movement_status") or ""),
                    str(row.get("movement_reason") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_baseline_whatif_board(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_BASELINE_WHATIF_JSON,
    csv_path: str | Path | None = DEFAULT_BASELINE_WHATIF_CSV,
    markdown_path: str | Path | None = DEFAULT_BASELINE_WHATIF_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "candidate_id",
        "scenario_id",
        "scenario_label",
        "current_rank",
        "whatif_rank",
        "rank_delta",
        "current_score",
        "whatif_score",
        "score_delta",
        "movement_status",
        "movement_reason",
        "site_class",
        "smiles",
        "review_required",
        "source_artifact",
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
        md_file.write_text(render_baseline_whatif_board_markdown(report), encoding="utf-8")
