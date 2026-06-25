from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import yaml


DEFAULT_SCAFFOLD_RULE_REVIEW_PATH = Path(__file__).resolve().parents[2] / "data" / "rules" / "scaffold_rule_reviews.yaml"
SCAFFOLD_RULE_REVIEW_STATUSES = ["active", "watch", "tuned", "blocked"]
SCAFFOLD_RULE_RESOLUTION_STATUSES = ["open", "accepted", "rejected", "needs_more_data", "retired"]


def load_scaffold_rule_reviews(path: str | Path | None = None) -> dict:
    review_path = Path(path) if path is not None else DEFAULT_SCAFFOLD_RULE_REVIEW_PATH
    if not review_path.exists():
        return {"version": "scaffold-rule-reviews-0.1", "reviews": []}
    with review_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if isinstance(data, list):
        data = {"version": "scaffold-rule-reviews-0.1", "reviews": data}
    data.setdefault("reviews", [])
    return data


def save_scaffold_rule_reviews(data: dict, path: str | Path | None = None) -> None:
    review_path = Path(path) if path is not None else DEFAULT_SCAFFOLD_RULE_REVIEW_PATH
    review_path.parent.mkdir(parents=True, exist_ok=True)
    with review_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=False)


def scaffold_rule_review_lookup(data: dict | None = None) -> dict[str, dict]:
    data = data or load_scaffold_rule_reviews()
    return {str(item.get("scaffold_rule_id")): item for item in data.get("reviews") or [] if item.get("scaffold_rule_id")}


def apply_scaffold_rule_reviews_to_rules(rules: list[dict], review_data: dict | None = None) -> list[dict]:
    lookup = scaffold_rule_review_lookup(review_data)
    filtered = []
    for rule in rules:
        rule_id = str(rule.get("scaffold_rule_id") or "")
        review = lookup.get(rule_id) or {}
        status = str(review.get("status") or "active")
        if status == "blocked":
            continue
        filtered.append({**rule, "review_overlay": review})
    return filtered


def apply_scaffold_rule_review_to_row(row: dict, review_lookup: dict[str, dict]) -> dict:
    rule_id = str(row.get("scaffold_rule_id") or "")
    review = review_lookup.get(rule_id) or {}
    if not review:
        return row
    out = dict(row)
    status = str(review.get("status") or "active")
    adjustment = float(review.get("score_adjustment") or 0.0)
    out["scaffold_rule_review_status"] = status
    out["scaffold_rule_review_note"] = review.get("note")
    out["scaffold_rule_review_adjustment"] = adjustment
    if out.get("scaffold_context_score") is not None and adjustment:
        score = max(0.0, min(100.0, float(out.get("scaffold_context_score") or 0.0) + adjustment))
        out["scaffold_context_score_raw_review"] = out.get("scaffold_context_score")
        out["scaffold_context_score"] = round(score, 2)
    if status in {"watch", "tuned"}:
        flags = [flag for flag in str(out.get("scaffold_context_flags") or "").split(";") if flag]
        flags.append(f"rule_review_{status}")
        out["scaffold_context_flags"] = ";".join(dict.fromkeys(flags))
    return out


def update_scaffold_rule_review(
    scaffold_rule_id: str,
    *,
    status: str,
    reviewer: str | None = None,
    owner: str | None = None,
    resolution_status: str | None = None,
    rule_version: str | None = None,
    note: str | None = None,
    score_adjustment: float = 0.0,
    path: str | Path | None = None,
    db_path: str | Path | None = None,
) -> dict:
    if status not in SCAFFOLD_RULE_REVIEW_STATUSES:
        raise ValueError(f"Unsupported scaffold rule review status: {status}")
    if resolution_status and resolution_status not in SCAFFOLD_RULE_RESOLUTION_STATUSES:
        raise ValueError(f"Unsupported scaffold rule resolution status: {resolution_status}")
    data = load_scaffold_rule_reviews(path)
    reviews = [item for item in data.get("reviews") or [] if str(item.get("scaffold_rule_id")) != str(scaffold_rule_id)]
    now = datetime.now(timezone.utc).isoformat()
    review = {
        "scaffold_rule_id": scaffold_rule_id,
        "status": status,
        "reviewed_by": reviewer,
        "owner": owner or "",
        "resolution_status": resolution_status or "open",
        "rule_version": rule_version or data.get("version") or "unspecified",
        "reviewed_at": now,
        "score_adjustment": float(score_adjustment or 0.0),
        "note": note or "",
    }
    event_digest = hashlib.sha1(
        "|".join(
            [
                str(scaffold_rule_id),
                status,
                reviewer or "",
                owner or "",
                resolution_status or "open",
                rule_version or "",
                str(score_adjustment or 0.0),
                note or "",
                now,
            ]
        ).encode("utf-8")
    ).hexdigest()[:12].upper()
    review["event_id"] = f"SCREV-{event_digest}"
    reviews.append(review)
    data["reviews"] = sorted(reviews, key=lambda item: str(item.get("scaffold_rule_id") or ""))
    save_scaffold_rule_reviews(data, path)
    if db_path is not None:
        from .database import initialize_database, insert_scaffold_rule_review_event

        conn = initialize_database(db_path)
        try:
            insert_scaffold_rule_review_event(conn, review)
        finally:
            conn.close()
    return review


def list_scaffold_rule_review_events(
    *,
    db_path: str | Path,
    scaffold_rule_id: str | None = None,
    limit: int = 200,
) -> list[dict]:
    from .database import initialize_database

    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        params: list[object] = []
        where = ""
        if scaffold_rule_id:
            where = "WHERE scaffold_rule_id=?"
            params.append(scaffold_rule_id)
        params.append(int(limit))
        rows = conn.execute(
            f"""
            SELECT event_id, scaffold_rule_id, status, reviewer, score_adjustment,
                   note, created_at, payload_json
            FROM scaffold_rule_review_event
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        events = []
        for row in rows:
            item = dict(row)
            try:
                payload = json.loads(item.get("payload_json") or "{}")
            except Exception:
                payload = {}
            item["owner"] = payload.get("owner") or ""
            item["resolution_status"] = payload.get("resolution_status") or "open"
            item["rule_version"] = payload.get("rule_version") or ""
            linked_ids = payload.get("linked_candidate_ids") or payload.get("candidate_ids") or []
            if isinstance(linked_ids, str):
                linked_ids = [linked_ids]
            item["linked_candidate_ids"] = ";".join(str(value) for value in linked_ids)
            events.append(item)
        return events
    finally:
        conn.close()
