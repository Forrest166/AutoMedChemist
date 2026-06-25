from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_PROMOTION_READINESS_PACKET_PATH = Path("data/projects/demo/promotion_readiness_packet.json")
DEFAULT_PROMOTION_READINESS_PACKET_CSV_PATH = Path("data/projects/demo/promotion_readiness_packet.csv")


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _resolve(root_path: Path, path: str | Path) -> Path:
    item = Path(path)
    return item if item.is_absolute() else root_path / item


def _status(level: str, label: str, details: str, owner_lane: str) -> dict:
    return {
        "level": level,
        "label": label,
        "details": details,
        "owner_lane": owner_lane,
    }


def build_promotion_readiness_packet(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    promotion_gate_path: str | Path = "data/projects/demo/closed_loop_promotion_gate.json",
    active_compare_path: str | Path = "data/projects/demo/evidence_value_policy_active_compare.json",
    profile_review_path: str | Path = "data/projects/demo/profile_impact_review_queue.json",
    endpoint_governance_path: str | Path = "data/projects/demo/measurement_gap_endpoint_governance.json",
    review_dashboard_path: str | Path = "data/projects/demo/project_memory_review_dashboard.json",
    review_queue_path: str | Path = "data/projects/demo/project_memory_review_queue.json",
) -> dict:
    root_path = Path(root)
    promotion_gate = _read_json(_resolve(root_path, promotion_gate_path))
    active_compare = _read_json(_resolve(root_path, active_compare_path))
    profile_review = _read_json(_resolve(root_path, profile_review_path))
    endpoint_governance = _read_json(_resolve(root_path, endpoint_governance_path))
    review_dashboard = _read_json(_resolve(root_path, review_dashboard_path))
    review_queue = _read_json(_resolve(root_path, review_queue_path))

    open_profile = int(profile_review.get("open_review_count") or 0)
    critical_profile = int((profile_review.get("severity_counts") or {}).get("critical") or 0)
    strict_pending = int(endpoint_governance.get("strict_exact_pending_count") or 0)
    blocked_pairs = int(endpoint_governance.get("blocked_cross_endpoint_pair_count") or 0)
    site_policy_rows = int(endpoint_governance.get("site_policy_row_count") or 0)
    open_like = int(review_dashboard.get("open_like_count") or review_queue.get("open_operator_item_count") or 0)
    block_count = int(promotion_gate.get("block_count") or 0)
    review_count = int(promotion_gate.get("review_count") or 0)
    findings = []
    if block_count:
        findings.append(_status("block", "Promotion gate has blocking checks", f"block_count={block_count}", "promotion_gate"))
    if open_profile:
        findings.append(
            _status(
                "review",
                "Profile impact review is still open",
                f"open_profile_impact_rows={open_profile}; severities={profile_review.get('severity_counts')}",
                "profile_impact",
            )
        )
    if strict_pending:
        findings.append(
            _status(
                "review",
                "Strict endpoint gaps remain pending",
                f"strict_exact_pending={strict_pending}; blocked_pairs={blocked_pairs}; site_classes={endpoint_governance.get('site_class_counts')}",
                "measurement_gap",
            )
        )
    if open_like:
        findings.append(
            _status(
                "review",
                "Project Memory queue still has open-like items",
                f"open_like={open_like}; lane_rows={review_dashboard.get('lane_row_count')}; lanes={review_queue.get('lane_counts')}",
                "project_memory",
            )
        )
    if review_count:
        findings.append(_status("watch", "Promotion gate has review checks", f"review_count={review_count}", "promotion_gate"))
    if not findings:
        findings.append(_status("pass", "Promotion packet is ready", "No blocking or open local governance items.", "project_memory"))

    status = "blocked" if any(row["level"] == "block" for row in findings) else "review_required" if any(row["level"] == "review" for row in findings) else "ready"
    readiness_score = max(
        0,
        100
        - min(block_count * 20, 40)
        - min(open_profile * 8, 24)
        - min(strict_pending * 5, 20)
        - min(blocked_pairs * 5, 10)
        - min(open_like * 3, 18)
        - min(review_count * 2, 6),
    )
    summary_rows = [
        {
            "section": "promotion_gate",
            "status": promotion_gate.get("promotion_status") or "missing",
            "primary_count": block_count,
            "secondary_count": review_count,
            "details": f"pass_count={promotion_gate.get('pass_count')}",
        },
        {
            "section": "active_policy_compare",
            "status": active_compare.get("status") or "missing",
            "primary_count": active_compare.get("profile_impact_review_count", 0),
            "secondary_count": active_compare.get("row_count", 0),
            "details": f"rollback_target={active_compare.get('rollback_target_policy_version')}",
        },
        {
            "section": "profile_impact_review",
            "status": profile_review.get("status") or "missing",
            "primary_count": open_profile,
            "secondary_count": profile_review.get("row_count", 0),
            "details": f"critical={critical_profile}; severity_counts={profile_review.get('severity_counts')}; review_status_counts={profile_review.get('review_status_counts')}",
        },
        {
            "section": "endpoint_governance",
            "status": endpoint_governance.get("status") or "missing",
            "primary_count": strict_pending,
            "secondary_count": blocked_pairs,
            "details": (
                f"site_policy_rows={site_policy_rows}; site_class_counts={endpoint_governance.get('site_class_counts')}; "
                f"site_endpoint_actions={endpoint_governance.get('site_class_endpoint_action_count')}"
            ),
        },
        {
            "section": "project_memory_review",
            "status": review_dashboard.get("status") or review_queue.get("status") or "missing",
            "primary_count": open_like,
            "secondary_count": review_queue.get("row_count", 0),
            "details": f"lane_counts={review_queue.get('lane_counts')}",
        },
    ]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "readiness_score": readiness_score,
        "mode": "non_experimental_promotion_readiness_packet",
        "project_name": project_name,
        "summary_rows": summary_rows,
        "findings": findings,
        "promotion_gate_status": promotion_gate.get("promotion_status") or "missing",
        "profile_impact_open_count": open_profile,
        "profile_impact_critical_count": critical_profile,
        "strict_exact_pending_count": strict_pending,
        "blocked_cross_endpoint_pair_count": blocked_pairs,
        "site_policy_row_count": site_policy_rows,
        "site_class_counts": endpoint_governance.get("site_class_counts") or {},
        "project_memory_open_like_count": open_like,
        "rollback_target_policy_version": active_compare.get("rollback_target_policy_version"),
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase", "real_experiment_feedback"],
        "recommended_next_actions": [
            "Clear profile-impact review rows or explicitly defer them before the next policy/profile promotion.",
            "Keep strict endpoint gaps visible; do not close them with cross-endpoint evidence.",
            "Use site-class endpoint actions to route methoxy, ester, basic amine, and terminal-tail risks to the right local review lane.",
            "Use this packet as the local promotion-readiness handoff instead of real experiment feedback.",
        ],
    }


def write_promotion_readiness_packet(
    report: dict,
    output_path: str | Path = DEFAULT_PROMOTION_READINESS_PACKET_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_PROMOTION_READINESS_PACKET_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    fieldnames = ["section", "status", "primary_count", "secondary_count", "details"]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.get("summary_rows") or []:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
