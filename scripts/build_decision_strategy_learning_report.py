from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.decision_packet import build_decision_strategy_learning_report, write_decision_strategy_learning_report  # noqa: E402
from localmedchem.strategy_learning import DEFAULT_POLICY_PATH, load_strategy_learning_policy  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Learn candidate strategy performance from decision packets and later outcomes.")
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "decision_strategy_learning_report.json"))
    parser.add_argument("--policy", default=str(ROOT / DEFAULT_POLICY_PATH))
    parser.add_argument("--since-days", type=int, default=None)
    parser.add_argument("--strategy-version", default=None)
    args = parser.parse_args()
    policy = load_strategy_learning_policy(args.policy)
    report = build_decision_strategy_learning_report(
        db_path=args.db,
        project_name=args.project_name,
        since_days=args.since_days if args.since_days is not None else policy.get("default_window_days"),
        strategy_version=args.strategy_version or policy.get("strategy_version") or "strategy-learning-v0.2",
        policy_version=policy.get("policy_version"),
    )
    write_decision_strategy_learning_report(report, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
