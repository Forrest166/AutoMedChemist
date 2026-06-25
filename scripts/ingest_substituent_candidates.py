from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.ingestion import generate_seed_from_candidates  # noqa: E402


def parse_seed_paths(value: str) -> list[Path]:
    return [Path(part.strip()) for part in value.replace(";", ",").split(",") if part.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize curated public-data candidates into a governed seed file.")
    parser.add_argument(
        "--source",
        default=str(ROOT / "data" / "sources" / "substituent_expansion_candidates.yaml"),
    )
    parser.add_argument("--existing-seeds", default=str(ROOT / "data" / "seeds" / "core_substituent_seed.yaml"))
    parser.add_argument("--output", default=str(ROOT / "data" / "seeds" / "pubchem_expansion_seed.yaml"))
    parser.add_argument("--report-out", default=str(ROOT / "data" / "substituents" / "ingestion_report.json"))
    args = parser.parse_args()

    report = generate_seed_from_candidates(
        source_path=args.source,
        existing_seed_paths=parse_seed_paths(args.existing_seeds),
        output_path=args.output,
    )
    report_path = Path(args.report_out)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

