from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")
DEFAULT_CONTRADICTION_REPORT_PATH = Path("data/substituents/rgroup_normalized_pair_contradictions.json")
DEFAULT_CONTRADICTION_CSV_PATH = Path("data/substituents/rgroup_normalized_pair_contradictions.csv")
DEFAULT_CONTRADICTION_REVIEW_PATH = Path("data/substituents/rgroup_normalized_pair_contradiction_reviews.csv")
DEFAULT_CONTRADICTION_DECISION_SUMMARY_PATH = Path("data/substituents/rgroup_normalized_pair_contradiction_decisions.json")
DEFAULT_PAIR_CONFLICT_OWNER_REVIEW_PACKET_PATH = Path("data/substituents/rgroup_pair_conflict_owner_review_packet.json")
DEFAULT_PAIR_CONFLICT_OWNER_REVIEW_PACKET_CSV_PATH = Path("data/substituents/rgroup_pair_conflict_owner_review_packet.csv")
DEFAULT_PAIR_CONFLICT_OWNER_DECISION_LEDGER_PATH = Path("data/substituents/rgroup_pair_conflict_owner_decision_ledger.json")
DEFAULT_PAIR_CONFLICT_OWNER_DECISION_LEDGER_CSV_PATH = Path("data/substituents/rgroup_pair_conflict_owner_decision_ledger.csv")
PAIR_CONTRADICTION_REVIEW_DECISIONS = {
    "pending_review",
    "accepted_bidirectional",
    "context_dependent",
    "defer_source_review",
    "prefer_reverse_direction",
    "reject_feed_direction",
    "reference_only_watch",
}
PAIR_CONFLICT_OWNER_DECISIONS = {
    "pending_owner_review",
    "keep_deferred",
    "raise_confidence_and_resolve",
    "reject_feed_direction",
}


def _int(value: object, default: int = 0) -> int:
    try:
        if value in {None, ""}:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: object, default: float = 0.0) -> float:
    try:
        if value in {None, ""}:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _split_key(key: str) -> tuple[str, str]:
    left, sep, right = str(key or "").partition(">>")
    return left if sep else "", right if sep else ""


def _conflict_id(replacement_id: object, reverse_key: object) -> str:
    digest = hashlib.sha1(f"{replacement_id}|{reverse_key}".encode("utf-8")).hexdigest()[:12].upper()
    return f"RGCON-{digest}"


def _rows(conn: sqlite3.Connection, query: str, params: tuple = ()) -> list[dict]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(query, params)]


def _read_csv_rows(path: str | Path) -> list[dict]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv_rows(rows: list[dict], path: str | Path, preferred_fields: list[str]) -> None:
    fields = list(preferred_fields)
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


def load_rgroup_pair_contradiction_reviews(path: str | Path = DEFAULT_CONTRADICTION_REVIEW_PATH) -> dict[str, dict]:
    return {str(row.get("conflict_id") or "").strip(): row for row in _read_csv_rows(path) if row.get("conflict_id")}


def _review_defaults(row: dict) -> dict:
    return {
        "review_decision": "pending_review",
        "resolution_class": "",
        "score_policy_action": "hold_feed_direction_out_of_positive_prior",
        "source_confidence_action": "keep_current_until_reviewed",
        "reviewer": "",
        "reviewed_at": "",
        "review_note": "",
    }


def _merge_review(row: dict, review: dict | None) -> dict:
    item = dict(row)
    defaults = _review_defaults(row)
    for key, value in defaults.items():
        item[key] = (review or {}).get(key) or row.get(key) or value
    return item


def _first_pass_decision(row: dict) -> dict:
    severity = str(row.get("severity") or "").lower()
    provenance = str(row.get("provenance_review_status") or "").lower()
    tier = str(row.get("source_confidence_tier") or "").lower()
    reverse_ratio = _float(row.get("reverse_to_direct_weight_ratio"), 0.0)
    direct_records = _int(row.get("direct_source_record_count"))
    reverse_records = _int(row.get("reverse_source_record_count"))
    score = _float(row.get("source_confidence_score"), 0.0)

    if severity == "blocking" or provenance in {"rejected", "retired"}:
        return {
            "review_decision": "reject_feed_direction",
            "resolution_class": "source_governance_block",
            "score_policy_action": "exclude_feed_direction_from_positive_prior",
            "source_confidence_action": "keep_rejected_or_retired",
            "review_note": "Rejected or retired provenance cannot be promoted as positive directional evidence.",
        }
    if "patent" in tier or provenance in {"deferred", "deferred_review"}:
        return {
            "review_decision": "defer_source_review",
            "resolution_class": "provisional_source_needs_owner_review",
            "score_policy_action": "hold_feed_direction_out_of_positive_prior",
            "source_confidence_action": "keep_deferred_until_owner_review",
            "review_note": "Provisional or deferred source is kept as traceable evidence but not promoted into a positive scoring prior.",
        }
    if reverse_ratio >= 3.0 and reverse_records > direct_records and score < 0.75:
        return {
            "review_decision": "prefer_reverse_direction",
            "resolution_class": "reverse_direction_stronger",
            "score_policy_action": "downweight_feed_direction_until_project_support",
            "source_confidence_action": "keep_current_confidence",
            "review_note": "Reverse direction has materially stronger aggregate evidence; keep this direction reviewable until project support appears.",
        }
    if direct_records and reverse_records:
        return {
            "review_decision": "context_dependent",
            "resolution_class": "bidirectional_context_dependent",
            "score_policy_action": "use_only_with_endpoint_or_project_context",
            "source_confidence_action": "retain_bidirectional_evidence",
            "review_note": "Both directions have support; treat as context-dependent bioisosteric evidence rather than a global positive prior.",
        }
    return {
        "review_decision": "accepted_bidirectional",
        "resolution_class": "accepted_low_risk_bidirectional",
        "score_policy_action": "allow_as_contextual_prior",
        "source_confidence_action": "retain_bidirectional_evidence",
        "review_note": "No blocking source issue detected; retain both directions as contextual evidence.",
    }


def build_rgroup_normalized_pair_contradiction_report(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    review_path: str | Path | None = DEFAULT_CONTRADICTION_REVIEW_PATH,
    min_reverse_aggregate_weight: int = 10,
    min_reverse_source_records: int = 1,
    high_weight_threshold: int = 50,
) -> dict:
    db_file = Path(db_path)
    if not db_file.exists():
        return {"status": "missing_db", "row_count": 0, "rows": []}
    with sqlite3.connect(db_file) as conn:
        normalized = {
            row["normalized_pair_key"]: row
            for row in _rows(
                conn,
                """
                select normalized_pair_key, normalized_source_smiles, normalized_target_smiles,
                       source_record_count, aggregate_edge_weight, source_names,
                       source_replacement_ids, source_confidence_tiers, max_source_confidence_score
                from rgroup_replacement_normalized
                where normalized_pair_key is not null and normalized_pair_key != ''
                """,
            )
        }
        feed_rows = _rows(
            conn,
            """
            select replacement_id, normalized_pair_key, normalized_source_smiles, normalized_target_smiles,
                   edge_weight, aggregate_edge_weight, source_record_count, source_name,
                   source_reference, source_confidence_tier, source_confidence_score,
                   row_sha256, source_owner, source_license, provenance_level,
                   provenance_review_status, provenance_note
            from rgroup_replacement
            where normalized_pair_key is not null and normalized_pair_key != ''
              and (
                row_sha256 is not null or source_owner is not null
                or provenance_level is not null or provenance_review_status is not null
              )
            """,
        )
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for feed in feed_rows:
        source, target = _split_key(feed.get("normalized_pair_key") or "")
        if not source or not target or source == target:
            continue
        reverse_key = f"{target}>>{source}"
        reverse = normalized.get(reverse_key)
        direct = normalized.get(feed.get("normalized_pair_key") or "")
        if not reverse:
            continue
        reverse_weight = _int(reverse.get("aggregate_edge_weight"))
        reverse_records = _int(reverse.get("source_record_count"))
        if reverse_weight < min_reverse_aggregate_weight or reverse_records < min_reverse_source_records:
            continue
        key = (str(feed.get("replacement_id") or ""), reverse_key)
        if key in seen:
            continue
        seen.add(key)
        direct_weight = _int((direct or {}).get("aggregate_edge_weight"))
        direct_records = _int((direct or {}).get("source_record_count"))
        severity = "high" if reverse_weight >= high_weight_threshold and reverse_weight >= max(1, direct_weight // 2) else "medium"
        if str(feed.get("provenance_review_status") or "").lower() in {"rejected", "retired"}:
            severity = "blocking"
        rows.append(
            {
                "conflict_id": _conflict_id(feed.get("replacement_id"), reverse_key),
                "severity": severity,
                "review_status": "open",
                "review_action": "review_directionality_before_scoring",
                "replacement_id": feed.get("replacement_id"),
                "normalized_pair_key": feed.get("normalized_pair_key"),
                "reverse_pair_key": reverse_key,
                "normalized_source_smiles": source,
                "normalized_target_smiles": target,
                "feed_edge_weight": feed.get("edge_weight"),
                "direct_aggregate_edge_weight": direct_weight,
                "direct_source_record_count": direct_records,
                "reverse_aggregate_edge_weight": reverse_weight,
                "reverse_source_record_count": reverse_records,
                "reverse_to_direct_weight_ratio": round(reverse_weight / max(1, direct_weight), 4),
                "source_name": feed.get("source_name"),
                "source_reference": feed.get("source_reference"),
                "source_confidence_tier": feed.get("source_confidence_tier"),
                "source_confidence_score": feed.get("source_confidence_score"),
                "source_owner": feed.get("source_owner"),
                "source_license": feed.get("source_license"),
                "provenance_level": feed.get("provenance_level"),
                "provenance_review_status": feed.get("provenance_review_status"),
                "row_sha256": feed.get("row_sha256"),
                "reverse_source_names": reverse.get("source_names"),
                "reverse_source_confidence_tiers": reverse.get("source_confidence_tiers"),
                "notes": (
                    "A governed feed row points opposite to an existing normalized pair with enough support. "
                    "Keep both as evidence, but require review before using this direction as a positive scoring prior."
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            {"blocking": 0, "high": 1, "medium": 2}.get(str(row.get("severity")), 9),
            -_int(row.get("reverse_aggregate_edge_weight")),
            str(row.get("normalized_pair_key") or ""),
        )
    )
    severity_counts: dict[str, int] = {}
    for row in rows:
        severity_counts[str(row.get("severity") or "unknown")] = severity_counts.get(str(row.get("severity") or "unknown"), 0) + 1
    reviews = load_rgroup_pair_contradiction_reviews(review_path) if review_path else {}
    if reviews:
        rows = [_merge_review(row, reviews.get(str(row.get("conflict_id") or ""))) for row in rows]
    review_status_counts: dict[str, int] = {}
    open_high_priority_count = 0
    for row in rows:
        decision = str(row.get("review_decision") or "pending_review")
        review_status_counts[decision] = review_status_counts.get(decision, 0) + 1
        if decision == "pending_review" and str(row.get("severity") or "") in {"blocking", "high"}:
            open_high_priority_count += 1
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "review_required" if rows else "empty",
        "row_count": len(rows),
        "high_priority_count": severity_counts.get("high", 0) + severity_counts.get("blocking", 0),
        "blocking_count": severity_counts.get("blocking", 0),
        "severity_counts": severity_counts,
        "review_status_counts": review_status_counts,
        "open_high_priority_count": open_high_priority_count,
        "review_path": str(review_path) if review_path else "",
        "min_reverse_aggregate_weight": min_reverse_aggregate_weight,
        "min_reverse_source_records": min_reverse_source_records,
        "high_weight_threshold": high_weight_threshold,
        "rows": rows,
        "recommended_next_actions": [
            "Review high and blocking conflicts before promoting the feed direction into score-positive priors.",
            "Resolve true bidirectional bioisosteric moves as context-dependent rather than globally positive.",
            "Raise source-confidence or mark rows deferred/rejected after review so expansion remains traceable.",
        ],
    }


def write_rgroup_normalized_pair_contradiction_report(
    report: dict,
    json_path: str | Path = DEFAULT_CONTRADICTION_REPORT_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_CONTRADICTION_CSV_PATH,
) -> None:
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    rows = [dict(row) for row in report.get("rows") or []]
    fields = [
        "conflict_id",
        "severity",
        "review_status",
        "review_action",
        "review_decision",
        "resolution_class",
        "score_policy_action",
        "source_confidence_action",
        "reviewer",
        "reviewed_at",
        "review_note",
        "replacement_id",
        "normalized_pair_key",
        "reverse_pair_key",
        "direct_aggregate_edge_weight",
        "reverse_aggregate_edge_weight",
        "reverse_to_direct_weight_ratio",
        "source_name",
        "source_confidence_tier",
        "provenance_review_status",
        "reverse_source_names",
        "notes",
    ]
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_rgroup_pair_contradiction_review_template(
    report: dict | str | Path,
    *,
    review_path: str | Path = DEFAULT_CONTRADICTION_REVIEW_PATH,
) -> dict:
    payload = json.loads(Path(report).read_text(encoding="utf-8")) if isinstance(report, (str, Path)) else dict(report or {})
    existing = load_rgroup_pair_contradiction_reviews(review_path)
    rows = [_merge_review(dict(row), existing.get(str(row.get("conflict_id") or ""))) for row in payload.get("rows") or []]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "row_count": len(rows),
        "review_path": str(review_path),
        "rows": rows,
    }


def write_rgroup_pair_contradiction_review_template(
    report: dict,
    path: str | Path = DEFAULT_CONTRADICTION_REVIEW_PATH,
) -> None:
    preferred = [
        "conflict_id",
        "severity",
        "review_decision",
        "resolution_class",
        "score_policy_action",
        "source_confidence_action",
        "reviewer",
        "reviewed_at",
        "review_note",
        "replacement_id",
        "normalized_pair_key",
        "reverse_pair_key",
        "direct_aggregate_edge_weight",
        "reverse_aggregate_edge_weight",
        "reverse_to_direct_weight_ratio",
        "source_name",
        "source_confidence_tier",
        "provenance_review_status",
        "reverse_source_names",
    ]
    _write_csv_rows([dict(row) for row in report.get("rows") or []], path, preferred)


def update_rgroup_pair_contradiction_review(
    conflict_id: str,
    *,
    decision: str,
    reviewer: str,
    review_note: str = "",
    resolution_class: str = "",
    score_policy_action: str = "",
    source_confidence_action: str = "",
    review_path: str | Path = DEFAULT_CONTRADICTION_REVIEW_PATH,
    report: dict | str | Path | None = DEFAULT_CONTRADICTION_REPORT_PATH,
) -> dict:
    normalized = str(decision or "").strip().lower()
    if normalized not in PAIR_CONTRADICTION_REVIEW_DECISIONS:
        raise ValueError(f"Unsupported pair contradiction decision: {decision}")
    if not reviewer:
        raise ValueError("reviewer is required")
    rows = _read_csv_rows(review_path)
    if not rows and report is not None:
        template = build_rgroup_pair_contradiction_review_template(report, review_path=review_path)
        rows = [dict(row) for row in template.get("rows") or []]
    updated = False
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        if str(row.get("conflict_id") or "").strip() != conflict_id:
            continue
        row["review_decision"] = normalized
        row["reviewer"] = reviewer
        row["reviewed_at"] = now
        row["review_note"] = review_note
        if resolution_class:
            row["resolution_class"] = resolution_class
        if score_policy_action:
            row["score_policy_action"] = score_policy_action
        if source_confidence_action:
            row["source_confidence_action"] = source_confidence_action
        updated = True
        break
    if not updated:
        raise ValueError(f"conflict_id not found in review template: {conflict_id}")
    write_rgroup_pair_contradiction_review_template({"rows": rows}, review_path)
    return {"status": "updated", "conflict_id": conflict_id, "decision": normalized, "review_path": str(review_path), "row_count": len(rows)}


def apply_rgroup_pair_contradiction_first_pass(
    report: dict | str | Path,
    *,
    reviewer: str,
    review_path: str | Path = DEFAULT_CONTRADICTION_REVIEW_PATH,
    overwrite: bool = False,
) -> dict:
    if not reviewer:
        raise ValueError("reviewer is required")
    template = build_rgroup_pair_contradiction_review_template(report, review_path=review_path)
    rows = []
    now = datetime.now(timezone.utc).isoformat()
    changed = 0
    for row in template.get("rows") or []:
        item = dict(row)
        current = str(item.get("review_decision") or "pending_review")
        if overwrite or current == "pending_review":
            decision = _first_pass_decision(item)
            item.update(decision)
            item["reviewer"] = reviewer
            item["reviewed_at"] = now
            changed += 1
        rows.append(item)
    write_rgroup_pair_contradiction_review_template({"rows": rows}, review_path)
    return build_rgroup_pair_contradiction_decision_summary({"rows": rows}, review_path=review_path, rows_changed=changed)


def build_rgroup_pair_contradiction_decision_summary(
    report: dict | str | Path,
    *,
    review_path: str | Path = DEFAULT_CONTRADICTION_REVIEW_PATH,
    rows_changed: int = 0,
) -> dict:
    payload = json.loads(Path(report).read_text(encoding="utf-8")) if isinstance(report, (str, Path)) else dict(report or {})
    rows = [dict(row) for row in payload.get("rows") or []]
    if not rows:
        rows = list(load_rgroup_pair_contradiction_reviews(review_path).values())
    decision_counts: dict[str, int] = {}
    severity_decision_counts: dict[str, int] = {}
    open_high = 0
    blocking_unresolved = 0
    for row in rows:
        decision = str(row.get("review_decision") or "pending_review")
        severity = str(row.get("severity") or "unknown")
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
        severity_decision_counts[f"{severity}:{decision}"] = severity_decision_counts.get(f"{severity}:{decision}", 0) + 1
        if decision == "pending_review" and severity in {"blocking", "high"}:
            open_high += 1
        if severity == "blocking" and decision not in {"reject_feed_direction", "reference_only_watch"}:
            blocking_unresolved += 1
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "review_complete" if rows and open_high == 0 and blocking_unresolved == 0 else "review_required" if rows else "empty",
        "row_count": len(rows),
        "rows_changed": rows_changed,
        "decision_counts": decision_counts,
        "severity_decision_counts": severity_decision_counts,
        "open_high_priority_count": open_high,
        "blocking_unresolved_count": blocking_unresolved,
        "review_path": str(review_path),
        "recommended_next_actions": [
            "Keep context-dependent and bidirectional rows out of global positive priors unless endpoint/project evidence matches.",
            "Resolve deferred source rows with source owners before raising source confidence.",
            "Rebuild the contradiction report after every large feed onboarding batch.",
        ],
    }


def write_rgroup_pair_contradiction_decision_summary(
    summary: dict,
    path: str | Path = DEFAULT_CONTRADICTION_DECISION_SUMMARY_PATH,
) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def _owner_action(row: dict) -> str:
    tier = str(row.get("source_confidence_tier") or "").lower()
    provenance = str(row.get("provenance_review_status") or "").lower()
    if "patent" in tier or "provisional" in provenance:
        return "confirm_patent_provenance_or_keep_deferred"
    if provenance in {"deferred", "deferred_review"}:
        return "confirm_source_review_or_keep_deferred"
    return "confirm_confidence_before_positive_prior"


def _owner_decision_rows(path: str | Path = DEFAULT_PAIR_CONFLICT_OWNER_DECISION_LEDGER_CSV_PATH) -> dict[str, dict]:
    rows = _read_csv_rows(path)
    out = {}
    for row in rows:
        for key in _owner_decision_reuse_keys(row, owner_review_id=str(row.get("owner_review_id") or "")):
            out.setdefault(key, row)
    return out


def _owner_decision_reuse_keys(row: dict, *, owner_review_id: str = "") -> list[str]:
    keys = []
    for field in ["owner_review_id", "conflict_id", "row_sha256"]:
        value = owner_review_id if field == "owner_review_id" else str(row.get(field) or "").strip()
        if value:
            keys.append(f"{field}:{value}")
            keys.append(value)
    source_owner = str(row.get("source_owner") or "").strip()
    source_name = str(row.get("source_name") or "").strip()
    normalized_pair = str(row.get("normalized_pair_key") or "").strip()
    reverse_pair = str(row.get("reverse_pair_key") or "").strip()
    row_sha = str(row.get("row_sha256") or "").strip()
    if source_owner and row_sha:
        keys.append(f"source_owner_row_sha256:{source_owner}|{row_sha}")
    if source_owner and normalized_pair:
        keys.append(f"source_owner_normalized_pair:{source_owner}|{normalized_pair}")
    if source_owner and normalized_pair and reverse_pair:
        keys.append(f"source_owner_pair_direction:{source_owner}|{normalized_pair}|{reverse_pair}")
    if source_name and normalized_pair:
        keys.append(f"source_name_normalized_pair:{source_name}|{normalized_pair}")
    return keys


def _match_owner_decision(owner_decisions: dict[str, dict], row: dict, *, owner_review_id: str) -> tuple[dict, str, str]:
    for key in _owner_decision_reuse_keys(row, owner_review_id=owner_review_id):
        if key in owner_decisions:
            basis = key.split(":", 1)[0] if ":" in key else "direct_id"
            return owner_decisions[key], basis, key
    return {}, "", ""


def build_rgroup_pair_conflict_owner_review_packet(
    report: dict | str | Path = DEFAULT_CONTRADICTION_REPORT_PATH,
    *,
    review_path: str | Path = DEFAULT_CONTRADICTION_REVIEW_PATH,
    owner_decision_ledger_path: str | Path = DEFAULT_PAIR_CONFLICT_OWNER_DECISION_LEDGER_CSV_PATH,
) -> dict:
    payload = json.loads(Path(report).read_text(encoding="utf-8")) if isinstance(report, (str, Path)) and Path(report).exists() else dict(report or {}) if not isinstance(report, (str, Path)) else {}
    rows = [dict(row) for row in payload.get("rows") or []]
    reviews = load_rgroup_pair_contradiction_reviews(review_path)
    if rows:
        rows = [_merge_review(row, reviews.get(str(row.get("conflict_id") or ""))) for row in rows]
    elif reviews:
        rows = list(reviews.values())
    deferred = [row for row in rows if str(row.get("review_decision") or "").strip().lower() == "defer_source_review"]
    packet_rows = []
    owner_counts: dict[str, int] = {}
    tier_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    owner_decisions = _owner_decision_rows(owner_decision_ledger_path)
    for row in deferred:
        owner = str(row.get("source_owner") or "unassigned_source_owner")
        tier = str(row.get("source_confidence_tier") or "unspecified")
        severity = str(row.get("severity") or "unknown")
        owner_counts[owner] = owner_counts.get(owner, 0) + 1
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        owner_review_id = f"RGOWNER-{str(row.get('conflict_id') or '').replace('RGCON-', '')}"
        owner_decision, match_basis, match_key = _match_owner_decision(owner_decisions, row, owner_review_id=owner_review_id)
        decision = str(owner_decision.get("owner_decision") or "pending_owner_review").strip().lower()
        if decision not in PAIR_CONFLICT_OWNER_DECISIONS:
            decision = "pending_owner_review"
        packet_rows.append(
            {
                "owner_review_id": owner_review_id,
                "conflict_id": row.get("conflict_id"),
                "severity": severity,
                "source_owner": owner,
                "source_name": row.get("source_name") or "",
                "source_confidence_tier": tier,
                "provenance_review_status": row.get("provenance_review_status") or "",
                "replacement_id": row.get("replacement_id") or "",
                "normalized_pair_key": row.get("normalized_pair_key") or "",
                "reverse_pair_key": row.get("reverse_pair_key") or "",
                "direct_aggregate_edge_weight": row.get("direct_aggregate_edge_weight") or "",
                "reverse_aggregate_edge_weight": row.get("reverse_aggregate_edge_weight") or "",
                "reverse_to_direct_weight_ratio": row.get("reverse_to_direct_weight_ratio") or "",
                "current_review_decision": row.get("review_decision") or "",
                "current_score_policy_action": row.get("score_policy_action") or "",
                "current_source_confidence_action": row.get("source_confidence_action") or "",
                "recommended_owner_action": _owner_action(row),
                "allowed_owner_decisions": "raise_confidence_and_resolve|keep_deferred|reject_feed_direction",
                "owner_decision": decision,
                "owner_reviewer": owner_decision.get("owner_reviewer") or "",
                "owner_reviewed_at": owner_decision.get("owner_reviewed_at") or "",
                "owner_review_note": owner_decision.get("owner_review_note") or "",
                "owner_decision_match_basis": match_basis,
                "owner_decision_match_key": match_key,
                "source_reference": row.get("source_reference") or "",
                "row_sha256": row.get("row_sha256") or "",
            }
        )
    packet_rows.sort(key=lambda row: (row["source_owner"], row["source_confidence_tier"], row["severity"], row["conflict_id"]))
    owner_decision_counts: dict[str, int] = {}
    for row in packet_rows:
        decision = str(row.get("owner_decision") or "pending_owner_review")
        owner_decision_counts[decision] = owner_decision_counts.get(decision, 0) + 1
    pending_owner_count = owner_decision_counts.get("pending_owner_review", 0)
    if not packet_rows:
        status = "closed"
    elif pending_owner_count:
        status = "owner_review_required"
    else:
        status = "owner_review_recorded"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "deferred_conflict_count": len(packet_rows),
        "pending_owner_review_count": pending_owner_count,
        "owner_decision_recorded_count": len(packet_rows) - pending_owner_count,
        "owner_count": len(owner_counts),
        "owner_counts": owner_counts,
        "owner_decision_counts": owner_decision_counts,
        "source_confidence_tier_counts": tier_counts,
        "severity_counts": severity_counts,
        "review_path": str(review_path),
        "owner_decision_ledger_path": str(owner_decision_ledger_path),
        "rows": packet_rows,
        "recommended_next_actions": [
            "Send each owner-scoped packet row to the source owner before raising confidence or reversing the first-pass decision.",
            "Keep deferred rows out of global positive priors while owner_decision remains pending_owner_review.",
            "After owner sign-off, update the pair contradiction review row as context_dependent, reject_feed_direction, or accepted_bidirectional.",
        ],
    }


def write_rgroup_pair_conflict_owner_review_packet(
    packet: dict,
    *,
    json_path: str | Path = DEFAULT_PAIR_CONFLICT_OWNER_REVIEW_PACKET_PATH,
    csv_path: str | Path | None = DEFAULT_PAIR_CONFLICT_OWNER_REVIEW_PACKET_CSV_PATH,
) -> None:
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")
    if not csv_path:
        return
    rows = [dict(row) for row in packet.get("rows") or []]
    fields = [
        "owner_review_id",
        "conflict_id",
        "severity",
        "source_owner",
        "source_name",
        "source_confidence_tier",
        "provenance_review_status",
        "replacement_id",
        "normalized_pair_key",
        "reverse_pair_key",
        "direct_aggregate_edge_weight",
        "reverse_aggregate_edge_weight",
        "reverse_to_direct_weight_ratio",
        "current_review_decision",
        "current_score_policy_action",
        "current_source_confidence_action",
        "recommended_owner_action",
        "allowed_owner_decisions",
        "owner_decision",
        "owner_reviewer",
        "owner_reviewed_at",
        "owner_review_note",
        "owner_decision_match_basis",
        "owner_decision_match_key",
        "source_reference",
        "row_sha256",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _review_update_for_owner_decision(row: dict) -> dict:
    owner_decision = str(row.get("owner_decision") or "pending_owner_review").strip().lower()
    note = str(row.get("owner_review_note") or "").strip()
    if owner_decision == "keep_deferred":
        return {
            "decision": "defer_source_review",
            "resolution_class": "provisional_source_owner_keep_deferred",
            "score_policy_action": "hold_feed_direction_out_of_positive_prior",
            "source_confidence_action": "keep_deferred_until_owner_review",
            "review_note": note or "Source-owner packet decision keeps this provisional direction deferred from positive priors.",
        }
    if owner_decision == "raise_confidence_and_resolve":
        return {
            "decision": "context_dependent",
            "resolution_class": "owner_confirmed_context_dependent",
            "score_policy_action": "use_only_with_endpoint_or_project_context",
            "source_confidence_action": "owner_confirmed_raise_confidence",
            "review_note": note or "Source-owner packet confirms the source can be retained as context-dependent evidence.",
        }
    if owner_decision == "reject_feed_direction":
        return {
            "decision": "reject_feed_direction",
            "resolution_class": "owner_rejected_feed_direction",
            "score_policy_action": "exclude_feed_direction_from_positive_prior",
            "source_confidence_action": "owner_confirmed_reject_direction",
            "review_note": note or "Source-owner packet rejects this feed direction for scoring.",
        }
    return {}


def build_rgroup_pair_conflict_owner_decision_ledger(
    packet: dict | str | Path = DEFAULT_PAIR_CONFLICT_OWNER_REVIEW_PACKET_PATH,
    *,
    reviewer: str = "",
    mark_all_keep_deferred: bool = False,
    apply_to_reviews: bool = False,
    review_path: str | Path = DEFAULT_CONTRADICTION_REVIEW_PATH,
    contradiction_report: dict | str | Path | None = DEFAULT_CONTRADICTION_REPORT_PATH,
) -> dict:
    payload = json.loads(Path(packet).read_text(encoding="utf-8")) if isinstance(packet, (str, Path)) and Path(packet).exists() else dict(packet or {}) if not isinstance(packet, (str, Path)) else {}
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    applied = 0
    skipped_pending = 0
    for raw in payload.get("rows") or []:
        row = dict(raw)
        decision = str(row.get("owner_decision") or "pending_owner_review").strip().lower()
        if mark_all_keep_deferred and decision == "pending_owner_review":
            decision = "keep_deferred"
            row["owner_decision"] = decision
            row["owner_reviewer"] = reviewer
            row["owner_reviewed_at"] = now
            row["owner_review_note"] = row.get("owner_review_note") or "Conservative production hold: keep provisional source direction deferred until source-owner evidence supports a stronger decision."
        if decision not in PAIR_CONFLICT_OWNER_DECISIONS:
            raise ValueError(f"Unsupported owner decision: {decision}")
        if decision == "pending_owner_review":
            skipped_pending += 1
        elif apply_to_reviews:
            update = _review_update_for_owner_decision(row)
            if update:
                update_rgroup_pair_contradiction_review(
                    str(row.get("conflict_id") or ""),
                    decision=update["decision"],
                    reviewer=row.get("owner_reviewer") or reviewer or "source_owner_decision_ledger",
                    review_note=update["review_note"],
                    resolution_class=update["resolution_class"],
                    score_policy_action=update["score_policy_action"],
                    source_confidence_action=update["source_confidence_action"],
                    review_path=review_path,
                    report=contradiction_report,
                )
                applied += 1
        rows.append(
            {
                "owner_review_id": row.get("owner_review_id") or "",
                "conflict_id": row.get("conflict_id") or "",
                "source_owner": row.get("source_owner") or "",
                "source_name": row.get("source_name") or "",
                "source_confidence_tier": row.get("source_confidence_tier") or "",
                "provenance_review_status": row.get("provenance_review_status") or "",
                "replacement_id": row.get("replacement_id") or "",
                "normalized_pair_key": row.get("normalized_pair_key") or "",
                "reverse_pair_key": row.get("reverse_pair_key") or "",
                "owner_decision": decision,
                "owner_reviewer": row.get("owner_reviewer") or "",
                "owner_reviewed_at": row.get("owner_reviewed_at") or "",
                "owner_review_note": row.get("owner_review_note") or "",
                "owner_decision_match_basis": row.get("owner_decision_match_basis") or "",
                "owner_decision_match_key": row.get("owner_decision_match_key") or "",
                "source_reference": row.get("source_reference") or "",
                "row_sha256": row.get("row_sha256") or "",
                "review_apply_status": "applied_to_pair_review" if apply_to_reviews and decision != "pending_owner_review" else "pending_owner_review" if decision == "pending_owner_review" else "recorded_not_applied",
            }
        )
    decision_counts: dict[str, int] = {}
    for row in rows:
        decision = str(row.get("owner_decision") or "pending_owner_review")
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
    if not rows:
        status = "closed_no_deferred_conflicts"
    elif decision_counts.get("pending_owner_review"):
        status = "owner_review_pending"
    elif set(decision_counts) == {"keep_deferred"}:
        status = "all_kept_deferred"
    else:
        status = "owner_decisions_applied" if applied else "owner_decisions_recorded"
    return {
        "created_at": now,
        "status": status,
        "row_count": len(rows),
        "decision_counts": decision_counts,
        "applied_to_pair_review_count": applied,
        "pending_owner_review_count": skipped_pending,
        "review_path": str(review_path),
        "rows": rows,
        "recommended_next_actions": [
            "Use keep_deferred for provisional sources when owner evidence is insufficient.",
            "Use raise_confidence_and_resolve only with explicit owner evidence and retain context-dependent scoring.",
            "Use reject_feed_direction when owner review identifies a source-quality or directionality problem.",
        ],
    }


def write_rgroup_pair_conflict_owner_decision_ledger(
    ledger: dict,
    *,
    json_path: str | Path = DEFAULT_PAIR_CONFLICT_OWNER_DECISION_LEDGER_PATH,
    csv_path: str | Path | None = DEFAULT_PAIR_CONFLICT_OWNER_DECISION_LEDGER_CSV_PATH,
) -> None:
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")
    if not csv_path:
        return
    rows = [dict(row) for row in ledger.get("rows") or []]
    fields = [
        "owner_review_id",
        "conflict_id",
        "source_owner",
        "source_name",
        "source_confidence_tier",
        "provenance_review_status",
        "replacement_id",
        "normalized_pair_key",
        "reverse_pair_key",
        "owner_decision",
        "owner_reviewer",
        "owner_reviewed_at",
        "owner_review_note",
        "owner_decision_match_basis",
        "owner_decision_match_key",
        "source_reference",
        "row_sha256",
        "review_apply_status",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
