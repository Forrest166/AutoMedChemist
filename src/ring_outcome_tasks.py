from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .evidence_confidence import EVIDENCE_RESIDUAL_TASK_STATUSES


DEFAULT_RING_OUTCOME_OVERLAY_PATH = Path("data/profiles/calibrated/ring_outcome_scoring_overlay.json")
DEFAULT_RING_OUTCOME_TASK_REPORT_PATH = Path("data/projects/demo/ring_outcome_residual_tasks.json")
DEFAULT_RING_OUTCOME_TASK_CSV_PATH = Path("data/projects/demo/ring_outcome_residual_tasks.csv")
RING_OUTCOME_TASK_PREFIX = "RINGTASK-"


def _load_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        return json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _float(value: object, default: float = 0.0) -> float:
    try:
        if value in {None, ""}:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: object, default: int = 0) -> int:
    try:
        if value in {None, ""}:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _task_id(context_id: object) -> str:
    digest = hashlib.sha1(str(context_id or "").encode("utf-8")).hexdigest()[:10].upper()
    return f"{RING_OUTCOME_TASK_PREFIX}{digest}"


def _reason_set(value: object) -> set[str]:
    return {part.strip() for part in str(value or "").split(";") if part.strip()}


def build_ring_outcome_residual_tasks(
    overlay: dict | str | Path,
    *,
    max_tasks: int = 20,
) -> dict:
    """Convert low-sample blocked ring outcome overlay contexts into measurement tasks."""
    payload = _load_json(overlay) if isinstance(overlay, (str, Path)) else dict(overlay or {})
    min_observed = max(1, _int(payload.get("min_observed"), 3))
    rows = []
    for context in payload.get("contexts") or []:
        reasons = _reason_set(context.get("gate_reasons"))
        if str(context.get("gate_status") or "") == "active" or "below_min_observed" not in reasons:
            continue
        review_decision = str(context.get("review_decision") or "").strip().lower()
        if review_decision in {"rejected", "retired"}:
            continue
        observed = _int(context.get("observed_count"))
        gap = max(1, min_observed - observed)
        proposed = _float(context.get("proposed_score_adjustment"))
        hit_rate = context.get("hit_rate")
        ci_low = context.get("hit_rate_ci_low")
        ci_high = context.get("hit_rate_ci_high")
        ci_width = _float(ci_high) - _float(ci_low) if ci_low not in {None, ""} and ci_high not in {None, ""} else 1.0
        adjustment_signal = min(1.0, abs(proposed) / 4.0)
        sample_gap_signal = min(1.0, gap / min_observed)
        uncertainty_signal = max(0.0, min(1.0, ci_width))
        expected_information_gain = min(
            1.5,
            (adjustment_signal * 0.45) + (sample_gap_signal * 0.35) + (uncertainty_signal * 0.20),
        )
        priority = "high" if expected_information_gain >= 0.65 or gap >= 2 else "medium"
        if expected_information_gain < 0.35:
            priority = "low"
        if context.get("learning_action") == "promote_context":
            action = "collect_ring_positive_confirmations"
        elif context.get("learning_action") == "downweight_context":
            action = "collect_ring_negative_controls"
        else:
            action = "collect_ring_outcome_followup"
        context_id = str(context.get("context_id") or "")
        rows.append(
            {
                "task_id": _task_id(context_id),
                "task_source": "ring_outcome_overlay",
                "source_context_id": context_id,
                "priority": priority,
                "recommended_action": action,
                "context_scope": "ring_outcome_overlay",
                "endpoint_group": context.get("endpoint") or "unspecified",
                "target_family": "all",
                "assay_type": "ring_outcome_followup",
                "evidence_source": "ring_outcome_learning",
                "calibration_status": "insufficient_ring_outcome_count",
                "observed_count": observed,
                "additional_outcome_target": gap,
                "suggested_next_outcome_count": gap,
                "expected_information_gain": round(expected_information_gain, 4),
                "information_gain_basis": (
                    f"proposed_adjustment={proposed:.4f}; observed={observed}; min_observed={min_observed}; "
                    f"sample_gap={gap}; ci_width={ci_width:.4f}"
                ),
                "abs_residual": round(min(1.0, adjustment_signal * 0.7 + sample_gap_signal * 0.3), 4),
                "calibration_residual": round(proposed / 10.0, 4),
                "residual_sample_status": "thin_ring_outcome_sample",
                "enumeration_type": context.get("enumeration_type"),
                "ring_novelty_bucket": context.get("ring_novelty_bucket"),
                "ring_diversity_bucket": context.get("ring_diversity_bucket"),
                "replacement_class": context.get("replacement_class"),
                "learning_action": context.get("learning_action"),
                "candidate_count": context.get("candidate_count"),
                "positive_count": context.get("positive_count"),
                "negative_count": context.get("negative_count"),
                "neutral_count": context.get("neutral_count"),
                "hit_rate": hit_rate,
                "hit_rate_ci_low": ci_low,
                "hit_rate_ci_high": ci_high,
                "proposed_score_adjustment": context.get("proposed_score_adjustment"),
                "review_decision": review_decision,
                "gate_reasons": context.get("gate_reasons"),
            }
        )
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    rows.sort(
        key=lambda item: (
            priority_rank.get(str(item.get("priority") or "low"), 9),
            -float(item.get("expected_information_gain") or 0.0),
            -int(item.get("additional_outcome_target") or 0),
            str(item.get("task_id") or ""),
        )
    )
    rows = rows[: int(max_tasks)]
    priority_counts = Counter(str(row.get("priority") or "unknown") for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_overlay_created_at": payload.get("source_report_created_at"),
        "min_observed": min_observed,
        "task_count": len(rows),
        "priority_counts": dict(priority_counts.most_common()),
        "tasks": rows,
    }


def merge_ring_outcome_tasks_into_registry(
    task_report: dict | list[dict],
    *,
    existing_registry: dict | None = None,
    reviewer: str | None = None,
    note: str | None = None,
) -> dict:
    """Status-preserving upsert for ring outcome tasks without retiring non-ring residual tasks."""
    now = datetime.now(timezone.utc).isoformat()
    tasks = task_report.get("tasks") if isinstance(task_report, dict) else task_report
    ring_tasks = [dict(row) for row in tasks or [] if str(row.get("task_id") or "").startswith(RING_OUTCOME_TASK_PREFIX)]
    registry = existing_registry or {"tasks": []}
    existing = {str(item.get("task_id")): dict(item) for item in registry.get("tasks") or [] if item.get("task_id")}
    current_ids = {str(item.get("task_id")) for item in ring_tasks if item.get("task_id")}
    out = []
    for previous in registry.get("tasks") or []:
        task_id = str(previous.get("task_id") or "")
        if task_id.startswith(RING_OUTCOME_TASK_PREFIX):
            continue
        out.append(dict(previous))

    for task in ring_tasks:
        task_id = str(task.get("task_id") or "")
        previous = existing.get(task_id, {})
        status = str(previous.get("status") or "open")
        if status not in EVIDENCE_RESIDUAL_TASK_STATUSES:
            status = "open"
        history = list(previous.get("status_history") or [])
        if not previous:
            history.append({"status": status, "created_at": now, "reviewer": reviewer, "note": note or "Ring outcome follow-up task opened."})
        elif any(previous.get(key) != task.get(key) for key in ["priority", "recommended_action", "observed_count", "additional_outcome_target"]):
            history.append({"status": status, "created_at": now, "reviewer": reviewer, "note": note or "Ring outcome task signal refreshed."})
        out.append(
            {
                **previous,
                **task,
                "status": status,
                "created_at": previous.get("created_at") or now,
                "updated_at": now if previous else previous.get("updated_at") or now,
                "last_seen_at": now,
                "reviewer": previous.get("reviewer") or reviewer,
                "status_note": previous.get("status_note") or "",
                "lifecycle_state": "active",
                "status_history": history[-20:],
            }
        )

    for task_id, previous in existing.items():
        if not task_id.startswith(RING_OUTCOME_TASK_PREFIX) or task_id in current_ids:
            continue
        status = str(previous.get("status") or "open")
        history = list(previous.get("status_history") or [])
        if status in {"open", "planned", "outcomes_imported"}:
            status = "resolved_by_calibration"
            history.append({"status": status, "created_at": now, "reviewer": reviewer, "note": note or "Ring context no longer blocked by current overlay."})
        out.append(
            {
                **previous,
                "status": status,
                "updated_at": now,
                "lifecycle_state": "not_in_current_overlay",
                "status_history": history[-20:],
            }
        )

    status_counts = Counter(str(item.get("status") or "unknown") for item in out)
    active_priority_counts = Counter(str(item.get("priority") or "unknown") for item in out if item.get("lifecycle_state") == "active")
    return {
        "created_at": registry.get("created_at") or now,
        "updated_at": now,
        "task_count": len(out),
        "active_task_count": sum(1 for item in out if item.get("lifecycle_state") == "active"),
        "status_counts": dict(status_counts.most_common()),
        "active_priority_counts": dict(active_priority_counts.most_common()),
        "last_ring_outcome_task_sync": {
            "created_at": now,
            "current_ring_task_count": len(ring_tasks),
            "reviewer": reviewer,
        },
        "tasks": sorted(
            out,
            key=lambda item: (
                item.get("lifecycle_state") != "active",
                {"open": 0, "planned": 1, "outcomes_imported": 2, "closed": 3, "resolved_by_calibration": 4, "retired": 5}.get(str(item.get("status")), 9),
                {"high": 0, "medium": 1, "low": 2}.get(str(item.get("priority")), 9),
                str(item.get("task_id") or ""),
            ),
        ),
    }


def _write_task_csv(rows: list[dict], csv_path: str | Path) -> None:
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    preferred = [
        "task_id",
        "priority",
        "recommended_action",
        "source_context_id",
        "endpoint_group",
        "assay_type",
        "observed_count",
        "additional_outcome_target",
        "expected_information_gain",
        "residual_sample_status",
        "enumeration_type",
        "ring_novelty_bucket",
        "ring_diversity_bucket",
        "replacement_class",
        "learning_action",
        "gate_reasons",
    ]
    extras = sorted({key for row in rows for key in row if key not in preferred})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=preferred + extras)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in preferred + extras})


def write_ring_outcome_residual_tasks(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_RING_OUTCOME_TASK_REPORT_PATH,
    csv_path: str | Path | None = DEFAULT_RING_OUTCOME_TASK_CSV_PATH,
) -> None:
    path = Path(json_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is not None:
        _write_task_csv(report.get("tasks") or [], csv_path)
