from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .database import initialize_database


QUEUE_DECISION_STATUSES = {"accepted", "deferred", "retired", "needs_review"}
QUEUE_DECISION_TEMPLATE_FIELDS = [
    "queue_id",
    "project_name",
    "run_id",
    "candidate_id",
    "endpoint_group",
    "queue_decision",
    "owner",
    "review_note",
    "reviewed_at",
]
DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")


def _float_or_none(value: object) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _action_for_row(row: dict) -> str:
    status = str(row.get("status") or "")
    after = float(row.get("priority_score_after") or 0)
    delta = float(row.get("priority_score_delta") or 0)
    if status in {"resolved_or_removed", "priority_down"} or delta <= -2:
        return "deprioritize_or_defer"
    if row.get("feedback_rows"):
        return "review_feedback_followup"
    if after >= 4 or status in {"new_priority", "priority_up"}:
        return "measure_next_batch"
    return "review_context"


def _stable_decision_key(row: dict) -> str:
    parts = [
        str(row.get("project_name") or ""),
        str(row.get("run_id") or ""),
        str(row.get("candidate_id") or ""),
        str(row.get("endpoint_group") or ""),
    ]
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:10].upper()
    return f"NDQKEY-{digest}"


def _packet_candidates(packet: dict) -> list[dict]:
    if isinstance(packet.get("packet"), dict):
        packet = packet["packet"]
    return [dict(row) for row in packet.get("candidates") or [] if isinstance(row, dict)]


def _packet_uncertainty(row: dict) -> dict:
    status = str(row.get("evidence_confidence_status") or "").strip().lower()
    residual = _float_or_none(row.get("evidence_confidence_max_abs_residual"))
    recommendation = str(row.get("decision_recommendation") or "").strip().lower()
    score = 0.0
    basis = []
    if status in {"no_evidence_sources", "uncalibrated"}:
        score += 3.0
        basis.append(f"evidence_status={status or 'unknown'}")
    elif status in {"provisional", "collect_more_outcomes"}:
        score += 2.0
        basis.append(f"evidence_status={status}")
    elif not status:
        score += 1.0
        basis.append("evidence_status=missing")
    if residual is not None:
        if residual >= 0.3:
            score += 3.0
        elif residual >= 0.15:
            score += 2.0
        elif residual >= 0.08:
            score += 1.0
        if residual >= 0.08:
            basis.append(f"max_abs_residual={residual:.3f}")
    if recommendation == "make" and score >= 2.0:
        score += 1.0
        basis.append("make_candidate_with_uncertain_evidence")
    if str(row.get("evidence_conflict_flags") or "").strip():
        score += 0.5
        basis.append("packet_conflict_flags_present")
    return {
        "decision_packet_uncertainty_score": round(score, 4),
        "decision_packet_evidence_status": status or "",
        "decision_packet_max_abs_residual": residual,
        "decision_packet_recommendation": recommendation or "",
        "decision_packet_uncertainty_basis": "; ".join(basis),
    }


def _packet_uncertainty_by_candidate(decision_packets: list[dict] | tuple[dict, ...] | dict | None) -> dict[str, dict]:
    if not decision_packets:
        return {}
    packets = list(decision_packets) if isinstance(decision_packets, (list, tuple)) else [decision_packets]
    lookup: dict[str, dict] = {}
    for packet in packets:
        if not isinstance(packet, dict):
            continue
        for row in _packet_candidates(packet):
            candidate_id = str(row.get("candidate_id") or "")
            if not candidate_id:
                continue
            uncertainty = _packet_uncertainty(row)
            current = lookup.get(candidate_id)
            if current is None or float(uncertainty.get("decision_packet_uncertainty_score") or 0.0) > float(
                current.get("decision_packet_uncertainty_score") or 0.0
            ):
                lookup[candidate_id] = uncertainty
    return lookup


def _analog_series_lookup(report: dict | None) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for series in (report or {}).get("series") or []:
        if series.get("series_key"):
            lookup[f"series:{series['series_key']}"] = series
        for example in series.get("example_candidates") or []:
            candidate_id = str(example.get("candidate_id") or "")
            if candidate_id and candidate_id not in lookup:
                lookup[candidate_id] = series
    return lookup


def _analog_series_for_candidate(row: dict, report: dict | None) -> dict:
    lookup = _analog_series_lookup(report)
    candidate_id = str(row.get("candidate_id") or "")
    series = lookup.get(candidate_id)
    if not series:
        series_key = "|".join(
            [
                str(row.get("site_type") or "unspecified"),
                str(row.get("enumeration_type") or "unspecified"),
                str(row.get("diversity_bucket") or row.get("replacement_label") or "unspecified"),
            ]
        )
        series = lookup.get(f"series:{series_key}")
    residual = _float_or_none((series or {}).get("max_evidence_confidence_abs_residual"))
    residual_score = 0.0
    if residual is not None:
        if residual >= 0.3:
            residual_score = 3.0
        elif residual >= 0.15:
            residual_score = 2.0
        elif residual >= 0.08:
            residual_score = 1.0
    return {
        "analog_series_key": (series or {}).get("series_key", ""),
        "analog_series_recommendation": (series or {}).get("series_recommendation", ""),
        "analog_series_primary_endpoint": (series or {}).get("primary_endpoint_group", ""),
        "analog_series_endpoint_go_score": (series or {}).get("endpoint_learned_go_score"),
        "analog_series_endpoint_stop_score": (series or {}).get("endpoint_learned_stop_score"),
        "analog_series_endpoint_learning_basis": (series or {}).get("endpoint_learning_basis", ""),
        "analog_series_max_abs_residual": residual,
        "analog_series_high_residual_candidate_count": (series or {}).get("high_residual_candidate_count", 0),
        "analog_series_residual_score": round(residual_score, 4),
    }


def _queue_delta_lookup(report: dict | None) -> dict[str, dict]:
    return {
        str(item.get("series_key") or ""): item
        for item in (report or {}).get("series") or []
        if item.get("series_key")
    }


def _queue_delta_for_candidate(row: dict, report: dict | None) -> dict:
    lookup = _queue_delta_lookup(report)
    endpoint = str(row.get("endpoint_group") or "project_panel")
    keys = [
        "|".join([endpoint, str(row.get("enumeration_type") or "unspecified"), str(row.get("replacement_label") or "unspecified")]),
        "|".join(["project_panel", str(row.get("enumeration_type") or "unspecified"), str(row.get("replacement_label") or "unspecified")]),
    ]
    series = next((lookup[key] for key in keys if key in lookup), None)
    if not series:
        return {
            "queue_analog_series_delta_key": "",
            "queue_analog_series_delta_action": "no_series_delta_match",
            "queue_analog_series_delta_score_adjustment": 0.0,
            "queue_analog_series_delta_basis": "",
            "queue_analog_series_delta_max_abs_residual": None,
        }
    action = str(series.get("series_delta_action") or "")
    adjustment = {
        "expand_or_measure_series": 1.5,
        "measure_representatives": 1.0,
        "review_feedback_driven_shift": 0.5,
        "watch_series": 0.0,
        "deprioritize_series": -2.0,
    }.get(action, 0.0)
    residual = _float_or_none(series.get("max_evidence_confidence_abs_residual"))
    if residual is not None and residual >= 0.15:
        adjustment += 0.75
    return {
        "queue_analog_series_delta_key": series.get("series_key"),
        "queue_analog_series_delta_action": action,
        "queue_analog_series_delta_score_adjustment": round(adjustment, 4),
        "queue_analog_series_delta_basis": (
            f"{action}; mean_priority_delta={series.get('mean_priority_delta')}; "
            f"max_residual={series.get('max_evidence_confidence_abs_residual')}"
        ),
        "queue_analog_series_delta_max_abs_residual": residual,
    }


def load_next_design_queue_decisions(path: str | Path | None) -> list[dict]:
    if path is None:
        return []
    decision_path = Path(path)
    if not decision_path.exists():
        return []
    if decision_path.suffix.lower() == ".json":
        data = json.loads(decision_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [dict(row) for row in data if isinstance(row, dict)]
        return [dict(row) for row in data.get("decisions") or data.get("queue") or [] if isinstance(row, dict)]
    with decision_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _decision_event_id(row: dict) -> str:
    parts = [
        str(row.get("queue_decision_key") or ""),
        str(row.get("queue_id") or ""),
        str(row.get("project_name") or ""),
        str(row.get("run_id") or ""),
        str(row.get("candidate_id") or ""),
        str(row.get("endpoint_group") or ""),
        str(row.get("queue_decision") or row.get("decision") or ""),
        str(row.get("reviewed_at") or ""),
        str(row.get("owner") or row.get("reviewer") or ""),
    ]
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:14].upper()
    return f"NDQEVT-{digest}"


def _normalize_queue_decision_row(row: dict, *, source_path: str | None = None) -> dict:
    status = str(row.get("queue_decision") or row.get("decision") or "").strip().lower() or "needs_review"
    if status not in QUEUE_DECISION_STATUSES:
        status = "needs_review"
    normalized = {
        "queue_decision_key": row.get("queue_decision_key") or _stable_decision_key(row),
        "queue_id": row.get("queue_id") or "",
        "project_name": row.get("project_name") or "",
        "run_id": row.get("run_id") or "",
        "candidate_id": row.get("candidate_id") or "",
        "endpoint_group": row.get("endpoint_group") or "project_panel",
        "queue_decision": status,
        "owner": row.get("owner") or row.get("reviewer") or "",
        "review_note": row.get("review_note") or row.get("note") or "",
        "reviewed_at": row.get("reviewed_at") or "",
        "source_path": source_path or row.get("source_path") or "",
    }
    normalized["event_id"] = row.get("event_id") or _decision_event_id(normalized)
    return normalized


def save_next_design_queue_decisions(
    decisions: list[dict] | tuple[dict, ...],
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    source_path: str | Path | None = None,
) -> dict:
    rows = [
        _normalize_queue_decision_row(row, source_path=str(source_path) if source_path else None)
        for row in decisions
        if row.get("candidate_id") and str(row.get("queue_decision") or row.get("decision") or "").strip().lower() in QUEUE_DECISION_STATUSES
    ]
    conn = initialize_database(db_path)
    try:
        for row in rows:
            conn.execute(
                """
                INSERT OR REPLACE INTO next_design_queue_decision_event (
                    event_id, queue_decision_key, queue_id, project_name, run_id, candidate_id,
                    endpoint_group, queue_decision, owner, review_note, reviewed_at,
                    source_path, created_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["event_id"],
                    row["queue_decision_key"],
                    row["queue_id"],
                    row["project_name"],
                    row["run_id"],
                    row["candidate_id"],
                    row["endpoint_group"],
                    row["queue_decision"],
                    row["owner"],
                    row["review_note"],
                    row["reviewed_at"],
                    row["source_path"],
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps(row, sort_keys=True),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return {"saved_count": len(rows), "decision_counts": dict(Counter(row["queue_decision"] for row in rows).most_common())}


def list_next_design_queue_decision_events(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    limit: int = 500,
) -> list[dict]:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if project_name:
            rows = conn.execute(
                """
                SELECT * FROM next_design_queue_decision_event
                WHERE project_name=?
                ORDER BY COALESCE(reviewed_at, created_at) DESC, created_at DESC
                LIMIT ?
                """,
                (project_name, int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM next_design_queue_decision_event
                ORDER BY COALESCE(reviewed_at, created_at) DESC, created_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def load_next_design_queue_decisions_from_db(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    limit: int = 500,
) -> list[dict]:
    return [
        {
            "queue_decision_key": row.get("queue_decision_key"),
            "queue_id": row.get("queue_id"),
            "project_name": row.get("project_name"),
            "run_id": row.get("run_id"),
            "candidate_id": row.get("candidate_id"),
            "endpoint_group": row.get("endpoint_group"),
            "queue_decision": row.get("queue_decision"),
            "owner": row.get("owner"),
            "review_note": row.get("review_note"),
            "reviewed_at": row.get("reviewed_at"),
        }
        for row in list_next_design_queue_decision_events(db_path=db_path, project_name=project_name, limit=limit)
    ]


def build_bulk_next_design_queue_decisions(
    queue_rows: list[dict] | tuple[dict, ...],
    decision: str,
    *,
    owner: str = "",
    review_note: str = "",
    endpoint_group: str | None = None,
    recommendation_action: str | None = None,
    max_rows: int | None = None,
) -> list[dict]:
    """Create reviewer-decision rows from a queue slice with optional filters."""
    status = str(decision or "").strip().lower()
    if status not in QUEUE_DECISION_STATUSES:
        raise ValueError(f"Unsupported queue decision: {decision}")
    now = datetime.now(timezone.utc).isoformat()
    out = []
    for row in queue_rows:
        if endpoint_group and str(row.get("endpoint_group") or "") != endpoint_group:
            continue
        if recommendation_action and str(row.get("recommendation_action") or "") != recommendation_action:
            continue
        candidate_id = str(row.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        item = {
            "queue_decision_key": row.get("queue_decision_key") or _stable_decision_key(row),
            "queue_id": row.get("queue_id") or "",
            "project_name": row.get("project_name") or "",
            "run_id": row.get("run_id") or "",
            "candidate_id": candidate_id,
            "endpoint_group": row.get("endpoint_group") or "project_panel",
            "queue_decision": status,
            "owner": owner or "bulk-review",
            "review_note": review_note
            or (
                f"Bulk {status} decision"
                + (f" for endpoint={endpoint_group}" if endpoint_group else "")
                + (f" action={recommendation_action}" if recommendation_action else "")
            ),
            "reviewed_at": now,
        }
        out.append(item)
        if max_rows is not None and len(out) >= int(max_rows):
            break
    return out


def _outcome_bucket(row: dict) -> str:
    stop_go = str(row.get("stop_go_decision") or "").strip().lower().replace(" ", "_")
    if stop_go in {"go", "positive"}:
        return "positive"
    if stop_go in {"stop", "negative"}:
        return "negative"
    if stop_go == "retest":
        return "retest"
    classification = str(row.get("classification") or "").strip().lower().replace(" ", "_")
    if classification in {"active", "pass", "positive", "improved", "go", "hit"}:
        return "positive"
    if classification in {"inactive", "fail", "failed", "negative", "worse", "stop"}:
        return "negative"
    score = _float_or_none(row.get("normalized_score"))
    if score is not None:
        if score >= 70:
            return "positive"
        if score <= 35:
            return "negative"
    return "watch"


def build_next_design_queue_reviewer_calibration_hints(report: dict) -> list[dict]:
    """Generate reviewer calibration hints from queue decisions with observed outcomes."""
    hints = []

    def add_hint(
        row: dict,
        *,
        scope: str,
        label_name: str | None = None,
        hint_type: str,
        severity: str,
        message: str,
        extra_fields: tuple[str, ...] = (),
    ) -> None:
        item = {
            "hint_type": hint_type,
            "severity": severity,
            "scope": scope,
            "queue_decision": row.get("queue_decision"),
            "decision_count": row.get("decision_count"),
            "observed_count": row.get("observed_count"),
            "positive_count": row.get("positive_count"),
            "negative_count": row.get("negative_count"),
            "hit_rate": row.get("hit_rate"),
            "negative_rate": row.get("negative_rate"),
            "message": message,
        }
        if label_name:
            item[label_name] = row.get(label_name)
        for field in extra_fields:
            item[field] = row.get(field)
        hints.append(item)

    for row in report.get("by_decision_and_endpoint") or []:
        decision = str(row.get("queue_decision") or "")
        observed = int(row.get("observed_count") or 0)
        positive = int(row.get("positive_count") or 0)
        negative = int(row.get("negative_count") or 0)
        hit_rate = _float_or_none(row.get("hit_rate"))
        negative_rate = _float_or_none(row.get("negative_rate"))
        if decision == "accepted" and observed >= 3 and hit_rate is not None and hit_rate < 0.5:
            add_hint(
                row,
                scope="endpoint",
                label_name="endpoint_group",
                hint_type="tighten_acceptance_threshold",
                severity="high",
                message="Accepted rows are producing fewer than half positive outcomes for this endpoint.",
            )
        if decision in {"deferred", "retired"} and positive > 0:
            add_hint(
                row,
                scope="endpoint",
                label_name="endpoint_group",
                hint_type="review_missed_positive",
                severity="medium",
                message="Deferred or retired rows include positive outcomes; review missed opportunity patterns.",
            )
        if decision == "needs_review" and observed >= 3:
            add_hint(
                row,
                scope="endpoint",
                label_name="endpoint_group",
                hint_type="resolve_needs_review_backlog",
                severity="medium",
                message="Needs-review rows already have outcomes; convert them into accepted/deferred/retired labels.",
            )
        if decision in {"accepted", "needs_review"} and observed >= 3 and negative_rate is not None and negative_rate >= 0.5:
            add_hint(
                row,
                scope="endpoint",
                label_name="endpoint_group",
                hint_type="tighten_or_retire_rule",
                severity="medium" if negative > positive else "high",
                message="This decision bucket is accumulating negative outcomes and should be rechecked.",
            )

    for row in report.get("by_decision_and_owner") or []:
        decision = str(row.get("queue_decision") or "")
        observed = int(row.get("observed_count") or 0)
        hit_rate = _float_or_none(row.get("hit_rate"))
        if decision == "accepted" and observed >= 3 and hit_rate is not None and hit_rate < 0.5:
            add_hint(
                row,
                scope="owner",
                label_name="owner",
                hint_type="review_owner_acceptance_calibration",
                severity="medium",
                message="Owner accepted rows have a low observed hit rate; review examples before next batch.",
            )

    for row in report.get("by_decision_project_owner") or []:
        decision = str(row.get("queue_decision") or "")
        observed = int(row.get("observed_count") or 0)
        positive = int(row.get("positive_count") or 0)
        hit_rate = _float_or_none(row.get("hit_rate"))
        if decision == "accepted" and observed >= 3 and hit_rate is not None and hit_rate < 0.5:
            add_hint(
                row,
                scope="project_owner",
                extra_fields=("project_name", "owner"),
                hint_type="review_project_owner_acceptance_calibration",
                severity="high",
                message="This project/reviewer accepted bucket is underperforming; inspect accepted examples before the next decision batch.",
            )
        if decision in {"deferred", "retired"} and positive > 0:
            add_hint(
                row,
                scope="project_owner",
                extra_fields=("project_name", "owner"),
                hint_type="review_project_owner_missed_positive",
                severity="medium",
                message="This project/reviewer deferred or retired bucket contains positives; review missed opportunity criteria.",
            )

    for row in report.get("by_decision_owner_endpoint") or []:
        decision = str(row.get("queue_decision") or "")
        observed = int(row.get("observed_count") or 0)
        hit_rate = _float_or_none(row.get("hit_rate"))
        negative_rate = _float_or_none(row.get("negative_rate"))
        if decision == "accepted" and observed >= 3 and hit_rate is not None and hit_rate < 0.5:
            add_hint(
                row,
                scope="owner_endpoint",
                extra_fields=("owner", "endpoint_group"),
                hint_type="review_owner_endpoint_acceptance_calibration",
                severity="high",
                message="This reviewer/endpoint accepted bucket has low observed hit rate; tighten or split the decision rule.",
            )
        if decision == "needs_review" and observed >= 3:
            add_hint(
                row,
                scope="owner_endpoint",
                extra_fields=("owner", "endpoint_group"),
                hint_type="resolve_owner_endpoint_needs_review_backlog",
                severity="medium",
                message="This reviewer/endpoint needs-review bucket already has outcomes; convert it into training labels.",
            )
        if decision in {"accepted", "needs_review"} and observed >= 3 and negative_rate is not None and negative_rate >= 0.5:
            add_hint(
                row,
                scope="owner_endpoint",
                extra_fields=("owner", "endpoint_group"),
                hint_type="tighten_owner_endpoint_negative_bucket",
                severity="medium",
                message="This reviewer/endpoint bucket is accumulating negative outcomes and should be recalibrated.",
            )

    severity_order = {"high": 0, "medium": 1, "low": 2}
    hints.sort(
        key=lambda row: (
            severity_order.get(str(row.get("severity") or ""), 9),
            str(row.get("scope") or ""),
            str(row.get("queue_decision") or ""),
        )
    )
    return hints


def build_next_design_queue_decision_quality_report(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    limit: int = 1000,
) -> dict:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        where = "WHERE (? IS NULL OR d.project_name=?)"
        decisions = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT * FROM next_design_queue_decision_event d
                {where}
                ORDER BY COALESCE(d.reviewed_at, d.created_at) DESC, d.created_at DESC
                LIMIT ?
                """,
                (project_name, project_name, int(limit)),
            ).fetchall()
        ]
        observations = [
            dict(row)
            for row in conn.execute(
                """
                SELECT f.feedback_id AS observation_id, 'feedback' AS observation_type,
                       f.run_id, f.candidate_id, COALESCE(f.project_name, pr.project_name, '') AS project_name,
                       f.endpoint AS endpoint_group, f.assay_name, f.assay_type,
                       f.normalized_score, f.classification, NULL AS stop_go_decision, f.recorded_at
                FROM project_feedback f
                LEFT JOIN project_run pr ON pr.run_id=f.run_id
                WHERE (? IS NULL OR COALESCE(f.project_name, pr.project_name, '')=?)
                UNION ALL
                SELECT e.event_id AS observation_id, 'experiment_event' AS observation_type,
                       e.run_id, e.candidate_id, COALESCE(p.project_name, pr.project_name, '') AS project_name,
                       e.endpoint_group, e.assay_name, e.assay_type,
                       e.normalized_score, e.classification, e.stop_go_decision, e.recorded_at
                FROM project_experiment_event e
                LEFT JOIN project_experiment_plan p ON p.plan_id=e.plan_id
                LEFT JOIN project_run pr ON pr.run_id=e.run_id
                WHERE (? IS NULL OR COALESCE(p.project_name, pr.project_name, '')=?)
                """,
                (project_name, project_name, project_name, project_name),
            ).fetchall()
        ]
    finally:
        conn.close()

    by_candidate: dict[str, list[dict]] = defaultdict(list)
    by_run_candidate: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for observation in observations:
        candidate_id = str(observation.get("candidate_id") or "")
        if not candidate_id:
            continue
        by_candidate[candidate_id].append(observation)
        by_run_candidate[(str(observation.get("run_id") or ""), candidate_id)].append(observation)

    outcomes = []
    grouped: dict[tuple[str, str], Counter] = defaultdict(Counter)
    owner_grouped: dict[tuple[str, str], Counter] = defaultdict(Counter)
    project_owner_grouped: dict[tuple[str, str, str], Counter] = defaultdict(Counter)
    owner_endpoint_grouped: dict[tuple[str, str, str], Counter] = defaultdict(Counter)
    for decision in decisions:
        candidate_id = str(decision.get("candidate_id") or "")
        run_id = str(decision.get("run_id") or "")
        rows = by_run_candidate.get((run_id, candidate_id)) or by_candidate.get(candidate_id, [])
        buckets = Counter(_outcome_bucket(row) for row in rows)
        scores = [value for value in (_float_or_none(row.get("normalized_score")) for row in rows) if value is not None]
        status = str(decision.get("queue_decision") or "needs_review")
        project = str(decision.get("project_name") or "unassigned_project")
        endpoint = str(decision.get("endpoint_group") or "project_panel")
        owner = str(decision.get("owner") or "unassigned")
        positive = int(buckets.get("positive", 0) > 0)
        negative = int(buckets.get("negative", 0) > 0)
        observed = int(bool(rows))
        for counter in (
            grouped[(status, endpoint)],
            owner_grouped[(status, owner)],
            project_owner_grouped[(status, project, owner)],
            owner_endpoint_grouped[(status, owner, endpoint)],
        ):
            counter["decision_count"] += 1
            counter["observed_count"] += observed
            counter["positive_count"] += positive
            counter["negative_count"] += negative
        outcomes.append(
            {
                "event_id": decision.get("event_id"),
                "queue_decision": status,
                "owner": owner,
                "project_name": decision.get("project_name"),
                "run_id": run_id,
                "candidate_id": candidate_id,
                "endpoint_group": endpoint,
                "observed_count": len(rows),
                "positive_count": positive,
                "negative_count": negative,
                "watch_count": int(buckets.get("watch", 0) > 0),
                "retest_count": int(buckets.get("retest", 0) > 0),
                "mean_normalized_score": round(sum(scores) / len(scores), 4) if scores else None,
                "outcome_bucket": "positive" if positive else "negative" if negative else "watch" if rows else "unobserved",
            }
        )

    def summarize(grouped_counts: dict[tuple[str, str], Counter], label_name: str) -> list[dict]:
        rows = []
        for (decision, label), counts in sorted(grouped_counts.items()):
            observed = int(counts.get("observed_count") or 0)
            rows.append(
                {
                    "queue_decision": decision,
                    label_name: label,
                    "decision_count": int(counts.get("decision_count") or 0),
                    "observed_count": observed,
                    "positive_count": int(counts.get("positive_count") or 0),
                    "negative_count": int(counts.get("negative_count") or 0),
                    "hit_rate": round(float(counts.get("positive_count") or 0) / observed, 4) if observed else None,
                    "negative_rate": round(float(counts.get("negative_count") or 0) / observed, 4) if observed else None,
                }
            )
        return rows

    def summarize_multi(grouped_counts: dict[tuple[str, ...], Counter], label_names: tuple[str, ...]) -> list[dict]:
        rows = []
        for key, counts in sorted(grouped_counts.items()):
            decision, *labels = key
            observed = int(counts.get("observed_count") or 0)
            item = {
                "queue_decision": decision,
                "decision_count": int(counts.get("decision_count") or 0),
                "observed_count": observed,
                "positive_count": int(counts.get("positive_count") or 0),
                "negative_count": int(counts.get("negative_count") or 0),
                "hit_rate": round(float(counts.get("positive_count") or 0) / observed, 4) if observed else None,
                "negative_rate": round(float(counts.get("negative_count") or 0) / observed, 4) if observed else None,
            }
            item.update({name: value for name, value in zip(label_names, labels)})
            rows.append(item)
        return rows

    decision_counts = Counter(row.get("queue_decision") or "needs_review" for row in decisions)
    observed_outcomes = [row for row in outcomes if row["observed_count"]]
    next_actions = []
    accepted = [row for row in observed_outcomes if row["queue_decision"] == "accepted"]
    deferred_positive = [row for row in observed_outcomes if row["queue_decision"] in {"deferred", "retired"} and row["positive_count"]]
    if accepted:
        accepted_hit_rate = sum(row["positive_count"] for row in accepted) / len(accepted)
        if accepted_hit_rate < 0.5:
            next_actions.append("Review accepted queue criteria because observed accepted hit rate is below 50%.")
    if deferred_positive:
        next_actions.append("Review deferred/retired positives as potential missed opportunities.")
    if not observed_outcomes:
        next_actions.append("Collect outcomes for reviewed queue rows before learning reviewer-decision quality.")
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name,
        "decision_event_count": len(decisions),
        "observed_decision_count": len(observed_outcomes),
        "decision_counts": dict(decision_counts.most_common()),
        "by_decision_and_endpoint": summarize(grouped, "endpoint_group"),
        "by_decision_and_owner": summarize(owner_grouped, "owner"),
        "by_decision_project_owner": summarize_multi(project_owner_grouped, ("project_name", "owner")),
        "by_decision_owner_endpoint": summarize_multi(owner_endpoint_grouped, ("owner", "endpoint_group")),
        "candidate_outcomes": outcomes[: int(limit)],
        "recommended_next_actions": next_actions,
    }
    report["reviewer_calibration_hints"] = build_next_design_queue_reviewer_calibration_hints(report)
    return report


def write_next_design_queue_decision_quality_report(report: dict, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def _decision_lookup(decisions: list[dict] | tuple[dict, ...] | None) -> tuple[dict[str, dict], dict[str, dict]]:
    by_queue_id: dict[str, dict] = {}
    by_candidate_key: dict[str, dict] = {}
    for decision in decisions or []:
        status = str(decision.get("queue_decision") or decision.get("decision") or "").strip().lower()
        if status and status not in QUEUE_DECISION_STATUSES:
            continue
        item = {**decision, "queue_decision": status or "needs_review"}
        queue_id = str(item.get("queue_id") or "").strip()
        if queue_id:
            by_queue_id[queue_id] = item
        candidate_id = str(item.get("candidate_id") or "").strip()
        if candidate_id:
            parts = [
                str(item.get("project_name") or ""),
                str(item.get("run_id") or ""),
                candidate_id,
                str(item.get("endpoint_group") or ""),
            ]
            keys = [
                "|".join(parts),
                "|".join(["", "", candidate_id, ""]),
                candidate_id,
            ]
            for key in keys:
                by_candidate_key[key] = item
    return by_queue_id, by_candidate_key


def apply_next_design_queue_decisions(rows: list[dict], decisions: list[dict] | tuple[dict, ...] | None) -> list[dict]:
    by_queue_id, by_candidate_key = _decision_lookup(decisions)
    updated = []
    for row in rows:
        candidate_id = str(row.get("candidate_id") or "")
        keys = [
            "|".join(
                [
                    str(row.get("project_name") or ""),
                    str(row.get("run_id") or ""),
                    candidate_id,
                    str(row.get("endpoint_group") or ""),
                ]
            ),
            "|".join(["", "", candidate_id, ""]),
            candidate_id,
        ]
        decision = by_queue_id.get(str(row.get("queue_id") or "")) or next((by_candidate_key[key] for key in keys if key in by_candidate_key), None)
        if not decision:
            updated.append(row)
            continue
        status = str(decision.get("queue_decision") or "needs_review").strip().lower()
        action = row.get("recommendation_action")
        if status == "accepted":
            action = "accepted_for_next_batch"
        elif status == "deferred":
            action = "deferred_by_reviewer"
        elif status == "retired":
            action = "retired_from_queue"
        updated.append(
            {
                **row,
                "queue_decision": status,
                "recommendation_action": action,
                "review_status": status,
                "owner": decision.get("owner") or decision.get("reviewer") or row.get("owner") or "",
                "review_note": decision.get("review_note") or decision.get("note") or row.get("review_note") or "",
                "reviewed_at": decision.get("reviewed_at") or row.get("reviewed_at") or "",
            }
        )
    return updated


def write_next_design_queue_decision_template(rows: list[dict], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUEUE_DECISION_TEMPLATE_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "queue_id": row.get("queue_id"),
                    "project_name": row.get("project_name"),
                    "run_id": row.get("run_id"),
                    "candidate_id": row.get("candidate_id"),
                    "endpoint_group": row.get("endpoint_group"),
                    "queue_decision": row.get("queue_decision") or "needs_review",
                    "owner": row.get("owner") or "",
                    "review_note": row.get("review_note") or "",
                    "reviewed_at": row.get("reviewed_at") or "",
                }
            )


def build_next_design_queue(
    priority_delta_report: dict,
    *,
    max_rows: int = 24,
    decision_packets: list[dict] | tuple[dict, ...] | dict | None = None,
    analog_series_report: dict | None = None,
    queue_analog_series_delta_report: dict | None = None,
    queue_decisions: list[dict] | tuple[dict, ...] | None = None,
) -> list[dict]:
    created_at = datetime.now(timezone.utc).isoformat()
    uncertainty_lookup = _packet_uncertainty_by_candidate(decision_packets)
    rows = []
    for item in priority_delta_report.get("priority_delta_rows") or []:
        explanations = item.get("change_explanations") or []
        endpoint_deltas = item.get("endpoint_control_deltas") or []
        feedback_rows = item.get("feedback_rows") or []
        endpoint = None
        if feedback_rows:
            endpoint = feedback_rows[0].get("endpoint")
        if endpoint is None and endpoint_deltas:
            endpoint = endpoint_deltas[0].get("endpoint_group")
        candidate_id = str(item.get("candidate_id") or "")
        uncertainty = uncertainty_lookup.get(candidate_id) or {
            "decision_packet_uncertainty_score": 0.0,
            "decision_packet_evidence_status": "",
            "decision_packet_max_abs_residual": None,
            "decision_packet_recommendation": "",
            "decision_packet_uncertainty_basis": "",
        }
        action = _action_for_row(item)
        if float(uncertainty.get("decision_packet_uncertainty_score") or 0.0) >= 3.0 and action in {"measure_next_batch", "review_context"}:
            action = "review_uncertainty_before_batch"
        priority_after = _float_or_none(item.get("priority_score_after")) or 0.0
        priority_delta = _float_or_none(item.get("priority_score_delta")) or 0.0
        analog_series = _analog_series_for_candidate({**item, "endpoint_group": endpoint or "project_panel"}, analog_series_report)
        queue_series_delta = _queue_delta_for_candidate({**item, "endpoint_group": endpoint or "project_panel"}, queue_analog_series_delta_report)
        queue_priority_score = (
            priority_after
            + float(uncertainty.get("decision_packet_uncertainty_score") or 0.0) * 0.75
            + float(analog_series.get("analog_series_residual_score") or 0.0) * 0.5
            + float(queue_series_delta.get("queue_analog_series_delta_score_adjustment") or 0.0)
        )
        if float(analog_series.get("analog_series_residual_score") or 0.0) >= 2.0 and action in {"measure_next_batch", "review_context"}:
            action = "review_uncertainty_before_batch"
        basis_parts = [str(text) for text in explanations[:3]]
        if analog_series.get("analog_series_max_abs_residual") is not None:
            basis_parts.append(f"analog_series_max_abs_residual={analog_series.get('analog_series_max_abs_residual')}")
        if queue_series_delta.get("queue_analog_series_delta_action") not in {"", "no_series_delta_match", None}:
            basis_parts.append(str(queue_series_delta.get("queue_analog_series_delta_basis") or ""))
        rows.append(
            {
                "queue_id": "",
                "queue_rank": 0,
                "queue_decision_key": "",
                "project_name": priority_delta_report.get("project_name"),
                "run_id": item.get("run_id"),
                "candidate_id": candidate_id,
                "smiles": item.get("smiles"),
                "endpoint_group": endpoint or "project_panel",
                "recommendation_action": action,
                "status": item.get("status"),
                "priority_score_before": item.get("priority_score_before"),
                "priority_score_after": item.get("priority_score_after"),
                "priority_score_delta": item.get("priority_score_delta"),
                "queue_priority_score": round(queue_priority_score, 4),
                "candidate_score": item.get("candidate_score"),
                "observed_feedback_mean": item.get("observed_feedback_mean"),
                "feedback_count": item.get("feedback_count"),
                **uncertainty,
                **analog_series,
                **queue_series_delta,
                "replacement_label": item.get("replacement_label"),
                "enumeration_type": item.get("enumeration_type"),
                "rationale": " ".join(part for part in basis_parts if part),
                "review_status": "needs_review",
                "queue_decision": "",
                "owner": "",
                "review_note": "",
                "reviewed_at": "",
                "created_at": created_at,
            }
        )
    rows.sort(
        key=lambda row: (
            -float(row.get("queue_priority_score") or 0.0),
            -float(row.get("decision_packet_uncertainty_score") or 0.0),
            -abs(_float_or_none(row.get("priority_score_delta")) or 0.0),
            str(row.get("candidate_id") or ""),
        )
    )
    rows = rows[: int(max_rows)]
    for index, row in enumerate(rows, start=1):
        row["queue_id"] = f"NDQ-{index:03d}"
        row["queue_rank"] = index
        row["queue_decision_key"] = _stable_decision_key(row)
    return apply_next_design_queue_decisions(rows, queue_decisions)


def render_next_design_queue_markdown(rows: list[dict]) -> str:
    lines = [
        "# Next Design Queue",
        "",
        f"- Queue size: `{len(rows)}`",
        "",
        "| Rank | Candidate | Action | Review | Endpoint | Delta | Packet uncertainty | Analog residual | Rationale |",
        "| ---: | --- | --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        rationale = str(row.get("rationale") or "").replace("|", "\\|")
        lines.append(
            "| {rank} | `{candidate}` | `{action}` | `{review}` | `{endpoint}` | `{delta}` | `{uncertainty}` | `{analog_residual}` | {rationale} |".format(
                rank=row.get("queue_rank"),
                candidate=row.get("candidate_id"),
                action=row.get("recommendation_action"),
                review=row.get("review_status"),
                endpoint=row.get("endpoint_group"),
                delta=row.get("priority_score_delta"),
                uncertainty=row.get("decision_packet_uncertainty_score"),
                analog_residual=row.get("analog_series_max_abs_residual"),
                rationale=rationale[:240],
            )
        )
    lines.append("")
    return "\n".join(lines)


def write_next_design_queue(rows: list[dict], *, csv_path: str | Path, json_path: str | Path, markdown_path: str | Path) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps({"queue": rows}, indent=2, sort_keys=True), encoding="utf-8")
    csv_file = Path(csv_path)
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "queue_id",
        "queue_rank",
        "project_name",
        "run_id",
        "candidate_id",
        "smiles",
        "endpoint_group",
        "recommendation_action",
        "status",
        "priority_score_delta",
        "rationale",
        "review_status",
        "owner",
        "created_at",
    ]
    with csv_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    md_file = Path(markdown_path)
    md_file.parent.mkdir(parents=True, exist_ok=True)
    md_file.write_text(render_next_design_queue_markdown(rows), encoding="utf-8")
