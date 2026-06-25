from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import yaml


DEFAULT_RING_OUTCOME_REPORT_PATH = Path("data/projects/demo/ring_outcome_learning_report.json")
DEFAULT_RING_OUTCOME_OVERLAY_PATH = Path("data/profiles/calibrated/ring_outcome_scoring_overlay.json")
DEFAULT_RING_OUTCOME_OVERLAY_CSV_PATH = Path("data/profiles/calibrated/ring_outcome_scoring_overlay.csv")
DEFAULT_RING_OUTCOME_REVIEW_PATH = Path("data/profiles/calibrated/ring_outcome_overlay_reviews.csv")
DEFAULT_RING_OUTCOME_MATURATION_POLICY_PATH = Path("data/profiles/ring_outcome_maturation_policy.yaml")
DEFAULT_RING_OUTCOME_ACTIVATION_PATH = Path("data/profiles/calibrated/ring_outcome_overlay_activation.json")
DEFAULT_RING_OUTCOME_ACTIVE_SNAPSHOT_PATH = Path("data/profiles/calibrated/ring_outcome_scoring_overlay_active.json")
APPROVED_REVIEW_DECISIONS = {"approved", "accepted", "accepted_with_review"}
REVIEW_DECISIONS = {"pending_review", "approved", "rejected", "deferred"}
RING_ENUMERATION_TYPES = {
    "ring_library_recommendation",
    "ring_rgroup_joint_recommendation",
    "ring_network_replacement",
    "scaffold_replacement",
}


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


def _norm(value: object) -> str:
    return str(value or "unspecified").strip() or "unspecified"


def ring_context_id(row: dict) -> str:
    parts = [
        _norm(row.get("enumeration_type")),
        _norm(row.get("endpoint")),
        _norm(row.get("ring_novelty_bucket")),
        _norm(row.get("ring_diversity_bucket")),
        _norm(row.get("replacement_class")),
    ]
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12].upper()
    return f"RINGCTX-{digest}"


def _wilson_interval(positive_count: int, observed_count: int, *, z: float = 1.96) -> tuple[float | None, float | None]:
    if observed_count <= 0:
        return None, None
    p = positive_count / observed_count
    denominator = 1 + z**2 / observed_count
    centre = p + z**2 / (2 * observed_count)
    margin = z * math.sqrt((p * (1 - p) + z**2 / (4 * observed_count)) / observed_count)
    return max(0.0, (centre - margin) / denominator), min(1.0, (centre + margin) / denominator)


def _load_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    return json.loads(source.read_text(encoding="utf-8"))


def load_ring_outcome_maturation_policy(path: str | Path | None = DEFAULT_RING_OUTCOME_MATURATION_POLICY_PATH) -> dict:
    if not path:
        return {}
    policy_path = Path(path)
    if not policy_path.exists():
        return {}
    payload = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def _endpoint_policy(policy: dict, endpoint: object, *, min_observed: int, promote_ci_low_threshold: float, downweight_ci_high_threshold: float, max_abs_adjustment: float) -> dict:
    defaults = dict(policy.get("defaults") or {}) if isinstance(policy, dict) else {}
    endpoint_map = dict(policy.get("endpoint_thresholds") or {}) if isinstance(policy, dict) else {}
    key = str(endpoint or "").strip().lower()
    endpoint_entry = dict(endpoint_map.get(key) or {}) if key else {}
    merged = {
        "min_observed": _int(defaults.get("min_observed"), min_observed),
        "promote_ci_low_threshold": _float(defaults.get("promote_ci_low_threshold"), promote_ci_low_threshold),
        "downweight_ci_high_threshold": _float(defaults.get("downweight_ci_high_threshold"), downweight_ci_high_threshold),
        "max_abs_adjustment": _float(defaults.get("max_abs_adjustment"), max_abs_adjustment),
    }
    for field in ["min_observed", "promote_ci_low_threshold", "downweight_ci_high_threshold", "max_abs_adjustment"]:
        if field in endpoint_entry and endpoint_entry.get(field) not in {None, ""}:
            merged[field] = _int(endpoint_entry[field]) if field == "min_observed" else _float(endpoint_entry[field], merged[field])
    merged["policy_endpoint"] = key or "default"
    return merged


def load_ring_outcome_overlay_reviews(path: str | Path = DEFAULT_RING_OUTCOME_REVIEW_PATH) -> dict[str, dict]:
    source = Path(path)
    if not source.exists():
        return {}
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    return {str(row.get("context_id") or "").strip(): row for row in rows if row.get("context_id")}


def _read_csv_rows(path: str | Path) -> list[dict]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_review_rows(rows: list[dict], path: str | Path) -> None:
    fields = [
        "context_id",
        "review_decision",
        "reviewer",
        "reviewed_at",
        "approved_score_adjustment",
        "review_note",
        "replay_status",
        "replay_candidate_count",
        "max_abs_proposed_score_delta",
        "max_abs_proposed_rank_delta",
    ]
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _replay_by_context(replay: dict) -> dict[str, dict]:
    grouped: dict[str, dict] = {}
    for row in replay.get("rows") or []:
        context_id = str(row.get("ring_outcome_context_id") or "").strip()
        if not context_id:
            continue
        current = grouped.setdefault(
            context_id,
            {
                "replay_candidate_count": 0,
                "max_abs_proposed_score_delta": 0.0,
                "max_abs_proposed_rank_delta": 0,
            },
        )
        current["replay_candidate_count"] += 1
        current["max_abs_proposed_score_delta"] = max(
            float(current["max_abs_proposed_score_delta"]),
            abs(_float(row.get("proposed_score_delta_vs_current"))),
        )
        current["max_abs_proposed_rank_delta"] = max(
            int(current["max_abs_proposed_rank_delta"]),
            abs(_int(row.get("proposed_rank_delta_vs_current"))),
        )
    return grouped


def build_ring_outcome_overlay_review_template(
    overlay: dict | str | Path,
    *,
    review_path: str | Path = DEFAULT_RING_OUTCOME_REVIEW_PATH,
    replay: dict | str | Path | None = None,
) -> dict:
    payload = _load_json(overlay) if isinstance(overlay, (str, Path)) else dict(overlay or {})
    replay_payload = _load_json(replay) if isinstance(replay, (str, Path)) else dict(replay or {}) if replay else {}
    replay_lookup = _replay_by_context(replay_payload)
    existing = load_ring_outcome_overlay_reviews(review_path)
    rows = []
    for context in payload.get("contexts") or []:
        context_id = str(context.get("context_id") or "").strip()
        if not context_id:
            continue
        previous = existing.get(context_id, {})
        replay_row = replay_lookup.get(context_id, {})
        rows.append(
            {
                "context_id": context_id,
                "review_decision": previous.get("review_decision") or "pending_review",
                "reviewer": previous.get("reviewer") or "",
                "reviewed_at": previous.get("reviewed_at") or "",
                "approved_score_adjustment": previous.get("approved_score_adjustment") or context.get("proposed_score_adjustment") or "",
                "review_note": previous.get("review_note") or previous.get("review_notes") or "",
                "replay_status": replay_payload.get("status") or "",
                "replay_candidate_count": replay_row.get("replay_candidate_count", 0),
                "max_abs_proposed_score_delta": replay_row.get("max_abs_proposed_score_delta", 0.0),
                "max_abs_proposed_rank_delta": replay_row.get("max_abs_proposed_rank_delta", 0),
                "gate_status": context.get("gate_status") or "",
                "gate_reasons": context.get("gate_reasons") or "",
                "endpoint": context.get("endpoint") or "",
                "learning_action": context.get("learning_action") or "",
                "observed_count": context.get("observed_count") or "",
                "policy_min_observed": context.get("policy_min_observed") or "",
            }
        )
    return {
        "status": "ready" if rows else "empty",
        "row_count": len(rows),
        "replay_status": replay_payload.get("status") or "",
        "review_path": str(review_path),
        "rows": rows,
    }


def write_ring_outcome_overlay_review_template(report: dict, path: str | Path = DEFAULT_RING_OUTCOME_REVIEW_PATH) -> None:
    _write_review_rows([dict(row) for row in report.get("rows") or []], path)


def update_ring_outcome_overlay_review(
    context_id: str,
    *,
    decision: str,
    reviewer: str,
    review_note: str = "",
    approved_score_adjustment: float | str | None = None,
    review_path: str | Path = DEFAULT_RING_OUTCOME_REVIEW_PATH,
    overlay: dict | str | Path | None = None,
    replay: dict | str | Path | None = None,
    require_replay: bool = True,
) -> dict:
    normalized_decision = str(decision or "").strip().lower()
    if normalized_decision not in REVIEW_DECISIONS:
        raise ValueError(f"Unsupported review decision: {decision}")
    if not reviewer:
        raise ValueError("reviewer is required")
    review_file = Path(review_path)
    rows = _read_csv_rows(review_file)
    if not rows and overlay is not None:
        template = build_ring_outcome_overlay_review_template(overlay, review_path=review_file, replay=replay)
        rows = [dict(row) for row in template.get("rows") or []]
    replay_payload = _load_json(replay) if isinstance(replay, (str, Path)) else dict(replay or {}) if replay else {}
    replay_lookup = _replay_by_context(replay_payload)
    if require_replay and normalized_decision == "approved":
        replay_row = replay_lookup.get(context_id)
        if not replay_payload or replay_row is None:
            raise ValueError("Replay evidence is required before approving a ring outcome overlay context.")
    updated = False
    for row in rows:
        if str(row.get("context_id") or "").strip() != context_id:
            continue
        row["review_decision"] = normalized_decision
        row["reviewer"] = reviewer
        row["reviewed_at"] = datetime.now(timezone.utc).isoformat()
        row["review_note"] = review_note
        if approved_score_adjustment not in {None, ""}:
            row["approved_score_adjustment"] = approved_score_adjustment
        if replay_payload:
            row["replay_status"] = replay_payload.get("status") or ""
            replay_row = replay_lookup.get(context_id, {})
            row["replay_candidate_count"] = replay_row.get("replay_candidate_count", 0)
            row["max_abs_proposed_score_delta"] = replay_row.get("max_abs_proposed_score_delta", 0.0)
            row["max_abs_proposed_rank_delta"] = replay_row.get("max_abs_proposed_rank_delta", 0)
        updated = True
        break
    if not updated:
        raise ValueError(f"context_id not found in review template: {context_id}")
    _write_review_rows(rows, review_file)
    return {
        "status": "updated",
        "context_id": context_id,
        "decision": normalized_decision,
        "review_path": str(review_file),
        "row_count": len(rows),
    }


def build_ring_outcome_scoring_overlay(
    report: dict | str | Path,
    *,
    review_path: str | Path | None = DEFAULT_RING_OUTCOME_REVIEW_PATH,
    policy_path: str | Path | None = None,
    min_observed: int = 3,
    require_approved_review: bool = True,
    promote_ci_low_threshold: float = 0.4,
    downweight_ci_high_threshold: float = 0.55,
    max_abs_adjustment: float = 4.0,
) -> dict:
    payload = _load_json(report) if isinstance(report, (str, Path)) else dict(report or {})
    reviews = load_ring_outcome_overlay_reviews(review_path) if review_path else {}
    policy = load_ring_outcome_maturation_policy(policy_path)
    contexts = []
    for group in payload.get("learning_groups") or []:
        action = str(group.get("learning_action") or "")
        observed_count = _int(group.get("observed_count"))
        positive_count = _int(group.get("positive_count"))
        hit_rate = group.get("hit_rate")
        hit_rate = _float(hit_rate, positive_count / observed_count if observed_count else 0.0)
        ci_low, ci_high = _wilson_interval(positive_count, observed_count)
        gate_policy = _endpoint_policy(
            policy,
            group.get("endpoint"),
            min_observed=min_observed,
            promote_ci_low_threshold=promote_ci_low_threshold,
            downweight_ci_high_threshold=downweight_ci_high_threshold,
            max_abs_adjustment=max_abs_adjustment,
        )
        context_max_adjustment = _float(gate_policy.get("max_abs_adjustment"), max_abs_adjustment)
        proposed = 0.0
        if action == "promote_context":
            proposed = min(context_max_adjustment, 1.0 + max(0.0, hit_rate - 0.6) * 8.0)
        elif action == "downweight_context":
            proposed = -min(context_max_adjustment, 1.0 + max(0.0, 0.35 - hit_rate) * 8.0)
        context = {
            "context_id": ring_context_id(group),
            "enumeration_type": group.get("enumeration_type"),
            "endpoint": group.get("endpoint"),
            "ring_novelty_bucket": group.get("ring_novelty_bucket"),
            "ring_diversity_bucket": group.get("ring_diversity_bucket"),
            "replacement_class": group.get("replacement_class"),
            "learning_action": action,
            "candidate_count": group.get("candidate_count"),
            "observed_count": observed_count,
            "positive_count": positive_count,
            "negative_count": group.get("negative_count"),
            "neutral_count": group.get("neutral_count"),
            "hit_rate": round(hit_rate, 4) if observed_count else None,
            "hit_rate_ci_low": round(ci_low, 4) if ci_low is not None else None,
            "hit_rate_ci_high": round(ci_high, 4) if ci_high is not None else None,
            "proposed_score_adjustment": round(proposed, 4),
            "policy_endpoint": gate_policy.get("policy_endpoint"),
            "policy_min_observed": gate_policy.get("min_observed"),
            "policy_promote_ci_low_threshold": gate_policy.get("promote_ci_low_threshold"),
            "policy_downweight_ci_high_threshold": gate_policy.get("downweight_ci_high_threshold"),
            "policy_max_abs_adjustment": gate_policy.get("max_abs_adjustment"),
        }
        review = reviews.get(context["context_id"], {})
        review_decision = str(review.get("review_decision") or "").strip().lower()
        approved_adjustment = review.get("approved_score_adjustment")
        if approved_adjustment not in {None, ""}:
            context["approved_score_adjustment"] = round(
                max(-context_max_adjustment, min(context_max_adjustment, _float(approved_adjustment))),
                4,
            )
        else:
            context["approved_score_adjustment"] = context["proposed_score_adjustment"]
        gate_reasons = []
        if observed_count < int(gate_policy.get("min_observed") or min_observed):
            gate_reasons.append("below_min_observed")
        if action == "promote_context" and (ci_low is None or ci_low < _float(gate_policy.get("promote_ci_low_threshold"), promote_ci_low_threshold)):
            gate_reasons.append("promote_ci_low_below_threshold")
        if action == "downweight_context" and (ci_high is None or ci_high > _float(gate_policy.get("downweight_ci_high_threshold"), downweight_ci_high_threshold)):
            gate_reasons.append("downweight_ci_high_above_threshold")
        if action not in {"promote_context", "downweight_context"}:
            gate_reasons.append("not_actionable_learning_action")
        if require_approved_review and review_decision not in APPROVED_REVIEW_DECISIONS:
            gate_reasons.append("missing_approved_review")
        context.update(
            {
                "review_decision": review_decision,
                "reviewer": review.get("reviewer") or "",
                "reviewed_at": review.get("reviewed_at") or "",
                "review_note": review.get("review_note") or review.get("review_notes") or "",
                "gate_status": "active" if not gate_reasons else "blocked",
                "gate_reasons": ";".join(gate_reasons),
                "active_score_adjustment": context["approved_score_adjustment"] if not gate_reasons else 0.0,
            }
        )
        contexts.append(context)
    contexts.sort(key=lambda row: (row["gate_status"] != "active", row["learning_action"], -_int(row.get("observed_count"))))
    return {
        "source_report_status": payload.get("status"),
        "source_report_created_at": payload.get("created_at"),
        "maturation_policy_version": policy.get("version") if policy else "",
        "maturation_policy_path": str(policy_path) if policy_path else "",
        "min_observed": min_observed,
        "require_approved_review": require_approved_review,
        "promote_ci_low_threshold": promote_ci_low_threshold,
        "downweight_ci_high_threshold": downweight_ci_high_threshold,
        "context_count": len(contexts),
        "active_context_count": sum(1 for row in contexts if row.get("gate_status") == "active"),
        "blocked_context_count": sum(1 for row in contexts if row.get("gate_status") != "active"),
        "contexts": contexts,
    }


def write_ring_outcome_scoring_overlay(
    overlay: dict,
    *,
    json_path: str | Path = DEFAULT_RING_OUTCOME_OVERLAY_PATH,
    csv_path: str | Path | None = DEFAULT_RING_OUTCOME_OVERLAY_CSV_PATH,
) -> None:
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(overlay, indent=2, sort_keys=True), encoding="utf-8")
    if not csv_path:
        return
    rows = overlay.get("contexts") or []
    fields = [
        "context_id",
        "enumeration_type",
        "endpoint",
        "ring_novelty_bucket",
        "ring_diversity_bucket",
        "replacement_class",
        "learning_action",
        "candidate_count",
        "observed_count",
        "positive_count",
        "negative_count",
        "neutral_count",
        "hit_rate",
        "hit_rate_ci_low",
        "hit_rate_ci_high",
        "proposed_score_adjustment",
        "policy_endpoint",
        "policy_min_observed",
        "policy_promote_ci_low_threshold",
        "policy_downweight_ci_high_threshold",
        "policy_max_abs_adjustment",
        "approved_score_adjustment",
        "active_score_adjustment",
        "gate_status",
        "gate_reasons",
        "review_decision",
        "reviewer",
        "reviewed_at",
        "review_note",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_ring_outcome_overlay_activation_report(
    overlay: dict | str | Path,
    *,
    replay: dict | str | Path | None = None,
    review_path: str | Path = DEFAULT_RING_OUTCOME_REVIEW_PATH,
    max_abs_score_delta: float = 5.0,
    max_abs_rank_delta: int = 50,
) -> dict:
    payload = _load_json(overlay) if isinstance(overlay, (str, Path)) else dict(overlay or {})
    replay_payload = _load_json(replay) if isinstance(replay, (str, Path)) else dict(replay or {}) if replay else {}
    replay_lookup = _replay_by_context(replay_payload)
    reviews = load_ring_outcome_overlay_reviews(review_path)
    active_contexts = [
        dict(row)
        for row in payload.get("contexts") or []
        if row.get("gate_status") == "active" and abs(_float(row.get("active_score_adjustment"))) > 0
    ]
    rows = []
    blockers = []
    for context in active_contexts:
        context_id = str(context.get("context_id") or "")
        review = reviews.get(context_id, {})
        replay_row = replay_lookup.get(context_id, {})
        row_blockers = []
        if str(review.get("review_decision") or "").lower() not in APPROVED_REVIEW_DECISIONS:
            row_blockers.append("missing_approved_review")
        if not replay_row:
            row_blockers.append("missing_replay_context")
        if _float(replay_row.get("max_abs_proposed_score_delta")) > max_abs_score_delta:
            row_blockers.append("score_delta_above_activation_limit")
        if _int(replay_row.get("max_abs_proposed_rank_delta")) > max_abs_rank_delta:
            row_blockers.append("rank_delta_above_activation_limit")
        rows.append(
            {
                "context_id": context_id,
                "endpoint": context.get("endpoint"),
                "learning_action": context.get("learning_action"),
                "active_score_adjustment": context.get("active_score_adjustment"),
                "review_decision": review.get("review_decision") or context.get("review_decision") or "",
                "reviewer": review.get("reviewer") or context.get("reviewer") or "",
                "replay_candidate_count": replay_row.get("replay_candidate_count", 0),
                "max_abs_proposed_score_delta": replay_row.get("max_abs_proposed_score_delta", 0.0),
                "max_abs_proposed_rank_delta": replay_row.get("max_abs_proposed_rank_delta", 0),
                "activation_status": "ready" if not row_blockers else "blocked",
                "activation_blockers": ";".join(row_blockers),
            }
        )
        blockers.extend(row_blockers)
    if not active_contexts:
        blockers.append("no_active_nonzero_context")
    status = "activated" if active_contexts and not blockers else "blocked_no_active_nonzero_context" if blockers == ["no_active_nonzero_context"] else "blocked"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "overlay_context_count": payload.get("context_count", 0),
        "active_context_count": len(active_contexts),
        "active_nonzero_context_count": len(active_contexts),
        "blockers": sorted(set(blockers)),
        "replay_status": replay_payload.get("status") or "",
        "max_abs_score_delta_limit": max_abs_score_delta,
        "max_abs_rank_delta_limit": max_abs_rank_delta,
        "rows": rows,
        "recommended_next_actions": [
            "Import real completed ring outcome results before expecting nonzero active contexts.",
            "Approve only contexts with replay rows and acceptable score/rank movement.",
            "Rebuild candidate queues after activation so active ring outcome adjustments are persisted.",
        ],
    }


def write_ring_outcome_overlay_activation_report(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_RING_OUTCOME_ACTIVATION_PATH,
    active_snapshot_path: str | Path | None = DEFAULT_RING_OUTCOME_ACTIVE_SNAPSHOT_PATH,
) -> None:
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if active_snapshot_path and report.get("status") == "activated":
        snapshot = {
            "created_at": report.get("created_at"),
            "status": "active",
            "active_context_count": report.get("active_context_count", 0),
            "contexts": report.get("rows") or [],
        }
        snapshot_out = Path(active_snapshot_path)
        snapshot_out.parent.mkdir(parents=True, exist_ok=True)
        snapshot_out.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def _candidate_context(row: dict, target_context: dict | None = None) -> dict:
    target_context = target_context or {}
    return {
        "enumeration_type": row.get("enumeration_type"),
        "endpoint": row.get("endpoint") or target_context.get("endpoint_group") or target_context.get("endpoint") or row.get("direction"),
        "ring_novelty_bucket": row.get("ring_novelty_bucket") or "unspecified",
        "ring_diversity_bucket": row.get("ring_diversity_bucket") or row.get("diversity_bucket") or "unspecified",
        "replacement_class": row.get("replacement_class") or "unspecified",
    }


def annotate_ring_outcome_learning_overlay(
    rows: list[dict],
    *,
    report_path: str | Path = DEFAULT_RING_OUTCOME_REPORT_PATH,
    review_path: str | Path | None = DEFAULT_RING_OUTCOME_REVIEW_PATH,
    policy_path: str | Path | None = None,
    target_context: dict | None = None,
    min_observed: int = 3,
    require_approved_review: bool = True,
) -> list[dict]:
    if not Path(report_path).exists():
        return rows
    overlay = build_ring_outcome_scoring_overlay(
        report_path,
        review_path=review_path,
        policy_path=policy_path,
        min_observed=min_observed,
        require_approved_review=require_approved_review,
    )
    contexts = {row["context_id"]: row for row in overlay.get("contexts") or []}
    out = []
    for row in rows:
        item = dict(row)
        if item.get("enumeration_type") not in RING_ENUMERATION_TYPES:
            out.append(item)
            continue
        context_id = ring_context_id(_candidate_context(item, target_context))
        context = contexts.get(context_id)
        item["ring_outcome_learning_context_id"] = context_id
        if not context:
            item["ring_outcome_learning_gate_status"] = "no_context"
            item["ring_outcome_learning_score_adjustment"] = 0.0
            out.append(item)
            continue
        item["ring_outcome_learning_action"] = context.get("learning_action")
        item["ring_outcome_learning_gate_status"] = context.get("gate_status")
        item["ring_outcome_learning_gate_reasons"] = context.get("gate_reasons")
        item["ring_outcome_learning_hit_rate"] = context.get("hit_rate")
        item["ring_outcome_learning_observed_count"] = context.get("observed_count")
        item["ring_outcome_learning_review_decision"] = context.get("review_decision")
        item["ring_outcome_learning_proposed_score_adjustment"] = context.get("proposed_score_adjustment")
        item["ring_outcome_learning_score_adjustment"] = context.get("active_score_adjustment") or 0.0
        out.append(item)
    return out
