from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.review import REVIEW_STATUSES, update_substituent_review  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Update a substituent review block and append version history.")
    parser.add_argument("substituent_id")
    parser.add_argument("--library", default=str(ROOT / "data" / "seeds" / "core_substituent_seed.yaml"))
    parser.add_argument("--status", choices=REVIEW_STATUSES, required=True)
    parser.add_argument("--reviewed-by", default=None)
    parser.add_argument("--note", default=None)
    parser.add_argument("--use-cases", default=None, help="Semicolon-separated list.")
    parser.add_argument("--avoid-contexts", default=None, help="Semicolon-separated list.")
    parser.add_argument("--default-enabled", choices=["true", "false"], default=None)
    parser.add_argument("--common-medchem", choices=["true", "false"], default=None)
    parser.add_argument("--mvp", choices=["true", "false"], default=None)
    parser.add_argument("--default-rank", type=int, default=None)
    parser.add_argument("--change-summary", default=None)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()

    def parse_bool(value: str | None) -> bool | None:
        if value is None:
            return None
        return value.lower() == "true"

    record = update_substituent_review(
        args.library,
        args.substituent_id,
        status=args.status,
        reviewed_by=args.reviewed_by,
        review_note=args.note,
        use_cases=args.use_cases,
        avoid_contexts=args.avoid_contexts,
        default_enabled=parse_bool(args.default_enabled),
        common_medchem=parse_bool(args.common_medchem),
        mvp=parse_bool(args.mvp),
        default_rank=args.default_rank,
        change_summary=args.change_summary,
    )
    print(f"Updated {record['substituent_id']} {record['name']} -> {record['review']['status']}")

    if args.rebuild:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build_library.py")], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()

