from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


DEFAULT_GOVERNED_INGESTION_BATCHES_JSON = Path("data/substituents/governed_ingestion_batches.json")
DEFAULT_GOVERNED_INGESTION_BATCHES_CSV = Path("data/substituents/governed_ingestion_batches.csv")
DEFAULT_GOVERNED_INGESTION_BATCHES_MD = Path("docs/governed_ingestion_batches.md")
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


def _read_yaml(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _int(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _gate_summary(*items: tuple[str, object]) -> str:
    return ";".join(f"{name}={value or 'missing'}" for name, value in items)


def build_governed_ingestion_batches(*, root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    source_guard = _read_json(root_path / "data/substituents/source_expansion_governance.json")
    simulator = _read_json(root_path / "data/substituents/feed_promotion_simulator.json")
    sandbox = _read_json(root_path / "data/projects/demo/staged_feed_sandbox_scoring.json")
    staging_budget = _read_json(root_path / "data/substituents/rgroup_staging_quality_budget.json")
    sandbox_review = _read_json(root_path / "data/projects/demo/sandbox_score_delta_review_packet.json")
    promotion_approval = _read_json(root_path / "data/substituents/rgroup_promotion_approval_ledger.json")
    diff = _read_json(root_path / "data/substituents/feed_absorption_diff_navigator.json")
    foundation = _read_json(root_path / "data/substituents/data_foundation_report.json")
    acceptance = _read_yaml(root_path / "data/rules/source_acceptance_manifest.yaml")
    staging = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_staging_gate.json")
    totals = foundation.get("totals") or {}
    source_guard_ready = source_guard.get("status") == "ready" and source_guard.get("ungated_expansion_allowed") is False
    foundation_ready = _int(totals.get("missing_asset_count")) == 0 and _int(totals.get("warning_count")) == 0
    allowed_scopes = source_guard.get("allowed_expansion_scopes") or ["ring_system", "rgroup_replacement", "literature_substituent", "substituent"]
    accepted_change_count = len(acceptance.get("accepted_changes", []) or acceptance.get("acceptances", []) or [])

    scope_policies = {
        "ring_system": {
            "max_new_rows": 50000,
            "quality_budget": "source_acceptance; ring_import_status; data_foundation_delta; no_missing_assets",
            "current_gate_status": source_guard.get("status"),
            "staged_row_count": 0,
        },
        "rgroup_replacement": {
            "max_new_rows": max(100, _int(simulator.get("staged_row_count")) or 1000),
            "quality_budget": "source_acceptance; feed_staging_gate; staging_quality_budget; promotion_simulator; sandbox_scoring_preview; sandbox_delta_signoff; duplicate_watch; owner_ledger",
            "current_gate_status": staging_budget.get("status") or simulator.get("status") or diff.get("status"),
            "staged_row_count": simulator.get("staged_row_count") or staging.get("staged_row_count") or 0,
        },
        "literature_substituent": {
            "max_new_rows": 1000,
            "quality_budget": "source_acceptance; provenance; literature_review; data_foundation_delta",
            "current_gate_status": source_guard.get("status"),
            "staged_row_count": 0,
        },
        "substituent": {
            "max_new_rows": 1000,
            "quality_budget": "source_acceptance; standardization; review_queue; data_foundation_delta",
            "current_gate_status": source_guard.get("status"),
            "staged_row_count": 0,
        },
    }

    rows: list[dict[str, Any]] = []
    for index, scope in enumerate(allowed_scopes, start=1):
        policy = scope_policies.get(str(scope), scope_policies["substituent"])
        staged_rows = _int(policy.get("staged_row_count"))
        sandbox_review_status = str(sandbox_review.get("status") or "")
        sandbox_production_approved = sandbox_review.get("production_scoring_approved") is True
        status = "awaiting_rows"
        if staged_rows > 0:
            status = "ready_for_batch_design" if source_guard_ready and foundation_ready else "blocked"
            promotion_allowed = promotion_approval.get("promotion_allowed") is True
            if scope == "rgroup_replacement" and simulator.get("status") == "blocked":
                status = "blocked"
            elif scope == "rgroup_replacement" and staging_budget.get("status") == "blocked":
                status = "blocked"
            elif scope == "rgroup_replacement" and sandbox_review.get("status") == "blocked":
                status = "blocked"
            elif scope == "rgroup_replacement" and promotion_approval.get("status") == "blocked":
                status = "blocked"
            elif scope == "rgroup_replacement" and simulator.get("status") == "awaiting_filled_staging_rows":
                status = "blocked"
            elif scope == "rgroup_replacement" and not sandbox_production_approved:
                status = "reviewed_holdout" if sandbox_review_status in {"reviewed_holdout", "review_required"} else "blocked"
            elif scope == "rgroup_replacement" and not promotion_allowed:
                status = "reviewed_holdout" if promotion_approval.get("status") in {"reviewed_holdout", "pending_approval", "partially_approved_holdout"} else "blocked"
        elif scope == "rgroup_replacement" and simulator.get("status") == "awaiting_filled_staging_rows":
            status = "awaiting_rows"
        rows.append(
            {
                "batch_id": f"GIN-{index:03d}-{scope}",
                "intake_scope": scope,
                "batch_status": status,
                "allowed_to_ingest": status in {"ready_for_batch_design"} and staged_rows > 0,
                "max_new_rows": policy["max_new_rows"],
                "staged_row_count": staged_rows,
                "quality_budget": policy["quality_budget"],
                "required_gates": "source_acceptance_manifest;source_expansion_governance;data_foundation;promotion_simulator",
                "current_gate_status": policy["current_gate_status"] or "missing",
                "gate_summary": _gate_summary(
                    ("source_guard", source_guard.get("status")),
                    ("foundation_missing", totals.get("missing_asset_count")),
                    ("foundation_warnings", totals.get("warning_count")),
                    ("simulator", simulator.get("status")),
                    ("sandbox", sandbox.get("status")),
                    ("staging_budget", staging_budget.get("status")),
                    ("sandbox_review", sandbox_review.get("status")),
                    ("promotion_approval", promotion_approval.get("status")),
                    ("accepted_changes", accepted_change_count),
                ),
                "data_foundation_delta_required": True,
                "next_action": (
                    "Fill governed staging rows and rerun simulator."
                    if status == "awaiting_rows"
                    else "Keep staged rows in holdout until sandbox delta signoff and promotion approval both approve production intake."
                    if status == "reviewed_holdout"
                    else "Create batch only after all gates are ready and data-foundation delta is reviewed."
                ),
            }
        )

    blocked_count = sum(1 for row in rows if row.get("batch_status") == "blocked")
    awaiting_count = sum(1 for row in rows if row.get("batch_status") == "awaiting_rows")
    holdout_count = sum(1 for row in rows if row.get("batch_status") == "reviewed_holdout")
    status = "blocked" if blocked_count else "awaiting_rows" if awaiting_count else "reviewed_holdout" if holdout_count else "ready"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "governed_ingestion_batches",
        "row_count": len(rows),
        "blocked_batch_count": blocked_count,
        "awaiting_row_batch_count": awaiting_count,
        "reviewed_holdout_batch_count": holdout_count,
        "allowed_ingestion_batch_count": sum(1 for row in rows if row.get("allowed_to_ingest") is True),
        "accepted_change_count": accepted_change_count,
        "sandbox_scoring_status": sandbox.get("status") or "missing",
        "sandbox_scored_candidate_count": sandbox.get("candidate_count", 0),
        "sandbox_matched_candidate_count": sandbox.get("candidate_with_staged_match_count", 0),
        "staging_quality_budget_status": staging_budget.get("status") or "missing",
        "staging_quality_budget_blocker_count": staging_budget.get("blocker_count", 0),
        "sandbox_score_delta_review_status": sandbox_review.get("status") or "missing",
        "sandbox_score_delta_signoff_required_count": sandbox_review.get("operator_signoff_required_count", 0),
        "sandbox_score_delta_approved": sandbox_review.get("production_scoring_approved") is True,
        "rgroup_promotion_approval_status": promotion_approval.get("status") or "missing",
        "rgroup_promotion_approval_allowed": promotion_approval.get("promotion_allowed") is True,
        "rgroup_promotion_approval_pending_count": promotion_approval.get("pending_approval_count", 0),
        "rgroup_promotion_approval_approved_count": promotion_approval.get("approved_count", 0),
        "data_foundation_delta_required": True,
        "rows": rows,
        "recommended_next_actions": [
            "Use governed batches to scale intake only after source acceptance, simulator, promotion approval, and data-foundation gates pass.",
            "Do not ingest rows directly into scoring libraries outside these batch gates.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_governed_ingestion_batches_markdown(report: dict) -> str:
    lines = [
        "# Governed Ingestion Batches",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Allowed ingestion batches: `{report.get('allowed_ingestion_batch_count')}`",
        "",
        "| Batch | Scope | Status | Allowed | Staged | Max Rows | Gate Status | Next Action |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("batch_id") or ""),
                    str(row.get("intake_scope") or ""),
                    str(row.get("batch_status") or ""),
                    str(row.get("allowed_to_ingest")),
                    str(row.get("staged_row_count") or 0),
                    str(row.get("max_new_rows") or 0),
                    str(row.get("current_gate_status") or ""),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_governed_ingestion_batches(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_GOVERNED_INGESTION_BATCHES_JSON,
    csv_path: str | Path | None = DEFAULT_GOVERNED_INGESTION_BATCHES_CSV,
    markdown_path: str | Path | None = DEFAULT_GOVERNED_INGESTION_BATCHES_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "batch_id",
        "intake_scope",
        "batch_status",
        "allowed_to_ingest",
        "max_new_rows",
        "staged_row_count",
        "quality_budget",
        "required_gates",
        "current_gate_status",
        "gate_summary",
        "data_foundation_delta_required",
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
        md_file.write_text(render_governed_ingestion_batches_markdown(report), encoding="utf-8")
