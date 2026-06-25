from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.novelty_batch import select_novelty_diversity_batch, write_novelty_diversity_batch  # noqa: E402


def _read_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a novelty-diversity candidate batch from a candidate CSV.")
    parser.add_argument("--input", default=str(ROOT / "data" / "projects" / "demo" / "candidates.csv"))
    parser.add_argument("--output-prefix", default=str(ROOT / "data" / "projects" / "demo" / "novelty_diversity_batch"))
    parser.add_argument("--max-rows", type=int, default=24)
    parser.add_argument("--per-bucket-limit", type=int, default=3)
    args = parser.parse_args()
    rows = _read_rows(Path(args.input))
    batch = select_novelty_diversity_batch(
        rows,
        max_rows=args.max_rows,
        per_bucket_limit=args.per_bucket_limit,
    )
    outputs = write_novelty_diversity_batch(batch, args.output_prefix)
    print(json.dumps({"selected_count": len(batch), "outputs": outputs, "rows": batch}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
