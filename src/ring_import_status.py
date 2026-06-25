from __future__ import annotations

import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .database import initialize_database
from .ring_library import DEFAULT_RING_IMPORT_STATE_PATH, load_import_state


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")
DEFAULT_REPORT_PATH = Path("data/substituents/ertl_ring_chunk_import_report.json")
DEFAULT_RAW_PATH = Path("data/raw/literature/ertl_4m_rings.zip")
DEFAULT_ESTIMATED_ERTL_TOTAL = 3_931_782


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def count_ertl_source_records(raw_path: str | Path = DEFAULT_RAW_PATH) -> int:
    count = 0
    with zipfile.ZipFile(raw_path) as archive:
        with archive.open("rings.smi") as handle:
            for raw in handle:
                line = raw.decode("utf-8", errors="replace").strip()
                if line and not line.startswith("#"):
                    count += 1
    return count


def _db_ring_counts(db_path: str | Path) -> dict:
    if not Path(db_path).exists():
        return {"ring_system_count": 0, "ertl_ring_system_count": 0, "ertl_max_source_rank": 0}
    conn = initialize_database(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM ring_system").fetchone()[0]
        ertl = conn.execute("SELECT COUNT(*) FROM ring_system WHERE source_dataset='ertl_4m_ring_systems'").fetchone()[0]
        max_rank = conn.execute(
            "SELECT COALESCE(MAX(source_rank), 0) FROM ring_system WHERE source_dataset='ertl_4m_ring_systems'"
        ).fetchone()[0]
    except sqlite3.Error:
        total = 0
        ertl = 0
        max_rank = 0
    finally:
        conn.close()
    return {"ring_system_count": int(total), "ertl_ring_system_count": int(ertl), "ertl_max_source_rank": int(max_rank or 0)}


def _checkpoint_integrity(ring_state: dict, latest_report: dict, raw_path: str | Path, *, db_max_source_rank: int = 0) -> dict:
    issues = []
    next_offset = max(
        int(ring_state.get("next_offset") or 0),
        int(latest_report.get("final_next_offset") or 0),
        int(db_max_source_rank or 0),
    )
    last_offset = ring_state.get("last_offset")
    last_imported = int(ring_state.get("last_imported_count") or latest_report.get("imported_total") or 0)
    if last_offset not in {None, ""}:
        last_offset_int = int(last_offset)
        if next_offset < last_offset_int:
            issues.append({"severity": "error", "check": "offset_order", "message": "next_offset is behind last_offset."})
        expected_next = last_offset_int + last_imported
        if last_imported and expected_next != next_offset:
            issues.append(
                {
                    "severity": "warning",
                    "check": "chunk_continuity",
                    "message": f"last_offset + last_imported_count ({expected_next}) differs from next_offset ({next_offset}).",
                }
            )
    report_next = latest_report.get("final_next_offset")
    if db_max_source_rank and db_max_source_rank > int(ring_state.get("next_offset") or 0):
        issues.append(
            {
                "severity": "warning",
                "check": "db_ahead_of_checkpoint",
                "message": "Database max Ertl source_rank is ahead of the saved checkpoint; run ring_import_status --repair-state-from-db.",
            }
        )
    if report_next not in {None, ""} and int(report_next) != next_offset:
        issues.append({"severity": "warning", "check": "report_state_mismatch", "message": "Latest chunk report offset differs from checkpoint state."})
    raw_file = Path(ring_state.get("source_path") or raw_path)
    if not raw_file.exists():
        issues.append({"severity": "warning", "check": "raw_source_exists", "message": f"Raw Ertl source is missing: {raw_file}"})
    if ring_state.get("last_error") or latest_report.get("error"):
        issues.append({"severity": "error", "check": "last_error", "message": str(ring_state.get("last_error") or latest_report.get("error"))})
    status = "error" if any(item["severity"] == "error" for item in issues) else "warning" if issues else "ok"
    return {
        "status": status,
        "issue_count": len(issues),
        "issues": issues,
        "source_path": str(raw_file),
        "source_sha256": ring_state.get("source_sha256"),
    }


def build_ring_import_status(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    state_path: str | Path = DEFAULT_RING_IMPORT_STATE_PATH,
    report_path: str | Path = DEFAULT_REPORT_PATH,
    raw_path: str | Path = DEFAULT_RAW_PATH,
    source_total: int | None = None,
    count_source: bool = False,
) -> dict:
    state = load_import_state(state_path)
    ring_state = state.get("ertl_4m_ring_systems") or {}
    latest_report = {}
    report_file = Path(report_path)
    if report_file.exists():
        latest_report = json.loads(report_file.read_text(encoding="utf-8"))

    db_counts = _db_ring_counts(db_path)
    if count_source:
        source_total = count_ertl_source_records(raw_path)
    source_total = int(source_total or ring_state.get("estimated_total_source_count") or DEFAULT_ESTIMATED_ERTL_TOTAL)
    next_offset = max(
        int(ring_state.get("next_offset") or 0),
        int(latest_report.get("final_next_offset") or 0),
        int(db_counts.get("ertl_max_source_rank") or 0),
    )
    remaining = max(source_total - next_offset, 0)

    finished_at = _parse_dt(ring_state.get("last_chunked_import_at"))
    throughput = ring_state.get("last_throughput_rings_per_second")
    if throughput in {None, ""}:
        throughput = latest_report.get("throughput_rings_per_second")
    try:
        throughput = float(throughput or 0.0)
    except (TypeError, ValueError):
        throughput = 0.0
    eta_seconds = int(remaining / throughput) if throughput > 0 and remaining else None
    eta_finished_at = None
    if eta_seconds is not None:
        eta_finished_at = datetime.now(timezone.utc).timestamp() + eta_seconds
        eta_finished_at = datetime.fromtimestamp(eta_finished_at, tz=timezone.utc).isoformat()

    last_error = ring_state.get("last_error") or latest_report.get("error")
    source_complete = bool(ring_state.get("exhausted")) or remaining == 0
    status = "failed" if last_error else "complete" if source_complete else "idle"
    stale_hours = None
    if finished_at:
        stale_hours = round((datetime.now(timezone.utc) - finished_at).total_seconds() / 3600.0, 3)

    return {
        "status": status,
        "source_total": source_total,
        "next_offset": next_offset,
        "remaining_source_records": remaining,
        "progress_fraction": round(next_offset / source_total, 6) if source_total else None,
        "progress_percent": round((next_offset / source_total) * 100.0, 3) if source_total else None,
        "last_imported_count": int(ring_state.get("last_imported_count") or latest_report.get("imported_total") or 0),
        "last_limit": ring_state.get("last_limit"),
        "last_offset": ring_state.get("last_offset"),
        "last_chunked_import_at": ring_state.get("last_chunked_import_at"),
        "hours_since_last_import": stale_hours,
        "last_runtime_seconds": ring_state.get("last_runtime_seconds") or latest_report.get("elapsed_seconds"),
        "last_throughput_rings_per_second": round(throughput, 3) if throughput else None,
        "eta_seconds": eta_seconds,
        "eta_finished_at": eta_finished_at,
        "continuous_mode": bool(ring_state.get("continuous_mode")),
        "exhausted": source_complete,
        "last_error": last_error,
        "checkpoint_integrity": _checkpoint_integrity(
            ring_state,
            latest_report,
            raw_path,
            db_max_source_rank=int(db_counts.get("ertl_max_source_rank") or 0),
        ),
        "latest_report": latest_report,
        **db_counts,
    }


def save_ring_import_status(status: dict, output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(status, indent=2, sort_keys=True), encoding="utf-8")


def _sync_chunk_report_to_checkpoint(
    *,
    status: dict,
    ring_state: dict,
    report_path: str | Path,
    now: str,
) -> dict:
    latest_report = dict(status.get("latest_report") or {})
    target_next = max(
        int(ring_state.get("next_offset") or 0),
        int(status.get("ertl_max_source_rank") or 0),
    )
    old_report_next = int(latest_report.get("final_next_offset") or 0)
    if not target_next or old_report_next == target_next:
        return {"report_repaired": False, "old_report_next_offset": old_report_next, "new_report_next_offset": old_report_next}

    source_total = int(status.get("source_total") or DEFAULT_ESTIMATED_ERTL_TOTAL)
    chunk_size = int(ring_state.get("last_limit") or latest_report.get("chunk_size") or 0)
    last_imported = int(ring_state.get("last_imported_count") or 0)
    last_offset_value = ring_state.get("last_offset")
    if last_offset_value in {None, ""}:
        last_offset = max(target_next - last_imported, 0)
    else:
        last_offset = int(last_offset_value)
    imported_count = max(target_next - last_offset, 0)
    if not chunk_size:
        chunk_size = imported_count or int(latest_report.get("chunk_size") or 0)

    chunks = []
    if imported_count:
        chunks.append(
            {
                "chunk_no": 1,
                "offset": last_offset,
                "imported_count": imported_count,
                "next_offset": target_next,
                "first_source_rank": last_offset + 1,
                "last_source_rank": target_next,
                "checkpoint_report_sync": True,
            }
        )
    repaired_report = {
        **latest_report,
        "checkpoint_report_sync": True,
        "checkpoint_repaired_at": now,
        "started_offset": last_offset,
        "final_next_offset": target_next,
        "imported_total": imported_count,
        "chunk_size": chunk_size,
        "source_total": source_total,
        "continuous": bool(ring_state.get("last_run_continuous_mode") or ring_state.get("continuous_mode")),
        "final_progress_percent": round((target_next / source_total) * 100.0, 4) if source_total else None,
        "finished_at": ring_state.get("last_chunked_import_at") or latest_report.get("finished_at") or now,
        "throughput_rings_per_second": ring_state.get("last_throughput_rings_per_second")
        or latest_report.get("throughput_rings_per_second"),
        "error": None,
        "chunks": chunks or latest_report.get("chunks") or [],
    }
    report_file = Path(report_path)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(json.dumps(repaired_report, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "report_repaired": True,
        "old_report_next_offset": old_report_next,
        "new_report_next_offset": target_next,
        "report_path": str(report_file.resolve()),
    }


def repair_ring_import_state_from_db_status(
    status: dict,
    *,
    state_path: str | Path = DEFAULT_RING_IMPORT_STATE_PATH,
    report_path: str | Path = DEFAULT_REPORT_PATH,
) -> dict:
    """Repair a stale Ertl checkpoint using the max source_rank already present in SQLite."""
    state_file = Path(state_path)
    state = load_import_state(state_file)
    ring_state = state.get("ertl_4m_ring_systems") or {}
    old_next = int(ring_state.get("next_offset") or 0)
    max_rank = int(status.get("ertl_max_source_rank") or 0)
    now = datetime.now(timezone.utc).isoformat()
    if max_rank <= old_next:
        report_repair = _sync_chunk_report_to_checkpoint(
            status=status,
            ring_state=ring_state,
            report_path=report_path,
            now=now,
        )
        return {
            "repaired": bool(report_repair.get("report_repaired")),
            "state_repaired": False,
            "report_repaired": bool(report_repair.get("report_repaired")),
            "old_next_offset": old_next,
            "new_next_offset": old_next,
            "reason": "checkpoint_not_behind_db",
            **report_repair,
        }

    chunk_size = int(ring_state.get("last_limit") or (status.get("latest_report") or {}).get("chunk_size") or 50000)
    repaired_total = max_rank - old_next
    last_imported = min(chunk_size, repaired_total)
    repaired_state = {
        **state,
        "ertl_4m_ring_systems": {
            **ring_state,
            "next_offset": max_rank,
            "last_offset": max_rank - last_imported,
            "last_imported_count": last_imported,
            "last_limit": chunk_size,
            "continuous_mode": False,
            "last_error": None,
            "last_chunked_import_at": ring_state.get("last_chunked_import_at") or now,
            "checkpoint_repaired_at": now,
            "checkpoint_repair_basis": "db_max_ertl_source_rank",
            "checkpoint_repaired_from_offset": old_next,
        },
    }
    save_ring_import_status(repaired_state, state_file)

    report_file = Path(report_path)
    latest_report = dict(status.get("latest_report") or {})
    source_total = int(status.get("source_total") or DEFAULT_ESTIMATED_ERTL_TOTAL)
    chunks = []
    cursor = old_next
    chunk_no = 0
    while cursor < max_rank:
        next_offset = min(max_rank, cursor + chunk_size)
        chunk_no += 1
        chunks.append(
            {
                "chunk_no": chunk_no,
                "offset": cursor,
                "imported_count": next_offset - cursor,
                "next_offset": next_offset,
                "first_source_rank": cursor + 1,
                "last_source_rank": next_offset,
                "checkpoint_repair": True,
            }
        )
        cursor = next_offset
    repaired_report = {
        **latest_report,
        "checkpoint_repair": True,
        "checkpoint_repaired_at": now,
        "started_offset": old_next,
        "final_next_offset": max_rank,
        "imported_total": repaired_total,
        "chunk_size": chunk_size,
        "source_total": source_total,
        "final_progress_percent": round((max_rank / source_total) * 100.0, 4) if source_total else None,
        "error": None,
        "chunks": chunks,
    }
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(json.dumps(repaired_report, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "repaired": True,
        "state_repaired": True,
        "report_repaired": True,
        "old_next_offset": old_next,
        "new_next_offset": max_rank,
        "repaired_imported_count": repaired_total,
        "chunk_size": chunk_size,
        "report_path": str(report_file.resolve()),
        "state_path": str(state_file.resolve()),
    }
