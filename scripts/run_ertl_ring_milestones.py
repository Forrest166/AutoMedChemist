from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from import_ertl_ring_chunks import import_ertl_ring_chunks  # noqa: E402
from localmedchem.data_foundation import validate_source_expansion_acceptance  # noqa: E402
from localmedchem.ring_import_status import build_ring_import_status, save_ring_import_status  # noqa: E402


def _target_report(target: float, import_report: dict | None, *, skipped: bool = False) -> dict:
    final_progress = None
    added_records = 0
    if import_report:
        final_progress = import_report.get("final_progress_percent")
        added_records = int(import_report.get("imported_total") or 0)
    return {
        "target_progress_percent": float(target),
        "skipped": skipped,
        "imported_count": added_records,
        "final_progress_percent": final_progress,
        "import_report": import_report or {},
    }


def run_ertl_ring_milestones(
    *,
    targets: list[float],
    chunk_size: int,
    max_runtime_seconds: float | None,
    source_total: int,
    db_path: str | Path,
    state_path: str | Path,
    raw_path: str | Path,
    fast_sqlite_pragmas: bool = False,
    defer_ring_indexes: bool = False,
) -> dict:
    started = datetime.now(timezone.utc)
    status_before = build_ring_import_status(db_path=db_path, state_path=state_path, raw_path=raw_path, source_total=source_total)
    target_reports = []
    for target in sorted({float(item) for item in targets}):
        current_progress = float((build_ring_import_status(db_path=db_path, state_path=state_path, raw_path=raw_path, source_total=source_total).get("progress_percent") or 0.0))
        if current_progress >= target:
            target_reports.append(_target_report(target, {"final_progress_percent": current_progress, "imported_total": 0}, skipped=True))
            continue
        import_report = import_ertl_ring_chunks(
            raw=raw_path,
            db_out=db_path,
            state_out=state_path,
            chunk_size=chunk_size,
            max_chunks=0,
            continuous=True,
            max_runtime_seconds=max_runtime_seconds,
            target_progress_percent=target,
            source_total=source_total,
            fast_sqlite_pragmas=fast_sqlite_pragmas,
            defer_ring_indexes=defer_ring_indexes,
        )
        (ROOT / "data" / "substituents" / "ertl_ring_chunk_import_report.json").write_text(
            json.dumps(import_report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        target_reports.append(_target_report(target, import_report))
        if max_runtime_seconds is not None and float(import_report.get("final_progress_percent") or 0.0) < target:
            break

    status_after = build_ring_import_status(db_path=db_path, state_path=state_path, raw_path=raw_path, source_total=source_total)
    save_ring_import_status(status_after, ROOT / "data" / "substituents" / "ring_import_status.json")
    before_count = int(status_before.get("ring_system_count") or 0)
    after_count = int(status_after.get("ring_system_count") or 0)
    jump_fraction = ((after_count - before_count) / max(before_count, 1)) if after_count >= before_count else 0.0
    acceptance = validate_source_expansion_acceptance(
        table="ring_system",
        check="unexpected_count_jump",
        change_fraction=jump_fraction,
        root=ROOT,
    )
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": started.isoformat(),
        "source_total": int(source_total),
        "chunk_size": int(chunk_size),
        "max_runtime_seconds": max_runtime_seconds,
        "fast_sqlite_pragmas": bool(fast_sqlite_pragmas),
        "defer_ring_indexes": bool(defer_ring_indexes),
        "status_before": status_before,
        "status_after": status_after,
        "target_reports": target_reports,
        "imported_total": sum(int(item.get("imported_count") or 0) for item in target_reports),
        "ring_system_count_delta": after_count - before_count,
        "ring_system_jump_fraction": round(jump_fraction, 6),
        "source_acceptance": acceptance,
        "recommended_next_actions": [
            "Continue the next milestone only after daily maintenance and strict quality gates pass.",
            "Keep the ring_system source acceptance active while DB-only Ertl import is intentionally expanding.",
            "Refresh data-foundation snapshots after each large milestone so drift is attributed to the reviewed import.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run reviewed Ertl ring import progress milestones.")
    parser.add_argument("--target-progress-percent", type=float, action="append", default=None)
    parser.add_argument("--chunk-size", type=int, default=50000)
    parser.add_argument("--max-runtime-seconds", type=float, default=None)
    parser.add_argument("--source-total", type=int, default=3_931_782)
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--state-path", default=str(ROOT / "data" / "substituents" / "ring_import_state.json"))
    parser.add_argument("--raw", default=str(ROOT / "data" / "raw" / "literature" / "ertl_4m_rings.zip"))
    parser.add_argument("--fast-sqlite-pragmas", action="store_true", help="Use reviewed SQLite speed settings during milestone import.")
    parser.add_argument("--defer-ring-indexes", action="store_true", help="Temporarily drop ring lookup indexes during the milestone import and rebuild them before exit.")
    parser.add_argument("--json-out", default=str(ROOT / "data" / "substituents" / "ertl_ring_milestone_report.json"))
    args = parser.parse_args()

    report = run_ertl_ring_milestones(
        targets=args.target_progress_percent or [40.0, 50.0],
        chunk_size=args.chunk_size,
        max_runtime_seconds=args.max_runtime_seconds,
        source_total=args.source_total,
        db_path=args.db_path,
        state_path=args.state_path,
        raw_path=args.raw,
        fast_sqlite_pragmas=args.fast_sqlite_pragmas,
        defer_ring_indexes=args.defer_ring_indexes,
    )
    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report.get("source_acceptance", {}).get("accepted"):
        raise SystemExit("Ring milestone import completed without an active source acceptance manifest entry.")


if __name__ == "__main__":
    main()
