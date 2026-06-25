from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.promotion_readiness_packet import build_promotion_readiness_packet, write_promotion_readiness_packet  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a non-experimental promotion readiness packet.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "promotion_readiness_packet.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "promotion_readiness_packet.csv"))
    args = parser.parse_args()
    packet = build_promotion_readiness_packet(root=args.root, project_name=args.project_name or None)
    write_promotion_readiness_packet(packet, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": packet.get("status"),
                "profile_impact_open_count": packet.get("profile_impact_open_count"),
                "strict_exact_pending_count": packet.get("strict_exact_pending_count"),
                "project_memory_open_like_count": packet.get("project_memory_open_like_count"),
                "mode": packet.get("mode"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
