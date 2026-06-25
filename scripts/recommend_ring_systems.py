from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.ring_recommender import recommend_ring_systems, write_ring_recommendations  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Recommend governed ring-system replacements from the ring library.")
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--search", default=None)
    parser.add_argument("--source-dataset", default="ertl_4m_ring_systems")
    parser.add_argument("--ring-class", default=None)
    parser.add_argument("--min-heavy", type=int, default=None)
    parser.add_argument("--max-heavy", type=int, default=None)
    parser.add_argument("--min-hetero", type=int, default=None)
    parser.add_argument("--max-hetero", type=int, default=None)
    parser.add_argument("--max-source-rank", type=int, default=None)
    parser.add_argument("--novelty-bucket", default=None)
    parser.add_argument("--diversity-bucket", default=None)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--order-by", default="source_rank")
    parser.add_argument("--cache", default=None, help="Optional JSON cache path for repeated ring recommendation queries.")
    parser.add_argument("--cache-ttl-seconds", type=float, default=86400)
    parser.add_argument("--json-out", default=str(ROOT / "data" / "substituents" / "ring_recommendations.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "substituents" / "ring_recommendations.csv"))
    args = parser.parse_args()

    report = recommend_ring_systems(
        db_path=args.db,
        search=args.search,
        source_dataset=args.source_dataset or None,
        ring_class=args.ring_class,
        min_heavy_atom_count=args.min_heavy,
        max_heavy_atom_count=args.max_heavy,
        min_hetero_atom_count=args.min_hetero,
        max_hetero_atom_count=args.max_hetero,
        max_source_rank=args.max_source_rank,
        novelty_bucket=args.novelty_bucket,
        diversity_bucket=args.diversity_bucket,
        limit=args.limit,
        order_by=args.order_by,
        cache_path=args.cache,
        cache_ttl_seconds=args.cache_ttl_seconds,
    )
    write_ring_recommendations(report, json_out=args.json_out, csv_out=args.csv_out)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
