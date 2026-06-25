from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .database import initialize_database, insert_route_quote_requests, update_project_route_batch_status, upsert_project_route_batches


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")
DECISION_STATUSES = ["unreviewed", "shortlisted", "rejected", "selected", "deferred"]
ROUTE_BATCH_STATUSES = ["needs_chemist_review", "approved", "ordered", "blocked", "completed"]


def _model_context(result: dict) -> dict:
    profile = result.get("scoring_profile") or {}
    calibration = profile.get("calibration") or {}
    return {
        "scoring_profile_id": profile.get("profile_id") or result.get("scoring_profile_id"),
        "scoring_profile_path": profile.get("path") or profile.get("_path") or result.get("scoring_profile_path"),
        "calibration_id": calibration.get("calibration_id") or result.get("calibration_id"),
        "calibration_endpoint_group": calibration.get("endpoint_group") or result.get("calibration_endpoint_group"),
        "calibration_created_at": calibration.get("created_at") or result.get("calibration_created_at"),
        "profile": profile,
    }


def save_project_run(
    result: dict,
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str = "default",
    note: str | None = None,
    filters: dict | None = None,
    run_id: str | None = None,
) -> str:
    conn = initialize_database(db_path)
    try:
        run_id = run_id or f"RUN-{uuid.uuid4().hex[:12].upper()}"
        selected_site = result.get("selected_site") or {}
        created_at = datetime.now(timezone.utc).isoformat()
        model_context = _model_context(result)
        conn.execute(
            """
            INSERT OR REPLACE INTO project_run (
                run_id, project_name, parent_smiles, direction, site_id, site_type,
                filters_json, score_weights_json, scoring_profile_id, scoring_profile_path,
                calibration_id, calibration_endpoint_group, calibration_created_at,
                model_context_json, analysis_json, note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                project_name,
                result.get("parent_smiles"),
                (result.get("candidates") or [{}])[0].get("direction") if result.get("candidates") else None,
                selected_site.get("site_id"),
                selected_site.get("site_type"),
                json.dumps(filters or {}, sort_keys=True),
                json.dumps(result.get("score_weights") or {}, sort_keys=True),
                model_context.get("scoring_profile_id"),
                model_context.get("scoring_profile_path"),
                model_context.get("calibration_id"),
                model_context.get("calibration_endpoint_group"),
                model_context.get("calibration_created_at"),
                json.dumps(model_context, sort_keys=True),
                json.dumps(result.get("analysis") or {}, sort_keys=True),
                note,
                created_at,
            ),
        )
        for row in result.get("candidates") or []:
            conn.execute(
                """
                INSERT OR REPLACE INTO project_candidate (
                    run_id, candidate_id, smiles, rank, score, cluster_id,
                    cluster_representative, enumeration_type, replacement_label,
                    decision_status, note, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(
                    (SELECT decision_status FROM project_candidate WHERE run_id=? AND candidate_id=?),
                    'unreviewed'
                ), COALESCE(
                    (SELECT note FROM project_candidate WHERE run_id=? AND candidate_id=?),
                    ''
                ), ?)
                """,
                (
                    run_id,
                    row.get("candidate_id"),
                    row.get("smiles"),
                    row.get("rank"),
                    row.get("score"),
                    str(row.get("cluster_id")) if row.get("cluster_id") is not None else None,
                    1 if row.get("cluster_representative") else 0,
                    row.get("enumeration_type"),
                    row.get("replacement_label"),
                    run_id,
                    row.get("candidate_id"),
                    run_id,
                    row.get("candidate_id"),
                    json.dumps(row, sort_keys=True),
                ),
            )
        batches = ((result.get("analysis") or {}).get("route_batch_summary") or {}).get("batches") or []
        if batches:
            upsert_project_route_batches(conn, run_id, batches)
            quote_rows = []
            for batch in batches:
                execution = batch.get("execution") or {}
                if not execution.get("quote_request_id"):
                    continue
                quote_rows.append(
                    {
                        "quote_request_id": execution.get("quote_request_id"),
                        "run_id": run_id,
                        "route_batch_id": batch.get("route_batch_id"),
                        "vendor_name": execution.get("vendor_name") or "unassigned",
                        "request_status": execution.get("quote_status"),
                        "catalog_urls": execution.get("catalog_urls") or [],
                        "reagent_overlap_score": execution.get("reagent_overlap_score"),
                        "protecting_group_risk": execution.get("protecting_group_risk"),
                        "regioselectivity_risk": execution.get("regioselectivity_risk"),
                        "purification_risk": execution.get("purification_risk"),
                        "route_execution_risk_score": execution.get("route_execution_risk_score"),
                        "payload": execution,
                    }
                )
            if quote_rows:
                insert_route_quote_requests(conn, quote_rows)
        conn.commit()
        return run_id
    finally:
        conn.close()


def list_project_runs(db_path: str | Path = DEFAULT_DB_PATH, project_name: str | None = None) -> list[dict]:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if project_name:
            rows = conn.execute(
                "SELECT * FROM project_run WHERE project_name=? ORDER BY created_at DESC",
                (project_name,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM project_run ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def load_project_candidates(db_path: str | Path, run_id: str) -> list[dict]:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM project_candidate WHERE run_id=? ORDER BY rank ASC",
            (run_id,),
        ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            payload = json.loads(item.pop("payload_json") or "{}")
            payload["decision_status"] = item.get("decision_status")
            payload["project_note"] = item.get("note")
            results.append(payload)
        return results
    finally:
        conn.close()


def update_candidate_decision(
    db_path: str | Path,
    run_id: str,
    candidate_id: str,
    *,
    decision_status: str,
    note: str | None = None,
) -> None:
    if decision_status not in DECISION_STATUSES:
        raise ValueError(f"Unsupported decision status: {decision_status}")
    conn = initialize_database(db_path)
    try:
        conn.execute(
            """
            UPDATE project_candidate
            SET decision_status=?, note=?
            WHERE run_id=? AND candidate_id=?
            """,
            (decision_status, note or "", run_id, candidate_id),
        )
        conn.commit()
    finally:
        conn.close()


def load_project_route_batches(db_path: str | Path, run_id: str) -> list[dict]:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM project_route_batch WHERE run_id=? ORDER BY route_batch_id ASC",
            (run_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_route_batch_decision(
    db_path: str | Path,
    run_id: str,
    route_batch_id: str,
    *,
    status: str,
    note: str | None = None,
) -> None:
    if status not in ROUTE_BATCH_STATUSES:
        raise ValueError(f"Unsupported route batch status: {status}")
    conn = initialize_database(db_path)
    try:
        update_project_route_batch_status(conn, run_id, route_batch_id, status=status, note=note)
    finally:
        conn.close()
