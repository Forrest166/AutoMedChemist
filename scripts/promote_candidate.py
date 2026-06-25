from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.database import initialize_database, record_candidate_promotion, update_candidate_status  # noqa: E402
from localmedchem.promotion import load_candidate_from_db, load_candidate_from_sources, promote_candidate_to_seed  # noqa: E402


DEFAULT_SEEDS = [
    ROOT / "data" / "seeds" / "core_substituent_seed.yaml",
    ROOT / "data" / "seeds" / "pubchem_expansion_seed.yaml",
]

DEFAULT_STAGING_CANDIDATES = [
    ROOT / "data" / "sources" / "substituent_expansion_candidates.yaml",
    ROOT / "data" / "sources" / "patent_mined_candidates.yaml",
    ROOT / "data" / "sources" / "chembl_fragment_candidates.yaml",
    ROOT / "data" / "sources" / "surechembl_patent_candidates.yaml",
]


def parse_paths(value: str) -> list[Path]:
    return [Path(part.strip()) for part in value.replace(";", ",").split(",") if part.strip()]


def substituent_exists(db_path: Path, substituent_id: str) -> bool:
    if not db_path.exists():
        return False
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT 1 FROM substituent WHERE substituent_id = ?", (substituent_id,)).fetchone()
        return row is not None
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote or reject a staged substituent candidate through governance.")
    parser.add_argument("candidate_id")
    parser.add_argument("--status", choices=["promoted", "approved", "rejected", "blocked"], default="promoted")
    parser.add_argument("--reviewed-by", default="localmedchem")
    parser.add_argument("--note", default="")
    parser.add_argument("--seed-out", default=str(ROOT / "data" / "seeds" / "pubchem_expansion_seed.yaml"))
    parser.add_argument("--existing-seeds", default=";".join(str(path) for path in DEFAULT_SEEDS))
    parser.add_argument("--staging-candidates", default=";".join(str(path) for path in DEFAULT_STAGING_CANDIDATES))
    parser.add_argument("--db-out", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db_out)
    candidate = load_candidate_from_db(db_path, args.candidate_id)
    if candidate is None:
        candidate = load_candidate_from_sources(parse_paths(args.staging_candidates), args.candidate_id)
    if candidate is None:
        raise SystemExit(f"Candidate not found: {args.candidate_id}")

    summary: dict = {
        "candidate_id": args.candidate_id,
        "requested_status": args.status,
        "candidate_name": candidate.get("name"),
        "dry_run": args.dry_run,
    }

    if args.status in {"rejected", "blocked"}:
        summary["status"] = args.status
        if not args.dry_run:
            conn = initialize_database(db_path)
            try:
                update_candidate_status(conn, args.candidate_id, args.status, review_tier=args.status)
            finally:
                conn.close()
        print(json.dumps(summary, indent=2, sort_keys=True))
        return

    if args.dry_run:
        summary["status"] = "would_promote"
        print(json.dumps(summary, indent=2, sort_keys=True))
        return

    result = promote_candidate_to_seed(
        candidate,
        existing_seed_paths=parse_paths(args.existing_seeds),
        output_seed_path=args.seed_out,
        reviewed_by=args.reviewed_by,
        note=args.note or None,
        source_version="promotion-0.2",
    )
    summary.update(result)
    pending_status = "promoted_pending_build" if result.get("appended") else result.get("status", "approved")

    conn = initialize_database(db_path)
    try:
        update_candidate_status(conn, args.candidate_id, pending_status, review_tier="approved")
    finally:
        conn.close()

    if args.rebuild and result.get("status") in {"promoted", "duplicate_existing"}:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build_library.py")], check=True)
        conn = initialize_database(db_path)
        try:
            update_candidate_status(conn, args.candidate_id, "promoted", review_tier="approved")
            if result.get("substituent_id") and substituent_exists(db_path, result["substituent_id"]):
                record_candidate_promotion(
                    conn,
                    args.candidate_id,
                    result["substituent_id"],
                    promotion_status="promoted",
                    notes=args.note or "Promoted through promote_candidate.py.",
                )
        finally:
            conn.close()
        summary["rebuilt_library"] = True
    else:
        summary["rebuilt_library"] = False

    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

