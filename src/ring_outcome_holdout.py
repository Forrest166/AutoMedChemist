from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_RING_OUTCOME_LEARNING_PATH = Path("data/projects/demo/ring_outcome_learning_report.json")
DEFAULT_RING_OUTCOME_OVERLAY_PATH = Path("data/profiles/calibrated/ring_outcome_scoring_overlay.json")
DEFAULT_RING_OUTCOME_REPLAY_PATH = Path("data/projects/demo/ring_outcome_overlay_replay.json")
DEFAULT_RING_OUTCOME_ACTIVATION_PATH = Path("data/profiles/calibrated/ring_outcome_overlay_activation.json")
DEFAULT_RING_OUTCOME_READINESS_PATH = Path("data/projects/demo/ring_outcome_production_readiness.json")
DEFAULT_RING_OUTCOME_HOLDOUT_PATH = Path("data/projects/demo/ring_outcome_holdout_report.json")
DEFAULT_RING_OUTCOME_HOLDOUT_CSV_PATH = Path("data/projects/demo/ring_outcome_holdout_report.csv")


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


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


def _endpoint(value: object) -> str:
    return str(value or "unspecified").strip().lower() or "unspecified"


def _max_abs(values: list[float]) -> float:
    return round(max([abs(value) for value in values] or [0.0]), 4)


def build_ring_outcome_holdout_report(
    *,
    learning_path: str | Path = DEFAULT_RING_OUTCOME_LEARNING_PATH,
    overlay_path: str | Path = DEFAULT_RING_OUTCOME_OVERLAY_PATH,
    replay_path: str | Path = DEFAULT_RING_OUTCOME_REPLAY_PATH,
    activation_path: str | Path = DEFAULT_RING_OUTCOME_ACTIVATION_PATH,
    readiness_path: str | Path = DEFAULT_RING_OUTCOME_READINESS_PATH,
    max_abs_rank_delta: int = 50,
    max_abs_score_delta: float = 5.0,
) -> dict:
    """Summarize endpoint-level ring overlay holdout readiness.

    This is a pre-activation safety report. It can be green while waiting for
    production results, but it only becomes holdout_ready after real active
    nonzero contexts exist and replay movement stays inside limits.
    """
    learning = _read_json(learning_path)
    overlay = _read_json(overlay_path)
    replay = _read_json(replay_path)
    activation = _read_json(activation_path)
    readiness = _read_json(readiness_path)

    contexts = {str(row.get("context_id") or ""): dict(row) for row in overlay.get("contexts") or [] if row.get("context_id")}
    endpoint_rows: dict[str, dict] = {}

    def endpoint_row(endpoint: object) -> dict:
        key = _endpoint(endpoint)
        return endpoint_rows.setdefault(
            key,
            {
                "endpoint": key,
                "learning_group_count": 0,
                "learning_observed_count": 0,
                "overlay_context_count": 0,
                "active_context_count": 0,
                "active_nonzero_context_count": 0,
                "blocked_context_count": 0,
                "replay_candidate_count": 0,
                "affected_candidate_count": 0,
                "proposed_affected_candidate_count": 0,
                "_active_score_deltas": [],
                "_proposed_score_deltas": [],
                "_active_rank_deltas": [],
                "_proposed_rank_deltas": [],
            },
        )

    for group in learning.get("learning_groups") or []:
        row = endpoint_row(group.get("endpoint"))
        row["learning_group_count"] += 1
        row["learning_observed_count"] += _int(group.get("observed_count"))

    for context in contexts.values():
        row = endpoint_row(context.get("endpoint"))
        row["overlay_context_count"] += 1
        if context.get("gate_status") == "active":
            row["active_context_count"] += 1
            if abs(_float(context.get("active_score_adjustment"))) > 0:
                row["active_nonzero_context_count"] += 1
        else:
            row["blocked_context_count"] += 1

    for replay_row in replay.get("rows") or []:
        context_id = str(replay_row.get("ring_outcome_context_id") or "")
        context = contexts.get(context_id, {})
        row = endpoint_row(context.get("endpoint") or "unspecified")
        row["replay_candidate_count"] += 1
        active_score_delta = _float(replay_row.get("score_delta_vs_current"))
        proposed_score_delta = _float(replay_row.get("proposed_score_delta_vs_current"))
        active_rank_delta = _int(replay_row.get("replay_rank_delta_vs_current"))
        proposed_rank_delta = _int(replay_row.get("proposed_rank_delta_vs_current"))
        row["_active_score_deltas"].append(active_score_delta)
        row["_proposed_score_deltas"].append(proposed_score_delta)
        row["_active_rank_deltas"].append(active_rank_delta)
        row["_proposed_rank_deltas"].append(proposed_rank_delta)
        if abs(active_score_delta) > 0 or active_rank_delta:
            row["affected_candidate_count"] += 1
        if abs(proposed_score_delta) > 0 or proposed_rank_delta:
            row["proposed_affected_candidate_count"] += 1

    rows = []
    for row in endpoint_rows.values():
        max_active_score = _max_abs(row.pop("_active_score_deltas"))
        max_proposed_score = _max_abs(row.pop("_proposed_score_deltas"))
        max_active_rank = max([abs(int(value)) for value in row.pop("_active_rank_deltas")] or [0])
        max_proposed_rank = max([abs(int(value)) for value in row.pop("_proposed_rank_deltas")] or [0])
        row.update(
            {
                "max_abs_active_score_delta": max_active_score,
                "max_abs_proposed_score_delta": max_proposed_score,
                "max_abs_active_rank_delta": max_active_rank,
                "max_abs_proposed_rank_delta": max_proposed_rank,
            }
        )
        if row["active_nonzero_context_count"] <= 0:
            row["holdout_status"] = "awaiting_active_nonzero_context"
        elif row["replay_candidate_count"] <= 0:
            row["holdout_status"] = "missing_replay_candidates"
        elif max_active_score > max_abs_score_delta or max_active_rank > max_abs_rank_delta:
            row["holdout_status"] = "rank_or_score_delta_review_required"
        else:
            row["holdout_status"] = "holdout_ready"
        rows.append(row)

    rows.sort(key=lambda row: (row["holdout_status"] != "holdout_ready", row["endpoint"]))
    active_nonzero = _int(activation.get("active_nonzero_context_count"))
    if readiness.get("status") == "awaiting_production_results":
        status = "awaiting_production_results"
    elif active_nonzero <= 0:
        status = "blocked_no_active_nonzero_context"
    elif any(row.get("holdout_status") in {"missing_replay_candidates", "rank_or_score_delta_review_required"} for row in rows):
        status = "holdout_review_required"
    else:
        status = "holdout_ready"

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "learning_status": learning.get("status") or "",
        "readiness_status": readiness.get("status") or "",
        "activation_status": activation.get("status") or "",
        "active_nonzero_context_count": active_nonzero,
        "replay_status": replay.get("status") or "",
        "max_abs_rank_delta_limit": max_abs_rank_delta,
        "max_abs_score_delta_limit": max_abs_score_delta,
        "endpoint_count": len(rows),
        "holdout_ready_endpoint_count": sum(1 for row in rows if row.get("holdout_status") == "holdout_ready"),
        "rows": rows,
        "recommended_next_actions": [
            "Import real production ring outcome results before expecting holdout_ready status.",
            "For every endpoint, require replay candidates and bounded score/rank movement before activating nonzero contexts.",
            "Keep endpoint-specific holdout rows visible in release smoke before broad overlay use.",
        ],
    }


def write_ring_outcome_holdout_report(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_RING_OUTCOME_HOLDOUT_PATH,
    csv_path: str | Path | None = DEFAULT_RING_OUTCOME_HOLDOUT_CSV_PATH,
) -> None:
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if not csv_path:
        return
    rows = [dict(row) for row in report.get("rows") or []]
    fields = [
        "endpoint",
        "holdout_status",
        "learning_group_count",
        "learning_observed_count",
        "overlay_context_count",
        "active_context_count",
        "active_nonzero_context_count",
        "blocked_context_count",
        "replay_candidate_count",
        "affected_candidate_count",
        "proposed_affected_candidate_count",
        "max_abs_active_score_delta",
        "max_abs_proposed_score_delta",
        "max_abs_active_rank_delta",
        "max_abs_proposed_rank_delta",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
