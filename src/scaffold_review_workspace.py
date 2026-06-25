from __future__ import annotations

import json
import sqlite3
import hashlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .database import initialize_database
from .scaffold_replacements import load_scaffold_replacements
from .scaffold_rule_review import DEFAULT_SCAFFOLD_RULE_REVIEW_PATH, load_scaffold_rule_reviews, scaffold_rule_review_lookup


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")
DEFAULT_SCAFFOLD_RULES_PATH = Path("data/rules/scaffold_replacements.yaml")
DEFAULT_SCAFFOLD_WORKSPACE_PATH = Path("data/substituents/scaffold_review_workspace_report.json")
SCAFFOLD_WORKSPACE_DECISION_FIELDS = [
    "workspace_key",
    "workspace_type",
    "review_priority",
    "scaffold_rule_id",
    "candidate_id",
    "run_id",
    "candidate_score",
    "candidate_smiles",
    "decision",
    "reviewer",
    "note",
    "context",
    "parent_context",
    "decision_options",
]


def _float_or_none(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_loads(text: str | None) -> dict:
    if not text:
        return {}
    try:
        data = json.loads(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _candidate_rows(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    limit: int = 5000,
) -> list[dict]:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT pc.run_id, pc.candidate_id, pc.rank, pc.score, pc.decision_status,
                   pc.enumeration_type, pc.replacement_label, pr.project_name,
                   pr.created_at AS run_created_at, pc.payload_json
            FROM project_candidate pc
            LEFT JOIN project_run pr ON pr.run_id=pc.run_id
            WHERE (? IS NULL OR pr.project_name=?)
            ORDER BY pr.created_at DESC, pc.rank ASC
            LIMIT ?
            """,
            (project_name, project_name, int(limit)),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for row in rows:
        item = dict(row)
        payload = _json_loads(item.pop("payload_json", None))
        if not payload:
            continue
        out.append({**item, **payload})
    return out


def _workspace_key(row: dict) -> tuple[str, str, str]:
    rule_id = str(row.get("scaffold_rule_id") or "").strip()
    if rule_id:
        return (f"scaffold_rule:{rule_id}", "scaffold_rule", rule_id)
    enumeration_type = str(row.get("enumeration_type") or "").strip()
    if enumeration_type == "ring_network_replacement":
        replacement = str(row.get("replacement_id") or row.get("substituent_id") or row.get("replacement_label") or "unknown")
        return (f"ring_network:{replacement}", "ring_network", replacement)
    replacement_class = str(row.get("replacement_class") or row.get("diversity_bucket") or row.get("replacement_label") or "unknown")
    return (f"operator:{enumeration_type}:{replacement_class}", "operator", replacement_class)


def _is_relevant_scaffold_row(row: dict) -> bool:
    enumeration_type = str(row.get("enumeration_type") or "")
    return (
        enumeration_type in {"scaffold_replacement", "ring_network_replacement"}
        or bool(row.get("scaffold_rule_id"))
        or row.get("scaffold_context_score") not in {None, ""}
        or row.get("ring_novelty_bucket") not in {None, ""}
    )


def _example_candidate(row: dict) -> dict:
    return {
        "run_id": row.get("run_id"),
        "project_name": row.get("project_name"),
        "candidate_id": row.get("candidate_id"),
        "rank": row.get("rank"),
        "score": row.get("score"),
        "decision_status": row.get("decision_status"),
        "enumeration_type": row.get("enumeration_type"),
        "site_type": row.get("site_type"),
        "direction": row.get("direction"),
        "replacement_label": row.get("replacement_label"),
        "smiles": row.get("smiles"),
        "scaffold_context_score": row.get("scaffold_context_score"),
        "scaffold_local_evidence_score": row.get("scaffold_local_evidence_score") or row.get("scaffold_local_mmp_score"),
        "evidence_confidence_calibration_score": row.get("evidence_confidence_calibration_score"),
        "evidence_conflict_flags": row.get("evidence_conflict_flags"),
        "endpoint_gate_decision": row.get("endpoint_gate_decision"),
        "novelty_batch_tier": row.get("novelty_batch_tier"),
        "ring_novelty_bucket": row.get("ring_novelty_bucket"),
        "ring_diversity_bucket": row.get("ring_diversity_bucket"),
    }


def _review_priority(summary: dict) -> str:
    if summary.get("review_status") == "blocked":
        return "blocked"
    if summary.get("candidate_count", 0) == 0:
        return "collect_examples"
    if summary.get("severe_conflict_count", 0) or summary.get("endpoint_stop_count", 0):
        return "needs_medchem_review"
    if summary.get("review_status") in {"watch", "tuned"}:
        return "monitor"
    if (summary.get("mean_scaffold_local_evidence_score") or 0) >= 70:
        return "candidate_for_promotion"
    return "routine_review"


DEFAULT_SCAFFOLD_CALIBRATION_SET_PATH = Path("data/rules/scaffold_calibration_set.yaml")


def _rule_summary(rule: dict, review: dict, *, default_rule_version: str | None = None) -> dict:
    risk = rule.get("risk") or {}
    rule_version = review.get("rule_version") or rule.get("rule_version") or default_rule_version or rule.get("source_reference")
    return {
        "workspace_key": f"scaffold_rule:{rule.get('scaffold_rule_id')}",
        "workspace_type": "scaffold_rule",
        "scaffold_rule_id": rule.get("scaffold_rule_id"),
        "name": rule.get("name"),
        "replacement_class": rule.get("replacement_class"),
        "attachment_count": rule.get("attachment_count"),
        "direction_tags": ";".join(rule.get("direction_tags") or []),
        "risk_tags": ";".join(risk.get("risk_tags") or []),
        "source_name": rule.get("source_name"),
        "source_reference": rule.get("source_reference"),
        "review_status": review.get("status", "active"),
        "owner": review.get("owner") or "",
        "resolution_status": review.get("resolution_status") or "open",
        "rule_version": rule_version,
        "score_adjustment": review.get("score_adjustment", 0.0),
        "reviewed_by": review.get("reviewed_by"),
        "reviewed_at": review.get("reviewed_at"),
        "review_note": review.get("note"),
        "candidate_count": 0,
        "example_candidates": [],
    }


def _summarize_group(base: dict, candidates: list[dict]) -> dict:
    scores = [value for value in (_float_or_none(row.get("score")) for row in candidates) if value is not None]
    context_scores = [value for value in (_float_or_none(row.get("scaffold_context_score")) for row in candidates) if value is not None]
    local_scores = [
        value
        for value in (
            _float_or_none(row.get("scaffold_local_evidence_score") or row.get("scaffold_local_mmp_score"))
            for row in candidates
        )
        if value is not None
    ]
    confidence_scores = [value for value in (_float_or_none(row.get("evidence_confidence_calibration_score")) for row in candidates) if value is not None]
    endpoint_counts = Counter(str(row.get("endpoint_gate_decision") or "unknown") for row in candidates)
    novelty_counts = Counter(str(row.get("novelty_batch_tier") or row.get("ring_novelty_bucket") or "unknown") for row in candidates)
    decision_counts = Counter(str(row.get("decision_status") or "unreviewed") for row in candidates)
    severe_conflict_count = sum(
        1
        for row in candidates
        if any(
            flag in {"target_family_activity_contradiction", "target_family_activity_cliff_high", "activity_cliff_high"}
            for flag in str(row.get("evidence_conflict_flags") or "").split(";")
            if flag
        )
    )
    examples = sorted((_example_candidate(row) for row in candidates), key=lambda row: _float_or_none(row.get("score")) or 0.0, reverse=True)[:8]
    summary = {
        **base,
        "candidate_count": len(candidates),
        "top_score": round(max(scores), 4) if scores else None,
        "mean_score": _mean(scores),
        "mean_scaffold_context_score": _mean(context_scores),
        "mean_scaffold_local_evidence_score": _mean(local_scores),
        "mean_evidence_confidence_score": _mean(confidence_scores),
        "endpoint_stop_count": int(endpoint_counts.get("stop", 0)),
        "endpoint_hold_count": int(endpoint_counts.get("hold", 0)),
        "endpoint_go_count": int(endpoint_counts.get("go", 0)),
        "severe_conflict_count": severe_conflict_count,
        "decision_counts": dict(decision_counts.most_common()),
        "novelty_counts": dict(novelty_counts.most_common()),
        "example_candidates": examples,
    }
    summary["review_priority"] = _review_priority(summary)
    return summary


def build_scaffold_review_workspace_report(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    scaffold_rules_path: str | Path = DEFAULT_SCAFFOLD_RULES_PATH,
    scaffold_rule_reviews_path: str | Path = DEFAULT_SCAFFOLD_RULE_REVIEW_PATH,
    candidate_limit: int = 5000,
    owner_filter: str | None = None,
    resolution_status_filter: str | None = None,
    rule_version_filter: str | None = None,
) -> dict:
    rules = load_scaffold_replacements(scaffold_rules_path) if Path(scaffold_rules_path).exists() else []
    review_data = load_scaffold_rule_reviews(scaffold_rule_reviews_path)
    review_lookup = scaffold_rule_review_lookup(review_data)
    summaries: dict[str, dict] = {}
    for rule in rules:
        rule_id = str(rule.get("scaffold_rule_id") or "")
        summaries[f"scaffold_rule:{rule_id}"] = _rule_summary(rule, review_lookup.get(rule_id) or {}, default_rule_version=review_data.get("version"))

    candidates = [row for row in _candidate_rows(db_path=db_path, project_name=project_name, limit=candidate_limit) if _is_relevant_scaffold_row(row)]
    grouped: dict[str, list[dict]] = defaultdict(list)
    group_meta: dict[str, dict] = {}
    for row in candidates:
        key, workspace_type, group_id = _workspace_key(row)
        grouped[key].append(row)
        if key not in group_meta:
            group_meta[key] = {
                "workspace_key": key,
                "workspace_type": workspace_type,
                "scaffold_rule_id": row.get("scaffold_rule_id") if workspace_type == "scaffold_rule" else None,
                "name": row.get("replacement_label") or group_id,
                "replacement_class": row.get("replacement_class"),
                "attachment_count": row.get("scaffold_attachment_count"),
                "direction_tags": row.get("direction"),
                "risk_tags": "",
                "source_name": "project_candidate_memory",
                "source_reference": None,
                "review_status": "observed_only",
                "owner": "",
                "resolution_status": "open",
                "rule_version": review_data.get("version") or "observed_candidate_memory",
                "score_adjustment": 0.0,
                "reviewed_by": None,
                "reviewed_at": None,
                "review_note": None,
            }

    entries = []
    for key, base in summaries.items():
        entries.append(_summarize_group(base, grouped.get(key, [])))
    for key, rows in grouped.items():
        if key in summaries:
            continue
        entries.append(_summarize_group(group_meta[key], rows))

    if owner_filter:
        entries = [row for row in entries if str(row.get("owner") or "").lower() == str(owner_filter).lower()]
    if resolution_status_filter:
        entries = [row for row in entries if str(row.get("resolution_status") or "").lower() == str(resolution_status_filter).lower()]
    if rule_version_filter:
        entries = [row for row in entries if str(rule_version_filter).lower() in str(row.get("rule_version") or "").lower()]

    entries.sort(
        key=lambda row: (
            {"needs_medchem_review": 0, "candidate_for_promotion": 1, "monitor": 2, "routine_review": 3, "collect_examples": 4, "blocked": 5}.get(
                row.get("review_priority"), 9
            ),
            -(row.get("candidate_count") or 0),
            row.get("workspace_key") or "",
        )
    )
    priority_counts = Counter(row.get("review_priority") for row in entries)
    status_counts = Counter(row.get("review_status") for row in entries)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name,
        "rule_count": len(rules),
        "candidate_count": len(candidates),
        "workspace_entry_count": len(entries),
        "review_priority_counts": dict(priority_counts.most_common()),
        "review_status_counts": dict(status_counts.most_common()),
        "owner_filter": owner_filter,
        "resolution_status_filter": resolution_status_filter,
        "rule_version_filter": rule_version_filter,
        "review_version": review_data.get("version"),
        "entries": entries,
        "recommended_next_actions": [
            "Review needs_medchem_review entries before enabling broader scaffold/ring enumeration.",
            "Promote rules with repeated high local-evidence examples into tuned status after medchem review.",
            "Collect measured outcomes for collect_examples rules so context calibration is not rule-only.",
        ],
    }


def write_scaffold_review_workspace_report(report: dict, output_path: str | Path = DEFAULT_SCAFFOLD_WORKSPACE_PATH) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def scaffold_workspace_decision_template_rows(workspace_report: dict, *, max_examples_per_entry: int = 1) -> list[dict]:
    rows = []
    for entry in workspace_report.get("entries") or []:
        examples = sorted(entry.get("example_candidates") or [], key=lambda row: _float_or_none(row.get("score")) or 0.0, reverse=True)
        for example in examples[: max(1, int(max_examples_per_entry))]:
            rows.append(
                {
                    "workspace_key": entry.get("workspace_key"),
                    "workspace_type": entry.get("workspace_type"),
                    "review_priority": entry.get("review_priority"),
                    "scaffold_rule_id": entry.get("scaffold_rule_id"),
                    "candidate_id": example.get("candidate_id"),
                    "run_id": example.get("run_id"),
                    "candidate_score": example.get("score"),
                    "candidate_smiles": example.get("smiles"),
                    "decision": "",
                    "reviewer": "",
                    "note": "",
                    "context": example.get("replacement_label") or entry.get("name"),
                    "parent_context": example.get("site_type") or entry.get("workspace_type"),
                    "decision_options": "accepted|rejected",
                }
            )
    return rows


def write_scaffold_workspace_decision_template(
    workspace_report: dict,
    output_path: str | Path,
    *,
    max_examples_per_entry: int = 1,
) -> list[dict]:
    rows = scaffold_workspace_decision_template_rows(workspace_report, max_examples_per_entry=max_examples_per_entry)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        import csv

        writer = csv.DictWriter(handle, fieldnames=SCAFFOLD_WORKSPACE_DECISION_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in SCAFFOLD_WORKSPACE_DECISION_FIELDS})
    return rows


def _calibration_case_id(scaffold_rule_id: str, candidate_id: str, decision: str) -> str:
    digest = hashlib.sha1("|".join([scaffold_rule_id, candidate_id, decision]).encode("utf-8")).hexdigest()[:10].upper()
    return f"SCC-AUTO-{digest}"


def append_workspace_examples_to_calibration_set(
    workspace_report: dict,
    decisions: list[dict],
    *,
    calibration_path: str | Path = DEFAULT_SCAFFOLD_CALIBRATION_SET_PATH,
    reviewer: str | None = None,
) -> dict:
    """Append reviewed scaffold workspace examples into the curated calibration set."""
    path = Path(calibration_path)
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    else:
        data = {"calibration_cases": []}
    cases = list(data.get("calibration_cases") or [])
    existing_ids = {str(item.get("case_id")) for item in cases}
    entries = {str(entry.get("workspace_key")): entry for entry in workspace_report.get("entries") or []}
    appended = []
    skipped = []
    now = datetime.now(timezone.utc).isoformat()
    for decision in decisions:
        workspace_key = str(decision.get("workspace_key") or "")
        candidate_id = str(decision.get("candidate_id") or "")
        outcome = str(decision.get("decision") or decision.get("observed_outcome") or "").strip().lower()
        if outcome not in {"accepted", "supported", "positive", "rejected", "failed", "negative"}:
            skipped.append({"workspace_key": workspace_key, "candidate_id": candidate_id, "reason": "unsupported_decision"})
            continue
        entry = entries.get(workspace_key) or {}
        examples = entry.get("example_candidates") or []
        example = next((item for item in examples if str(item.get("candidate_id") or "") == candidate_id), None)
        if not entry or not example:
            skipped.append({"workspace_key": workspace_key, "candidate_id": candidate_id, "reason": "example_not_found"})
            continue
        scaffold_rule_id = str(entry.get("scaffold_rule_id") or example.get("scaffold_rule_id") or workspace_key.split(":")[-1])
        case_id = _calibration_case_id(scaffold_rule_id, candidate_id, outcome)
        if case_id in existing_ids:
            skipped.append({"workspace_key": workspace_key, "candidate_id": candidate_id, "reason": "duplicate_case"})
            continue
        positive = outcome in {"accepted", "supported", "positive"}
        case = {
            "case_id": case_id,
            "scaffold_rule_id": scaffold_rule_id,
            "context": decision.get("context") or example.get("replacement_label") or entry.get("name"),
            "parent_context": decision.get("parent_context") or example.get("site_type") or entry.get("workspace_type"),
            "expected_outcome": "positive" if positive else "negative",
            "observed_outcome": "supported" if positive else "fail",
            "evidence_note": decision.get("note")
            or f"Added from scaffold workspace review for candidate {candidate_id}; score={example.get('score')}.",
            "source": "scaffold_review_workspace",
            "candidate_id": candidate_id,
            "run_id": example.get("run_id"),
            "reviewed_by": reviewer or decision.get("reviewer"),
            "reviewed_at": now,
            "rule_version": entry.get("rule_version"),
        }
        cases.append(case)
        existing_ids.add(case_id)
        appended.append(case)
    data["calibration_cases"] = cases
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=False)
    return {
        "calibration_path": str(path.resolve()),
        "appended_count": len(appended),
        "skipped_count": len(skipped),
        "appended_cases": appended,
        "skipped": skipped,
    }
