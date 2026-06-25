from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.ring_import_status import build_ring_import_status, repair_ring_import_state_from_db_status, save_ring_import_status  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Report Ertl ring import progress, throughput, and ETA.")
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--state", default=str(ROOT / "data" / "substituents" / "ring_import_state.json"))
    parser.add_argument("--report", default=str(ROOT / "data" / "substituents" / "ertl_ring_chunk_import_report.json"))
    parser.add_argument("--raw", default=str(ROOT / "data" / "raw" / "literature" / "ertl_4m_rings.zip"))
    parser.add_argument("--source-total", type=int, default=None)
    parser.add_argument("--count-source", action="store_true", help="Count records in rings.smi; slower but exact.")
    parser.add_argument("--repair-state-from-db", action="store_true", help="Advance a stale checkpoint to the max Ertl source_rank already present in SQLite.")
    parser.add_argument("--out", default=str(ROOT / "data" / "substituents" / "ring_import_status.json"))
    args = parser.parse_args()

    status = build_ring_import_status(
        db_path=args.db,
        state_path=args.state,
        report_path=args.report,
        raw_path=args.raw,
        source_total=args.source_total,
        count_source=args.count_source,
    )
    if args.repair_state_from_db:
        repair = repair_ring_import_state_from_db_status(status, state_path=args.state, report_path=args.report)
        status = build_ring_import_status(
            db_path=args.db,
            state_path=args.state,
            report_path=args.report,
            raw_path=args.raw,
            source_total=args.source_total,
            count_source=args.count_source,
        )
        status["state_repair"] = repair
    save_ring_import_status(status, args.out)
    print(json.dumps(status, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
