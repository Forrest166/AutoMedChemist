from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.evidence_confidence import repair_blank_residual_outcome_imports  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Revert residual task outcome-import statuses that have no measured result payload.")
    parser.add_argument("--registry", default=str(ROOT / "data" / "substituents" / "evidence_residual_task_registry.json"))
    parser.add_argument("--reviewer", default="codex")
    parser.add_argument("--note", default="Repaired blank residual outcome import; awaiting measured result payload.")
    args = parser.parse_args()
    registry = repair_blank_residual_outcome_imports(
        registry_path=args.registry,
        reviewer=args.reviewer or None,
        note=args.note or None,
    )
    print(
        json.dumps(
            {
                "registry": str(Path(args.registry).resolve()),
                "repaired_count": (registry.get("last_blank_outcome_repair") or {}).get("repaired_count"),
                "status_counts": registry.get("status_counts") or {},
                "task_count": registry.get("task_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
