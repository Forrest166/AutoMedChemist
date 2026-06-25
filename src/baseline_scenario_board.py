from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASELINE_SCENARIO_BOARD_JSON = Path("data/projects/demo/baseline_scenario_board.json")
DEFAULT_BASELINE_SCENARIO_BOARD_CSV = Path("data/projects/demo/baseline_scenario_board.csv")
DEFAULT_BASELINE_SCENARIO_BOARD_MD = Path("docs/baseline_scenario_board.md")
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


def _count(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _max_delta(*values: object) -> float:
    out = 0.0
    for value in values:
        try:
            out = max(out, abs(float(value or 0)))
        except (TypeError, ValueError):
            continue
    return round(out, 3)


def _row(
    scenario_id: str,
    scenario_type: str,
    label: str,
    status: object,
    details: str,
    *,
    baseline_id: object = "",
    changed: object = 0,
    entered: object = 0,
    exited: object = 0,
    added: object = 0,
    removed: object = 0,
    max_score_delta: object = 0,
    artifact_path: str | Path = "",
    artifact_csv_path: str | Path = "",
    next_action: str = "",
) -> dict[str, Any]:
    movement = _count(changed) + _count(entered) + _count(exited) + _count(added) + _count(removed)
    return {
        "scenario_id": scenario_id,
        "scenario_type": scenario_type,
        "label": label,
        "status": status or "missing",
        "baseline_id": baseline_id or "",
        "movement_count": movement,
        "changed_count": _count(changed),
        "entered_count": _count(entered),
        "exited_count": _count(exited),
        "added_count": _count(added),
        "removed_count": _count(removed),
        "max_abs_score_delta": _max_delta(max_score_delta),
        "details": details,
        "artifact_path": str(artifact_path or ""),
        "artifact_csv_path": str(artifact_csv_path or ""),
        "next_action": next_action,
        "export_scope": "local_baseline_scenario_board",
        "procurement_allowed": False,
        "feedback_import_allowed": False,
    }


def build_baseline_scenario_board(*, root: str | Path = ".", project_name: str = "demo") -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    baseline_history = _read_json(project_dir / "baseline_history_explorer.json")
    active_preview = _read_json(project_dir / "baseline_active_preview.json") or (baseline_history.get("active_preview") or {})
    active_row = (active_preview.get("preview") or (active_preview.get("rows") or [{}])[0] if active_preview else {}) or {}
    candidate_baseline = _read_json(project_dir / "candidate_baseline_compare.json")
    governance_diff = _read_json(project_dir / "local_governance_diff_report.json")
    policy_compare = _read_json(project_dir / "evidence_value_policy_active_compare.json")
    profile_compare = _read_json(project_dir / "profile_rollback_snapshot_compare.json")
    lineage_compare = _read_json(project_dir / "baseline_lineage_compare.json")

    rows = [
        _row(
            "active_baseline_to_current",
            "active_baseline",
            "Active baseline -> current candidates",
            active_preview.get("status") or baseline_history.get("status"),
            (
                f"active={active_preview.get('active_baseline_id') or baseline_history.get('active_baseline_id')}; "
                f"matrix={baseline_history.get('matrix_row_count')}; rollback={baseline_history.get('rollback_option_count')}"
            ),
            baseline_id=active_preview.get("active_baseline_id") or baseline_history.get("active_baseline_id"),
            changed=active_row.get("changed_candidate_count"),
            entered=active_row.get("entered_candidate_count"),
            exited=active_row.get("exited_candidate_count"),
            max_score_delta=active_row.get("max_abs_score_delta"),
            artifact_path=project_dir / "baseline_active_preview.json",
            artifact_csv_path=project_dir / "baseline_history_explorer_matrix.csv",
            next_action="Compare active-to-current movement before changing local baseline assumptions.",
        ),
        _row(
            "candidate_baseline_compare",
            "candidate_baseline",
            "Candidate baseline compare",
            candidate_baseline.get("status"),
            f"baseline={candidate_baseline.get('baseline_id')}; changed={candidate_baseline.get('changed_candidate_count')}; added={candidate_baseline.get('added_candidate_count')}; removed={candidate_baseline.get('removed_candidate_count')}",
            baseline_id=candidate_baseline.get("baseline_id"),
            changed=candidate_baseline.get("changed_candidate_count"),
            added=candidate_baseline.get("added_candidate_count"),
            removed=candidate_baseline.get("removed_candidate_count"),
            max_score_delta=candidate_baseline.get("max_abs_score_delta"),
            artifact_path=project_dir / "candidate_baseline_compare.json",
            artifact_csv_path=project_dir / "candidate_baseline_compare.csv",
            next_action="Review candidate-level movement before pinning a candidate baseline.",
        ),
        _row(
            "lineage_compare",
            "candidate_lineage",
            "Baseline lineage compare",
            lineage_compare.get("status"),
            f"base={lineage_compare.get('base_baseline_id')}; head={lineage_compare.get('head_baseline_id')}; changed={lineage_compare.get('changed_candidate_count')}; entered={lineage_compare.get('entered_candidate_count')}; exited={lineage_compare.get('exited_candidate_count')}",
            baseline_id=f"{lineage_compare.get('base_baseline_id') or ''}->{lineage_compare.get('head_baseline_id') or ''}",
            changed=lineage_compare.get("changed_candidate_count"),
            entered=lineage_compare.get("entered_candidate_count"),
            exited=lineage_compare.get("exited_candidate_count"),
            max_score_delta=lineage_compare.get("max_abs_score_delta"),
            artifact_path=project_dir / "baseline_lineage_compare.json",
            artifact_csv_path=project_dir / "baseline_lineage_compare.csv",
            next_action="Use lineage rows to explain candidate-level baseline movement.",
        ),
        _row(
            "governance_policy_diff",
            "policy_profile",
            "Governance policy diff",
            governance_diff.get("status"),
            f"changed={governance_diff.get('changed_candidate_count')}; added={governance_diff.get('added_candidate_count')}; removed={governance_diff.get('removed_candidate_count')}",
            changed=governance_diff.get("changed_candidate_count"),
            added=governance_diff.get("added_candidate_count"),
            removed=governance_diff.get("removed_candidate_count"),
            max_score_delta=governance_diff.get("max_abs_score_delta"),
            artifact_path=project_dir / "local_governance_diff_report.json",
            artifact_csv_path=project_dir / "local_governance_diff_report.csv",
            next_action="Separate policy/profile changes from candidate baseline movement before local review.",
        ),
        _row(
            "evidence_value_policy_active_compare",
            "policy_profile",
            "Evidence-value active policy compare",
            policy_compare.get("status") or "missing",
            f"policy={policy_compare.get('policy_version') or policy_compare.get('active_policy_version') or ''}; rows={policy_compare.get('row_count')}; changed={policy_compare.get('changed_candidate_count')}",
            baseline_id=policy_compare.get("policy_version") or policy_compare.get("active_policy_version"),
            changed=policy_compare.get("changed_candidate_count"),
            added=policy_compare.get("added_candidate_count"),
            removed=policy_compare.get("removed_candidate_count"),
            max_score_delta=policy_compare.get("max_abs_score_delta"),
            artifact_path=project_dir / "evidence_value_policy_active_compare.json",
            artifact_csv_path=project_dir / "evidence_value_policy_active_compare.csv",
            next_action="Check evidence-value policy drift separately from structural candidate movement.",
        ),
        _row(
            "profile_rollback_snapshot_compare",
            "policy_profile",
            "Profile rollback snapshot compare",
            profile_compare.get("status") or "missing",
            f"base={profile_compare.get('base_snapshot_id')}; head={profile_compare.get('head_snapshot_id')}; changed={profile_compare.get('changed_candidate_count')}",
            baseline_id=f"{profile_compare.get('base_snapshot_id') or ''}->{profile_compare.get('head_snapshot_id') or ''}",
            changed=profile_compare.get("changed_candidate_count"),
            added=profile_compare.get("added_candidate_count"),
            removed=profile_compare.get("removed_candidate_count"),
            max_score_delta=profile_compare.get("max_abs_score_delta"),
            artifact_path=project_dir / "profile_rollback_snapshot_compare.json",
            artifact_csv_path=project_dir / "profile_rollback_snapshot_compare.csv",
            next_action="Use rollback snapshots as local explanatory context only.",
        ),
    ]
    ready_rows = [row for row in rows if str(row.get("status") or "").lower() not in {"", "missing"}]
    attention_count = sum(1 for row in rows if _count(row.get("movement_count")) > 0 or str(row.get("status") or "").lower() in {"warn", "attention_required", "review_required"})
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if ready_rows else "missing_inputs",
        "mode": "baseline_scenario_board",
        "project_name": project_name,
        "row_count": len(rows),
        "ready_row_count": len(ready_rows),
        "attention_count": attention_count,
        "rows": rows,
        "recommended_next_actions": [
            "Use this board to compare active baseline, candidate baseline, and policy/profile changes without mixing their causes.",
            "Open the artifact for any row with movement_count > 0 before pinning, rolling back, or changing a local scoring profile.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_baseline_scenario_board_markdown(report: dict) -> str:
    lines = [
        "# Baseline Scenario Board",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows / attention: `{report.get('row_count')}` / `{report.get('attention_count')}`",
        "",
        "| Scenario | Type | Status | Baseline | Movement | dScore | Details | Next Action |",
        "| --- | --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("label") or row.get("scenario_id") or ""),
                    str(row.get("scenario_type") or ""),
                    str(row.get("status") or ""),
                    str(row.get("baseline_id") or ""),
                    str(row.get("movement_count") or 0),
                    str(row.get("max_abs_score_delta") or 0),
                    str(row.get("details") or "").replace("|", "/"),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_baseline_scenario_board(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_BASELINE_SCENARIO_BOARD_JSON,
    csv_path: str | Path | None = DEFAULT_BASELINE_SCENARIO_BOARD_CSV,
    markdown_path: str | Path | None = DEFAULT_BASELINE_SCENARIO_BOARD_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "scenario_id",
        "scenario_type",
        "label",
        "status",
        "baseline_id",
        "movement_count",
        "changed_count",
        "entered_count",
        "exited_count",
        "added_count",
        "removed_count",
        "max_abs_score_delta",
        "details",
        "artifact_path",
        "artifact_csv_path",
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
        md_file.write_text(render_baseline_scenario_board_markdown(report), encoding="utf-8")
