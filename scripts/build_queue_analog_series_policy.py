from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.analog_series import (  # noqa: E402
    calibrate_queue_analog_series_policy,
    load_queue_analog_series_delta_report,
    load_queue_analog_series_policy_document,
    rollback_queue_analog_series_policy,
    write_queue_analog_series_policy,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate or roll back the queue analog-series scoring policy.")
    parser.add_argument("--queue-delta", default=str(ROOT / "data" / "projects" / "closed_loop" / "queue_analog_series_delta.json"))
    parser.add_argument("--policy", default=str(ROOT / "data" / "rules" / "queue_analog_series_policy.yaml"))
    parser.add_argument("--version", default=None, help="Version id for a new calibrated policy version.")
    parser.add_argument("--rollback-version", default=None, help="Activate an existing policy version instead of calibrating.")
    parser.add_argument("--reviewer", default="codex")
    parser.add_argument("--note", default="")
    parser.add_argument("--blend", type=float, default=0.45)
    parser.add_argument("--json-out", default=str(ROOT / "data" / "projects" / "closed_loop" / "queue_analog_series_policy_report.json"))
    args = parser.parse_args()

    policy = load_queue_analog_series_policy_document(args.policy)
    if args.rollback_version:
        updated = rollback_queue_analog_series_policy(
            policy,
            version=args.rollback_version,
            reviewer=args.reviewer,
            note=args.note,
        )
        event = "rollback"
    else:
        delta_report = load_queue_analog_series_delta_report(args.queue_delta)
        updated = calibrate_queue_analog_series_policy(
            delta_report,
            previous_policy=policy,
            version=args.version,
            reviewer=args.reviewer,
            note=args.note,
            blend=args.blend,
        )
        event = "calibrated"

    write_queue_analog_series_policy(updated, args.policy)
    report = {
        "event": event,
        "policy_path": str(Path(args.policy).resolve()),
        "active_version": updated.get("active_version"),
        "version_count": len(updated.get("versions") or []),
        "latest_calibration": updated.get("latest_calibration"),
        "change_log_tail": (updated.get("change_log") or [])[-5:],
    }
    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
