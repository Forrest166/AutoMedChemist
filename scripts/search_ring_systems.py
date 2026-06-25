from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.ring_search import ring_source_summary, search_ring_systems  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the SQLite ring-system data foundation.")
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--query", default=None)
    parser.add_argument("--ring-class", default=None)
    parser.add_argument("--source-dataset", default=None)
    parser.add_argument("--min-heavy-atoms", type=int, default=None)
    parser.add_argument("--max-heavy-atoms", type=int, default=None)
    parser.add_argument("--novelty-bucket", default=None)
    parser.add_argument("--diversity-bucket", default=None)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    if args.summary:
        rows = ring_source_summary(db_path=args.db_path)
    else:
        rows = search_ring_systems(
            db_path=args.db_path,
            query=args.query,
            ring_class=args.ring_class,
            source_dataset=args.source_dataset,
            min_heavy_atoms=args.min_heavy_atoms,
            max_heavy_atoms=args.max_heavy_atoms,
            novelty_bucket=args.novelty_bucket,
            diversity_bucket=args.diversity_bucket,
            limit=args.limit,
        )
    print(json.dumps({"count": len(rows), "rows": rows}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
