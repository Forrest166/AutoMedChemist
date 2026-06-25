from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.database import initialize_database, insert_ring_systems  # noqa: E402
from localmedchem.ring_library import (  # noqa: E402
    DEFAULT_RING_IMPORT_STATE_PATH,
    file_sha256,
    iter_ertl_ring_records,
    load_import_state,
    save_import_state,
    validate_ring_substituent_collections,
)


RAW = ROOT / "data" / "raw" / "literature" / "ertl_4m_rings.zip"

RING_IMPORT_DEFERRED_INDEXES = {
    "idx_ring_system_canonical": "CREATE INDEX IF NOT EXISTS idx_ring_system_canonical ON ring_system(canonical_smiles)",
    "idx_ring_system_class": "CREATE INDEX IF NOT EXISTS idx_ring_system_class ON ring_system(ring_class)",
    "idx_ring_system_dataset": "CREATE INDEX IF NOT EXISTS idx_ring_system_dataset ON ring_system(source_dataset)",
    "idx_ring_system_dataset_rank": "CREATE INDEX IF NOT EXISTS idx_ring_system_dataset_rank ON ring_system(source_dataset, source_rank)",
    "idx_ring_system_dataset_class_heavy": (
        "CREATE INDEX IF NOT EXISTS idx_ring_system_dataset_class_heavy "
        "ON ring_system(source_dataset, ring_class, heavy_atom_count)"
    ),
    "idx_ring_system_dataset_class_rank": (
        "CREATE INDEX IF NOT EXISTS idx_ring_system_dataset_class_rank "
        "ON ring_system(source_dataset, ring_class, source_rank)"
    ),
    "idx_ring_system_heavy_atoms": "CREATE INDEX IF NOT EXISTS idx_ring_system_heavy_atoms ON ring_system(heavy_atom_count)",
}


def _drop_ring_import_indexes(conn) -> list[str]:
    dropped = []
    for name in RING_IMPORT_DEFERRED_INDEXES:
        conn.execute(f"DROP INDEX IF EXISTS {name}")
        dropped.append(name)
    conn.commit()
    return dropped


def _recreate_ring_import_indexes(conn) -> list[str]:
    recreated = []
    for name, sql in RING_IMPORT_DEFERRED_INDEXES.items():
        conn.execute(sql)
        recreated.append(name)
    conn.commit()
    return recreated


def import_ertl_ring_chunks(
    *,
    raw: str | Path = RAW,
    db_out: str | Path = ROOT / "data" / "localmedchem.sqlite",
    state_out: str | Path = DEFAULT_RING_IMPORT_STATE_PATH,
    offset: int | None = None,
    chunk_size: int = 5000,
    max_chunks: int = 1,
    continuous: bool = False,
    sleep_seconds: float = 0.0,
    max_runtime_seconds: float | None = None,
    target_progress_percent: float | None = None,
    source_total: int = 3_931_782,
    fast_sqlite_pragmas: bool = False,
    defer_ring_indexes: bool = False,
) -> dict:
    raw_path = Path(raw)
    state = load_import_state(state_out)
    ring_state = state.get("ertl_4m_ring_systems") or {}
    start_offset = offset if offset is not None else int(ring_state.get("next_offset") or 0)
    current_offset = start_offset
    source_sha = file_sha256(raw_path)
    started_at = time.monotonic()
    started_wall = datetime.now(timezone.utc)
    if not continuous and not max_chunks:
        max_chunks = 1

    imported_total = 0
    chunk_reports = []
    exhausted = False
    conn = initialize_database(db_out)
    if fast_sqlite_pragmas:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=-200000")
    dropped_indexes = _drop_ring_import_indexes(conn) if defer_ring_indexes else []
    recreated_indexes: list[str] = []
    failure: str | None = None
    try:
        chunk_no = 0
        record_iter = iter_ertl_ring_records(raw_path, limit=0, offset=current_offset)
        while True:
            if max_chunks and chunk_no >= max_chunks:
                break
            if max_runtime_seconds is not None and (time.monotonic() - started_at) >= max_runtime_seconds:
                break
            if target_progress_percent is not None and source_total > 0:
                if (current_offset / source_total) * 100.0 >= float(target_progress_percent):
                    break
            chunk_no += 1
            rows = list(islice(record_iter, int(chunk_size)))
            if not rows:
                exhausted = True
                chunk_reports.append({"chunk_no": chunk_no, "offset": current_offset, "imported_count": 0, "next_offset": current_offset})
                break
            quality = validate_ring_substituent_collections(rows, [], [], [])
            if quality["error_count"]:
                raise SystemExit(f"Chunk validation failed at offset {current_offset}: {quality['issues'][:5]}")
            insert_ring_systems(conn, rows)
            imported_total += len(rows)
            next_offset = max(int(row.get("source_rank") or current_offset) for row in rows)
            chunk_reports.append(
                {
                    "chunk_no": chunk_no,
                    "offset": current_offset,
                    "imported_count": len(rows),
                    "next_offset": next_offset,
                    "first_source_rank": rows[0].get("source_rank"),
                    "last_source_rank": rows[-1].get("source_rank"),
                }
            )
            current_offset = next_offset
            partial_elapsed = round(time.monotonic() - started_at, 3)
            partial_throughput = round(imported_total / partial_elapsed, 3) if partial_elapsed > 0 and imported_total else None
            save_import_state(
                {
                    **state,
                    "ertl_4m_ring_systems": {
                        **ring_state,
                        "source_path": str(raw_path.resolve()),
                        "source_sha256": source_sha,
                        "last_offset": chunk_reports[-1]["offset"],
                        "last_limit": chunk_size,
                        "last_imported_count": chunk_reports[-1]["imported_count"],
                        "next_offset": current_offset,
                        "full_import_requested": True,
                        "db_only": True,
                        "continuous_mode": bool(continuous),
                        "last_run_continuous_mode": bool(continuous),
                        "exhausted": exhausted,
                        "last_runtime_seconds": partial_elapsed,
                        "last_throughput_rings_per_second": partial_throughput,
                        "last_error": None,
                        "last_started_at": started_wall.isoformat(),
                        "last_chunked_import_at": datetime.now(timezone.utc).isoformat(),
                    },
                },
                state_out,
            )
            if not continuous:
                continue
            if sleep_seconds:
                time.sleep(max(float(sleep_seconds), 0.0))
    except Exception as exc:
        failure = str(exc)
        failed_state = {
            **state,
            "ertl_4m_ring_systems": {
                **ring_state,
                "source_path": str(raw_path.resolve()),
                "source_sha256": source_sha,
                "last_offset": chunk_reports[-1]["offset"] if chunk_reports else current_offset,
                "last_limit": chunk_size,
                "last_imported_count": chunk_reports[-1]["imported_count"] if chunk_reports else 0,
                "next_offset": current_offset,
                "full_import_requested": True,
                "db_only": True,
                "continuous_mode": False,
                "last_run_continuous_mode": bool(continuous),
                "exhausted": exhausted,
                "last_runtime_seconds": round(time.monotonic() - started_at, 3),
                "last_throughput_rings_per_second": None,
                "last_error": failure,
                "last_started_at": started_wall.isoformat(),
                "last_chunked_import_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        save_import_state(failed_state, state_out)
        raise
    finally:
        if defer_ring_indexes:
            recreated_indexes = _recreate_ring_import_indexes(conn)
        conn.close()

    finished_wall = datetime.now(timezone.utc)
    elapsed_seconds = round(time.monotonic() - started_at, 3)
    throughput = round(imported_total / elapsed_seconds, 3) if elapsed_seconds > 0 and imported_total else None
    updated_state = {
        **state,
        "ertl_4m_ring_systems": {
            **ring_state,
            "source_path": str(raw_path.resolve()),
            "source_sha256": source_sha,
            "last_offset": chunk_reports[-1]["offset"] if chunk_reports else current_offset,
            "last_limit": chunk_size,
            "last_imported_count": chunk_reports[-1]["imported_count"] if chunk_reports else 0,
            "next_offset": current_offset,
            "full_import_requested": True,
            "db_only": True,
            "continuous_mode": False,
            "last_run_continuous_mode": bool(continuous),
            "exhausted": exhausted,
            "last_runtime_seconds": elapsed_seconds,
            "last_throughput_rings_per_second": throughput,
            "last_error": failure,
            "last_started_at": started_wall.isoformat(),
            "last_chunked_import_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    save_import_state(updated_state, state_out)

    return {
        "source_path": str(raw_path.resolve()),
        "source_sha256": source_sha,
        "db_out": str(Path(db_out).resolve()),
        "started_offset": start_offset,
        "final_next_offset": current_offset,
        "chunk_size": chunk_size,
        "max_chunks": max_chunks,
        "continuous": continuous,
        "sleep_seconds": sleep_seconds,
        "max_runtime_seconds": max_runtime_seconds,
        "target_progress_percent": target_progress_percent,
        "source_total": source_total,
        "fast_sqlite_pragmas": bool(fast_sqlite_pragmas),
        "defer_ring_indexes": bool(defer_ring_indexes),
        "dropped_ring_indexes": dropped_indexes,
        "recreated_ring_indexes": recreated_indexes,
        "final_progress_percent": round((current_offset / source_total) * 100.0, 4) if source_total else None,
        "exhausted": exhausted,
        "imported_total": imported_total,
        "started_at": started_wall.isoformat(),
        "finished_at": finished_wall.isoformat(),
        "elapsed_seconds": elapsed_seconds,
        "throughput_rings_per_second": throughput,
        "error": failure,
        "chunks": chunk_reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Ertl 4M ring systems into SQLite in DB-only chunks.")
    parser.add_argument("--raw", default=str(RAW))
    parser.add_argument("--db-out", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--state-out", default=str(DEFAULT_RING_IMPORT_STATE_PATH))
    parser.add_argument("--offset", type=int, default=None)
    parser.add_argument("--chunk-size", type=int, default=5000)
    parser.add_argument("--max-chunks", type=int, default=1, help="Use 0 for unlimited chunks when combined with --continuous.")
    parser.add_argument("--continuous", action="store_true", help="Keep importing chunks until --max-chunks, --max-runtime-seconds, or source exhaustion.")
    parser.add_argument("--sleep-seconds", type=float, default=0.0, help="Pause between chunks in continuous mode.")
    parser.add_argument("--max-runtime-seconds", type=float, default=None)
    parser.add_argument("--target-progress-percent", type=float, default=None, help="Stop once checkpoint offset reaches this percent of the Ertl source.")
    parser.add_argument("--source-total", type=int, default=3_931_782)
    parser.add_argument("--fast-sqlite-pragmas", action="store_true", help="Use WAL/NORMAL sync, memory temp store, and a larger cache for reviewed bulk imports.")
    parser.add_argument("--defer-ring-indexes", action="store_true", help="Drop non-unique ring lookup indexes during the import and rebuild them before exit.")
    parser.add_argument("--report-out", default=str(ROOT / "data" / "substituents" / "ertl_ring_chunk_import_report.json"))
    args = parser.parse_args()

    report = import_ertl_ring_chunks(
        raw=args.raw,
        db_out=args.db_out,
        state_out=args.state_out,
        offset=args.offset,
        chunk_size=args.chunk_size,
        max_chunks=args.max_chunks,
        continuous=args.continuous,
        sleep_seconds=args.sleep_seconds,
        max_runtime_seconds=args.max_runtime_seconds,
        target_progress_percent=args.target_progress_percent,
        source_total=args.source_total,
        fast_sqlite_pragmas=args.fast_sqlite_pragmas,
        defer_ring_indexes=args.defer_ring_indexes,
    )
    Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report_out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
