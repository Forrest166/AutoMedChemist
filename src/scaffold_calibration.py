from __future__ import annotations

import json
import sqlite3
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

import yaml

from .database import initialize_database


DEFAULT_SCAFFOLD_CALIBRATION_PATH = Path("data/rules/scaffold_calibration_set.yaml")
DEFAULT_SCAFFOLD_CALIBRATION_REPORT_PATH = Path("data/substituents/scaffold_calibration_report.json")
DEFAULT_SCAFFOLD_CALIBRATION_AUDIT_PATH = Path("data/substituents/scaffold_calibration_audit_report.json")
DEFAULT_SCAFFOLD_REVIEW_DRAFT_PATH = Path("data/substituents/scaffold_rule_review_drafts.csv")
DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")
POSITIVE_DECISIONS = {"shortlisted", "selected"}
NEGATIVE_DECISIONS = {"rejected"}
POSITIVE_CLASSES = {"active", "pass", "improved", "selected", "shortlisted"}
NEGATIVE_CLASSES = {"inactive", "fail", "worse", "rejected"}


def load_scaffold_calibration_cases(path: str | Path = DEFAULT_SCAFFOLD_CALIBRATION_PATH) -> list[dict]:
    calibration_path = Path(path)
    if not calibration_path.exists():
        return []
    with calibration_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if isinstance(data, dict):
        return list(data.get("calibration_cases") or [])
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported scaffold calibration shape: {calibration_path}")


def _case_score(case: dict) -> float:
    expected = str(case.get("expected_outcome") or "").lower()
    observed = str(case.get("observed_outcome") or "").lower()
    if not expected or not observed:
        return 0.0
    positive = {"positive", "pass", "supported", "improved"}
    negative = {"negative", "fail", "worse", "deprioritized"}
    if expected in positive and observed in positive:
        return 1.0
    if expected in negative and observed in negative:
        return 1.0
    if observed in {"neutral", "mixed", "inconclusive"}:
        return 0.5
    return -1.0


def calibrate_scaffold_rules(cases: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        rule_id = str(case.get("scaffold_rule_id") or "").strip()
        if rule_id:
            grouped[rule_id].append(case)

    rules = []
    for rule_id, items in sorted(grouped.items()):
        scores = [_case_score(item) for item in items]
        positives = sum(1 for score in scores if score > 0)
        negatives = sum(1 for score in scores if score < 0)
        neutral = sum(1 for score in scores if score == 0)
        mean_score = sum(scores) / len(scores) if scores else 0.0
        if mean_score >= 0.75 and len(items) >= 2:
            action = "boost"
            adjustment = 8.0
        elif mean_score <= 0.0 and negatives:
            action = "deprioritize"
            adjustment = -15.0
        else:
            action = "watch"
            adjustment = 0.0
        rules.append(
            {
                "scaffold_rule_id": rule_id,
                "case_count": len(items),
                "positive_case_count": positives,
                "negative_case_count": negatives,
                "neutral_case_count": neutral,
                "mean_case_score": round(mean_score, 4),
                "calibration_action": action,
                "score_adjustment": adjustment,
                "contexts": sorted({str(item.get("context") or "general") for item in items}),
            }
        )

    action_counts = Counter(item["calibration_action"] for item in rules)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(cases),
        "rule_count": len(rules),
        "action_counts": dict(action_counts.most_common()),
        "rules": rules,
    }


def _rule_lookup(report: dict | None) -> dict[str, dict]:
    return {str(item.get("scaffold_rule_id")): item for item in (report or {}).get("rules") or [] if item.get("scaffold_rule_id")}


def _suggest_rule_status_change(rule_id: str, current_rule: dict, workspace_entry: dict) -> dict | None:
    action = str(current_rule.get("calibration_action") or "unseen")
    case_count = int(current_rule.get("case_count") or 0)
    workspace_priority = str(workspace_entry.get("review_priority") or "")
    workspace_status = str(workspace_entry.get("review_status") or "")
    workspace_candidates = int(workspace_entry.get("candidate_count") or 0)
    suggested_status = None
    suggested_resolution = "needs_more_data"
    confidence = "low"
    rationale = ""
    if action == "boost" and case_count >= 2 and workspace_priority != "needs_medchem_review":
        suggested_status = "tuned"
        suggested_resolution = "accepted"
        confidence = "medium" if case_count < 5 else "high"
        rationale = "Calibration cases support a positive score adjustment; medchem sign-off is still required before writing rule review status."
    elif action == "deprioritize" and case_count >= 1:
        suggested_status = "watch"
        confidence = "medium" if case_count >= 3 else "low"
        rationale = "Calibration cases show negative or mixed behavior; keep the rule visible but conservative pending review."
    elif workspace_priority == "needs_medchem_review":
        suggested_status = workspace_status if workspace_status in {"watch", "blocked", "tuned"} else "watch"
        rationale = "Workspace evidence explicitly requires medchem review before promotion or broad use."
    elif workspace_candidates and case_count < 2:
        suggested_status = workspace_status if workspace_status in {"watch", "blocked", "tuned"} else "watch"
        rationale = "Workspace has candidate examples but calibration support is still thin."
    if not suggested_status:
        return None
    return {
        "scaffold_rule_id": rule_id,
        "current_calibration_action": action,
        "current_case_count": case_count,
        "current_score_adjustment": current_rule.get("score_adjustment"),
        "workspace_review_priority": workspace_priority,
        "workspace_review_status": workspace_status,
        "workspace_candidate_count": workspace_candidates,
        "suggested_review_status": suggested_status,
        "suggested_resolution_status": suggested_resolution,
        "suggested_score_adjustment": current_rule.get("score_adjustment") if action in {"boost", "deprioritize"} else None,
        "suggestion_confidence": confidence,
        "requires_manual_review": True,
        "rationale": rationale,
    }


def build_scaffold_calibration_audit_report(
    previous_report: dict | None,
    current_report: dict,
    *,
    workspace_report: dict | None = None,
) -> dict:
    previous = _rule_lookup(previous_report)
    current = _rule_lookup(current_report)
    workspace = {str(item.get("scaffold_rule_id")): item for item in (workspace_report or {}).get("entries") or [] if item.get("scaffold_rule_id")}
    all_rule_ids = sorted(set(previous) | set(current))
    rows = []
    for rule_id in all_rule_ids:
        before = previous.get(rule_id) or {}
        after = current.get(rule_id) or {}
        workspace_entry = workspace.get(rule_id) or {}
        before_adjustment = _float_or_none(before.get("score_adjustment")) or 0.0
        after_adjustment = _float_or_none(after.get("score_adjustment")) or 0.0
        before_action = str(before.get("calibration_action") or "missing")
        after_action = str(after.get("calibration_action") or "missing")
        case_delta = int(after.get("case_count") or 0) - int(before.get("case_count") or 0)
        adjustment_delta = round(after_adjustment - before_adjustment, 4)
        changed = before_action != after_action or abs(adjustment_delta) > 0.0001 or case_delta != 0
        if not changed and rule_id in previous and rule_id in current:
            continue
        if rule_id not in previous:
            change_type = "new_rule_signal"
        elif rule_id not in current:
            change_type = "removed_rule_signal"
        elif before_action != after_action:
            change_type = "action_changed"
        elif abs(adjustment_delta) > 0.0001:
            change_type = "adjustment_changed"
        else:
            change_type = "case_count_changed"
        rows.append(
            {
                "scaffold_rule_id": rule_id,
                "change_type": change_type,
                "previous_action": before_action,
                "current_action": after_action,
                "previous_score_adjustment": before.get("score_adjustment"),
                "current_score_adjustment": after.get("score_adjustment"),
                "score_adjustment_delta": adjustment_delta,
                "previous_case_count": before.get("case_count", 0),
                "current_case_count": after.get("case_count", 0),
                "case_count_delta": case_delta,
                "previous_mean_case_score": before.get("mean_case_score"),
                "current_mean_case_score": after.get("mean_case_score"),
                "workspace_review_priority": workspace_entry.get("review_priority"),
                "workspace_review_status": workspace_entry.get("review_status"),
                "workspace_candidate_count": workspace_entry.get("candidate_count"),
                "workspace_top_score": workspace_entry.get("top_score"),
            }
        )
    rows.sort(
        key=lambda row: (
            {"action_changed": 0, "new_rule_signal": 1, "adjustment_changed": 2, "case_count_changed": 3, "removed_rule_signal": 4}.get(
                str(row.get("change_type")), 9
            ),
            -abs(float(row.get("score_adjustment_delta") or 0.0)),
            -(row.get("current_case_count") or 0),
            str(row.get("scaffold_rule_id") or ""),
        )
    )
    workspace_alignment = []
    for rule_id, entry in workspace.items():
        current_rule = current.get(rule_id) or {}
        priority = str(entry.get("review_priority") or "")
        action = str(current_rule.get("calibration_action") or "unseen")
        case_count = int(current_rule.get("case_count") or 0)
        candidate_count = int(entry.get("candidate_count") or 0)
        if priority in {"needs_medchem_review", "candidate_for_promotion"} or action in {"boost", "deprioritize"} or (candidate_count and case_count < 2):
            workspace_alignment.append(
                {
                    "scaffold_rule_id": rule_id,
                    "review_priority": priority,
                    "calibration_action": action,
                    "score_adjustment": current_rule.get("score_adjustment"),
                    "case_count": case_count,
                    "workspace_candidate_count": candidate_count,
                    "recommended_followup": "review_before_promotion"
                    if priority == "needs_medchem_review"
                    else "candidate_for_rule_status_update"
                    if action == "boost"
                    else "monitor_or_collect_more_examples",
                }
            )
    suggested_rule_status_changes = []
    for rule_id in sorted(set(current) | set(workspace)):
        suggestion = _suggest_rule_status_change(rule_id, current.get(rule_id) or {}, workspace.get(rule_id) or {})
        if suggestion:
            suggested_rule_status_changes.append(suggestion)
    suggested_rule_status_changes.sort(
        key=lambda row: (
            {"high": 0, "medium": 1, "low": 2}.get(str(row.get("suggestion_confidence")), 9),
            {"tuned": 0, "watch": 1, "blocked": 2}.get(str(row.get("suggested_review_status")), 9),
            -(row.get("workspace_candidate_count") or 0),
            str(row.get("scaffold_rule_id") or ""),
        )
    )
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "previous_created_at": (previous_report or {}).get("created_at"),
        "current_created_at": current_report.get("created_at"),
        "previous_rule_count": len(previous),
        "current_rule_count": len(current),
        "changed_rule_count": len(rows),
        "action_change_count": sum(1 for row in rows if row.get("change_type") == "action_changed"),
        "new_rule_signal_count": sum(1 for row in rows if row.get("change_type") == "new_rule_signal"),
        "workspace_entry_count": len((workspace_report or {}).get("entries") or []),
        "suggested_rule_status_change_count": len(suggested_rule_status_changes),
        "changed_rules": rows,
        "workspace_alignment": sorted(
            workspace_alignment,
            key=lambda row: (
                {"review_before_promotion": 0, "candidate_for_rule_status_update": 1, "monitor_or_collect_more_examples": 2}.get(
                    str(row.get("recommended_followup")), 9
                ),
                -(row.get("workspace_candidate_count") or 0),
            ),
        ),
        "suggested_rule_status_changes": suggested_rule_status_changes,
        "recommended_next_actions": [
            "Review action_changed scaffold rules before updating broad rule status.",
            "Use workspace_alignment to decide which boosted or deprioritized rules need medchem sign-off.",
            "Collect more examples for rules with workspace candidates but low calibration case counts.",
            "Apply suggested_rule_status_changes only through the manual scaffold rule review workflow.",
        ],
    }


def calibration_lookup(report: dict | None) -> dict[str, dict]:
    return {str(item.get("scaffold_rule_id")): item for item in (report or {}).get("rules") or [] if item.get("scaffold_rule_id")}


def _float_or_none(value) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _candidate_payload(value: str | None) -> dict:
    try:
        return json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}


def _outcome(row: dict) -> str:
    decision = str(row.get("decision_status") or "").strip().lower()
    classification = str(row.get("classification") or "").strip().lower()
    normalized = _float_or_none(row.get("normalized_score"))
    if decision in POSITIVE_DECISIONS or classification in POSITIVE_CLASSES or (normalized is not None and normalized >= 70):
        return "positive"
    if decision in NEGATIVE_DECISIONS or classification in NEGATIVE_CLASSES or (normalized is not None and normalized <= 30):
        return "negative"
    return "neutral"


def _split_flags(value: str | None) -> list[str]:
    return [flag.strip() for flag in str(value or "").split(";") if flag.strip()]


def _query_scaffold_feedback(conn: sqlite3.Connection, project_name: str | None = None) -> list[dict]:
    conn.row_factory = sqlite3.Row
    params: tuple = ()
    where = ""
    if project_name:
        where = "WHERE pr.project_name = ?"
        params = (project_name,)
    rows = conn.execute(
        f"""
        SELECT
            pr.project_name,
            pc.run_id,
            pc.candidate_id,
            pc.decision_status,
            pc.enumeration_type,
            pc.payload_json,
            pf.normalized_score,
            pf.classification
        FROM project_candidate pc
        JOIN project_run pr ON pr.run_id = pc.run_id
        LEFT JOIN project_feedback pf
            ON pf.run_id = pc.run_id AND pf.candidate_id = pc.candidate_id
        {where}
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def scaffold_context_calibration_report(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
) -> dict:
    conn = initialize_database(db_path)
    try:
        rows = _query_scaffold_feedback(conn, project_name=project_name)
    finally:
        conn.close()

    scaffold_rows = []
    for row in rows:
        payload = _candidate_payload(row.get("payload_json"))
        score = _float_or_none(payload.get("scaffold_context_score"))
        if score is None and row.get("enumeration_type") != "scaffold_replacement":
            continue
        scaffold_rows.append({**row, "payload": payload, "scaffold_context_score": score})

    positives = [row for row in scaffold_rows if _outcome(row) == "positive"]
    negatives = [row for row in scaffold_rows if _outcome(row) == "negative"]
    neutrals = [row for row in scaffold_rows if _outcome(row) == "neutral"]

    def mean_score(items: list[dict]) -> float | None:
        scores = [_float_or_none(item.get("scaffold_context_score")) for item in items]
        scores = [score for score in scores if score is not None]
        return round(mean(scores), 4) if scores else None

    flag_rows: dict[str, list[str]] = defaultdict(list)
    for row in scaffold_rows:
        flags = _split_flags((row.get("payload") or {}).get("scaffold_context_flags")) or ["no_flag"]
        outcome = _outcome(row)
        for flag in flags:
            flag_rows[flag].append(outcome)

    flag_impacts = []
    flag_penalties = {}
    for flag, outcomes in sorted(flag_rows.items()):
        counts = Counter(outcomes)
        total = sum(counts.values())
        negative_rate = counts.get("negative", 0) / total if total else 0.0
        positive_rate = counts.get("positive", 0) / total if total else 0.0
        suggested_penalty = 0.0
        if total >= 3 and negative_rate - positive_rate >= 0.25 and flag != "no_flag":
            suggested_penalty = min(12.0, round((negative_rate - positive_rate) * 20.0, 2))
            flag_penalties[flag] = suggested_penalty
        flag_impacts.append(
            {
                "flag": flag,
                "candidate_count": total,
                "outcome_counts": dict(counts.most_common()),
                "positive_rate": round(positive_rate, 4),
                "negative_rate": round(negative_rate, 4),
                "suggested_penalty": suggested_penalty,
            }
        )

    positive_mean = mean_score(positives)
    negative_mean = mean_score(negatives)
    score_offset = 0.0
    basis = "Insufficient positive/negative scaffold feedback; keep default scaffold-context behavior."
    if positive_mean is not None and negative_mean is not None:
        delta = positive_mean - negative_mean
        if delta >= 8:
            score_offset = 3.0
            basis = "Positive scaffold candidates show higher context scores; mild positive offset suggested."
        elif delta <= -8:
            score_offset = -4.0
            basis = "Negative scaffold candidates show higher context scores; conservative downshift suggested."
        else:
            basis = "Positive and negative scaffold candidates are not clearly separated; keep near-default scoring."

    calibration_profile = {
        "scaffold_context_calibration": {
            "enabled": True,
            "score_offset": score_offset,
            "flag_penalties": flag_penalties,
            "min_score": 0,
            "max_score": 100,
            "basis": basis,
        }
    }
    return {
        "project_name": project_name,
        "scaffold_candidate_count": len(scaffold_rows),
        "outcome_counts": dict(Counter(_outcome(row) for row in scaffold_rows).most_common()),
        "positive_count": len(positives),
        "negative_count": len(negatives),
        "neutral_count": len(neutrals),
        "positive_mean_context_score": positive_mean,
        "negative_mean_context_score": negative_mean,
        "flag_impacts": flag_impacts,
        "calibration_profile": calibration_profile,
        "basis": basis,
    }


def apply_scaffold_context_calibration(score: float | None, *, profile: dict | None = None, row: dict | None = None) -> float | None:
    if score is None:
        return None
    profile = profile or {}
    row = row or {}
    config = profile.get("scaffold_context_calibration") or {}
    if config and not config.get("enabled", True):
        return round(float(score), 2)
    replacement_class = str(row.get("replacement_class") or "")
    class_adjustments = config.get("replacement_class_adjustments") or {}
    flag_adjustments = config.get("flag_adjustments") or {}
    adjustment = float(config.get("score_offset") or 0.0)
    adjustment += float(class_adjustments.get(replacement_class, 0.0) or 0.0)
    flags = set(_split_flags(row.get("scaffold_context_flags")))
    for flag in flags:
        adjustment += float(flag_adjustments.get(flag, 0.0) or 0.0)
        adjustment -= float((config.get("flag_penalties") or {}).get(flag, 0.0) or 0.0)
    min_score = float(config.get("min_score", 0.0))
    max_score = float(config.get("max_score", 100.0))
    return round(max(min_score, min(max_score, float(score) + adjustment)), 2)


def load_scaffold_calibration_report(path: str | Path = DEFAULT_SCAFFOLD_CALIBRATION_REPORT_PATH) -> dict:
    report_path = Path(path)
    if not report_path.exists():
        return {}
    return json.loads(report_path.read_text(encoding="utf-8")) or {}


def write_scaffold_calibration_report(report: dict, output_path: str | Path = DEFAULT_SCAFFOLD_CALIBRATION_REPORT_PATH) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def write_scaffold_calibration_audit_report(report: dict, output_path: str | Path = DEFAULT_SCAFFOLD_CALIBRATION_AUDIT_PATH) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


SCAFFOLD_REVIEW_DRAFT_FIELDS = [
    "draft_id",
    "draft_status",
    "scaffold_rule_id",
    "suggested_status",
    "suggested_resolution_status",
    "suggested_score_adjustment",
    "suggestion_confidence",
    "requires_manual_review",
    "reviewer",
    "owner",
    "rule_version",
    "note",
    "source_audit_created_at",
    "rationale",
    "reviewed_at",
    "reviewed_by",
    "review_note",
    "applied_at",
    "applied_by",
    "application_event_id",
]
SCAFFOLD_REVIEW_DRAFT_STATUSES = {
    "draft_not_applied",
    "approved_for_apply",
    "ready_to_apply",
    "apply",
    "deferred",
    "rejected",
    "retired",
    "applied",
}
SCAFFOLD_REVIEW_DRAFT_APPLY_STATUSES = {"approved_for_apply", "ready_to_apply", "apply"}


def build_scaffold_rule_review_drafts(
    audit_report: dict,
    *,
    reviewer: str | None = None,
    owner: str | None = None,
    rule_version: str | None = None,
) -> list[dict]:
    """Turn scaffold audit suggestions into non-applied manual-review draft rows."""
    import hashlib

    created_at = audit_report.get("created_at") or datetime.now(timezone.utc).isoformat()
    rows = []
    for suggestion in audit_report.get("suggested_rule_status_changes") or []:
        rule_id = str(suggestion.get("scaffold_rule_id") or "")
        if not rule_id:
            continue
        digest = hashlib.sha1("|".join([rule_id, str(suggestion.get("suggested_review_status") or ""), created_at]).encode("utf-8")).hexdigest()[:10].upper()
        rows.append(
            {
                "draft_id": f"SCRDRAFT-{digest}",
                "draft_status": "draft_not_applied",
                "scaffold_rule_id": rule_id,
                "suggested_status": suggestion.get("suggested_review_status"),
                "suggested_resolution_status": suggestion.get("suggested_resolution_status"),
                "suggested_score_adjustment": suggestion.get("suggested_score_adjustment"),
                "suggestion_confidence": suggestion.get("suggestion_confidence"),
                "requires_manual_review": True,
                "reviewer": reviewer or "",
                "owner": owner or "",
                "rule_version": rule_version or "",
                "note": "Draft generated from scaffold calibration audit; apply only through manual scaffold rule review.",
                "source_audit_created_at": created_at,
                "rationale": suggestion.get("rationale"),
            }
        )
    rows.sort(
        key=lambda row: (
            {"high": 0, "medium": 1, "low": 2}.get(str(row.get("suggestion_confidence")), 9),
            str(row.get("scaffold_rule_id") or ""),
        )
    )
    return rows


def write_scaffold_rule_review_drafts(rows: list[dict], output_path: str | Path = DEFAULT_SCAFFOLD_REVIEW_DRAFT_PATH) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    extras = sorted({key for row in rows for key in row if key not in SCAFFOLD_REVIEW_DRAFT_FIELDS})
    fieldnames = SCAFFOLD_REVIEW_DRAFT_FIELDS + extras
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def load_scaffold_rule_review_drafts(path: str | Path = DEFAULT_SCAFFOLD_REVIEW_DRAFT_PATH) -> list[dict]:
    draft_path = Path(path)
    if not draft_path.exists():
        return []
    with draft_path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _float_or_default(value: object, default: float = 0.0) -> float:
    if value in {None, ""}:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def update_scaffold_rule_review_draft_status(
    draft_id: str,
    *,
    status: str,
    draft_path: str | Path = DEFAULT_SCAFFOLD_REVIEW_DRAFT_PATH,
    reviewer: str | None = None,
    note: str | None = None,
    rows: list[dict] | None = None,
    write_back: bool = True,
) -> dict:
    """Record an explicit review decision for one scaffold rule-review draft."""
    normalized = str(status or "").strip().lower()
    if normalized not in SCAFFOLD_REVIEW_DRAFT_STATUSES:
        raise ValueError(f"Unsupported scaffold review draft status: {status}")
    now = datetime.now(timezone.utc).isoformat()
    source_rows = [dict(row) for row in (rows if rows is not None else load_scaffold_rule_review_drafts(draft_path))]
    updated_rows = []
    updated = None
    for row in source_rows:
        if str(row.get("draft_id") or "") != str(draft_id):
            updated_rows.append(row)
            continue
        updated = {
            **row,
            "draft_status": normalized,
            "reviewed_at": now,
            "reviewed_by": reviewer or row.get("reviewer") or row.get("reviewed_by") or "",
            "review_note": note or row.get("review_note") or "",
        }
        updated_rows.append(updated)
    if updated is None:
        raise ValueError(f"Scaffold review draft not found: {draft_id}")
    if write_back:
        write_scaffold_rule_review_drafts(updated_rows, draft_path)
    return {
        "created_at": now,
        "draft_id": draft_id,
        "status": normalized,
        "updated": updated,
        "rows": updated_rows,
    }


def bulk_update_scaffold_rule_review_draft_status(
    *,
    status: str,
    draft_path: str | Path = DEFAULT_SCAFFOLD_REVIEW_DRAFT_PATH,
    draft_ids: list[str] | None = None,
    current_statuses: list[str] | None = None,
    suggestion_confidences: list[str] | None = None,
    reviewer: str | None = None,
    note: str | None = None,
    rows: list[dict] | None = None,
    write_back: bool = True,
) -> dict:
    """Record one review decision across a filtered scaffold draft batch."""
    normalized = str(status or "").strip().lower()
    if normalized not in SCAFFOLD_REVIEW_DRAFT_STATUSES:
        raise ValueError(f"Unsupported scaffold review draft status: {status}")
    selected_ids = {str(item) for item in draft_ids or [] if str(item)}
    selected_current_statuses = {str(item).strip().lower() for item in current_statuses or [] if str(item).strip()}
    selected_confidences = {str(item).strip().lower() for item in suggestion_confidences or [] if str(item).strip()}
    now = datetime.now(timezone.utc).isoformat()
    source_rows = [dict(row) for row in (rows if rows is not None else load_scaffold_rule_review_drafts(draft_path))]
    updated_rows = []
    updated = []
    skipped = []
    for row in source_rows:
        draft_id = str(row.get("draft_id") or "")
        current_status = str(row.get("draft_status") or "").strip().lower()
        confidence = str(row.get("suggestion_confidence") or "").strip().lower()
        matches = True
        if selected_ids and draft_id not in selected_ids:
            matches = False
        if selected_current_statuses and current_status not in selected_current_statuses:
            matches = False
        if selected_confidences and confidence not in selected_confidences:
            matches = False
        if current_status == "applied":
            matches = False
        if not matches:
            skipped.append(row)
            updated_rows.append(row)
            continue
        changed = {
            **row,
            "draft_status": normalized,
            "reviewed_at": now,
            "reviewed_by": reviewer or row.get("reviewer") or row.get("reviewed_by") or "",
            "review_note": note or row.get("review_note") or "",
        }
        updated.append(changed)
        updated_rows.append(changed)
    if write_back:
        write_scaffold_rule_review_drafts(updated_rows, draft_path)
    return {
        "created_at": now,
        "status": normalized,
        "updated_count": len(updated),
        "skipped_count": len(skipped),
        "updated_draft_ids": [row.get("draft_id") for row in updated],
        "rows": updated_rows,
    }


def apply_scaffold_rule_review_drafts(
    rows: list[dict] | None = None,
    *,
    draft_path: str | Path = DEFAULT_SCAFFOLD_REVIEW_DRAFT_PATH,
    draft_ids: list[str] | None = None,
    reviewer: str | None = None,
    owner: str | None = None,
    rule_reviews_path: str | Path | None = None,
    db_path: str | Path | None = None,
    allow_selected_draft_status: bool = False,
    write_back: bool = True,
) -> dict:
    """Apply manually approved scaffold review drafts through the review workflow."""
    from .scaffold_rule_review import update_scaffold_rule_review

    now = datetime.now(timezone.utc).isoformat()
    selected = {str(item) for item in draft_ids or [] if str(item)}
    source_rows = [dict(row) for row in (rows if rows is not None else load_scaffold_rule_review_drafts(draft_path))]
    applied = []
    skipped = []
    updated_rows = []
    for row in source_rows:
        draft_id = str(row.get("draft_id") or "")
        status = str(row.get("draft_status") or "").strip().lower()
        selected_for_apply = bool(selected and draft_id in selected)
        approved_for_apply = status in SCAFFOLD_REVIEW_DRAFT_APPLY_STATUSES
        if not approved_for_apply and not (selected_for_apply and allow_selected_draft_status):
            skipped.append({**row, "skip_reason": "not_approved_for_apply"})
            updated_rows.append(row)
            continue
        rule_id = str(row.get("scaffold_rule_id") or "")
        suggested_status = str(row.get("suggested_status") or "").strip()
        if not rule_id or not suggested_status:
            skipped.append({**row, "skip_reason": "missing_rule_or_status"})
            updated_rows.append(row)
            continue
        review = update_scaffold_rule_review(
            rule_id,
            status=suggested_status,
            reviewer=reviewer or row.get("reviewer") or None,
            owner=owner or row.get("owner") or None,
            resolution_status=row.get("suggested_resolution_status") or None,
            rule_version=row.get("rule_version") or None,
            note=row.get("note") or row.get("rationale") or None,
            score_adjustment=_float_or_default(row.get("suggested_score_adjustment"), 0.0),
            path=rule_reviews_path,
            db_path=db_path,
        )
        updated = {
            **row,
            "draft_status": "applied",
            "applied_at": now,
            "applied_by": reviewer or row.get("reviewer") or "",
            "application_event_id": review.get("event_id"),
        }
        updated_rows.append(updated)
        applied.append(updated)
    if write_back:
        write_scaffold_rule_review_drafts(updated_rows, draft_path)
    return {
        "created_at": now,
        "processed_count": len(source_rows),
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "applied_draft_ids": [row.get("draft_id") for row in applied],
        "skipped": skipped,
        "rows": updated_rows,
    }
