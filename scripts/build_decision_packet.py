from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.decision_packet import build_decision_packet, save_decision_packet, write_decision_packet  # noqa: E402
from localmedchem.pipeline import run_mvp  # noqa: E402


def _read_candidates(path: str | Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a medchem make/defer/reject decision packet from candidate rows.")
    parser.add_argument("--candidates-csv", default=None)
    parser.add_argument("--smiles", default="COc1ccc(Cl)cc1")
    parser.add_argument("--direction", default="increase_polarity")
    parser.add_argument("--site-index", type=int, default=0)
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--source-run-id", default=None)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--save-db", action="store_true")
    parser.add_argument("--review-status", default="needs_review")
    parser.add_argument("--output-prefix", default=str(ROOT / "data" / "projects" / "demo" / "medchem_decision_packet"))
    args = parser.parse_args()

    if args.candidates_csv:
        rows = _read_candidates(args.candidates_csv)
        parent_smiles = None
        site_type = None
    else:
        result = run_mvp(
            smiles=args.smiles,
            direction=args.direction,
            site_index=args.site_index,
            project_name=args.project_name,
            db_path=ROOT / "data" / "localmedchem.sqlite",
            max_candidates=80,
            diverse_top_n=20,
        )
        rows = result.get("candidates") or []
        parent_smiles = result.get("parent_smiles")
        site_type = (result.get("selected_site") or {}).get("site_type")
    packet = build_decision_packet(
        rows,
        project_name=args.project_name,
        source_run_id=args.source_run_id,
        parent_smiles=parent_smiles,
        direction=args.direction,
        site_type=site_type,
        limit=args.limit,
    )
    outputs = write_decision_packet(packet, args.output_prefix)
    packet_id = None
    if args.save_db:
        packet_id = save_decision_packet(packet, db_path=args.db, status=args.review_status)
    print(json.dumps({"packet_id": packet_id, "packet": packet, "outputs": outputs}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
