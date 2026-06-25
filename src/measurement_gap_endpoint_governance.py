from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from rdkit import Chem

from .site_class_guidance import SITE_CLASS_ENDPOINT_POLICIES
from .sites import detect_modification_sites


DEFAULT_MEASUREMENT_GAP_ENDPOINT_GOVERNANCE_PATH = Path("data/projects/demo/measurement_gap_endpoint_governance.json")
DEFAULT_MEASUREMENT_GAP_ENDPOINT_GOVERNANCE_CSV_PATH = Path("data/projects/demo/measurement_gap_endpoint_governance.csv")

GOVERNED_ENDPOINT_GROUPS = [
    "potency",
    "selectivity",
    "permeability",
    "solubility",
    "metabolic_stability",
    "clearance",
    "hERG",
    "toxicity",
]

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


def _split_endpoints(value: object) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").replace(",", ";").split(";")
    endpoints = []
    for item in raw_items:
        endpoint = str(item or "").strip()
        if endpoint and endpoint not in endpoints:
            endpoints.append(endpoint)
    return endpoints


def _strict_status(row: dict, pending_ids: set[str]) -> str:
    closure = str(row.get("closure_status") or "")
    plan_id = str(row.get("measurement_plan_id") or "")
    exact_count = int(row.get("exact_result_count") or 0)
    mismatch_count = int(row.get("endpoint_mismatch_count") or 0)
    if closure == "manual_endpoint_remap_approved":
        return "manual_remap_recorded_not_automatic"
    if closure == "deferred":
        return "deferred"
    if exact_count:
        return "exact_endpoint_ready_for_import"
    if closure in {"exact_measurement_required", "needs_new_measured_feedback"} or plan_id in pending_ids:
        return "strict_exact_endpoint_pending"
    if closure == "manual_endpoint_confirmation_required" or mismatch_count:
        return "cross_endpoint_blocked"
    return "closed_or_not_applicable"


def _site_context(smiles: str) -> dict:
    mol = Chem.MolFromSmiles(str(smiles or ""))
    if mol is None:
        return {
            "site_classes": [],
            "site_policy_rows": [],
            "site_class_endpoint_groups": [],
            "site_class_actions": [],
            "site_detection_status": "invalid_smiles",
        }
    sites = detect_modification_sites(mol)
    policy_rows = []
    endpoint_groups: list[str] = []
    actions: list[str] = []
    site_classes: list[str] = []
    for site in sites:
        policy = SITE_CLASS_ENDPOINT_POLICIES.get(site.site_type)
        if not policy:
            continue
        site_class = str(policy.get("site_class") or site.site_type)
        if site_class not in site_classes:
            site_classes.append(site_class)
        action = str(policy.get("governance_action") or "")
        if action and action not in actions:
            actions.append(action)
        for endpoint in policy.get("linked_endpoint_groups") or []:
            endpoint = str(endpoint)
            if endpoint and endpoint not in endpoint_groups:
                endpoint_groups.append(endpoint)
        policy_rows.append(
            {
                "site_id": site.site_id,
                "site_type": site.site_type,
                "site_class": site_class,
                "atom_idx": site.atom_idx,
                "operation_type": site.operation_type,
                "enumeration_ready": site.enumeration_ready,
                "linked_endpoint_groups": ";".join(policy.get("linked_endpoint_groups") or []),
                "governance_action": action,
                "risk_note": policy.get("risk_note") or "",
            }
        )
    return {
        "site_classes": site_classes,
        "site_policy_rows": policy_rows,
        "site_class_endpoint_groups": endpoint_groups,
        "site_class_actions": actions,
        "site_detection_status": "ready",
    }


def build_measurement_gap_endpoint_governance(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    gap_closure_path: str | Path = "data/projects/demo/measurement_feedback_gap_closure.json",
    exact_intake_path: str | Path = "data/projects/demo/measurement_gap_exact_result_intake.json",
) -> dict:
    root_path = Path(root)
    gap_file = _resolve(root_path, gap_closure_path)
    exact_file = _resolve(root_path, exact_intake_path)
    gap_closure = _read_json(gap_file)
    exact_intake = _read_json(exact_file)
    pending_ids = {str(item) for item in exact_intake.get("pending_measurement_plan_ids") or [] if str(item)}
    rows = []
    pair_rows = []
    site_policy_rows = []
    for raw in gap_closure.get("rows") or []:
        row = dict(raw)
        plan_id = str(row.get("measurement_plan_id") or "")
        required = str(row.get("required_endpoint_group") or row.get("endpoint_group") or "").strip()
        available = _split_endpoints(row.get("available_endpoint_groups"))
        status = _strict_status(row, pending_ids)
        site_context = _site_context(str(row.get("smiles") or ""))
        site_classes = site_context["site_classes"]
        site_endpoint_groups = site_context["site_class_endpoint_groups"]
        endpoint_linked_site_classes = [
            str(site_row.get("site_class") or "")
            for site_row in site_context["site_policy_rows"]
            if required in _split_endpoints(site_row.get("linked_endpoint_groups"))
        ]
        endpoint_linked_site_classes = list(dict.fromkeys(item for item in endpoint_linked_site_classes if item))
        rows.append(
            {
                "measurement_plan_id": plan_id,
                "candidate_id": row.get("candidate_id"),
                "queue_id": row.get("queue_id"),
                "required_endpoint_group": required,
                "available_endpoint_groups": ";".join(available),
                "site_classes": ";".join(site_classes),
                "site_class_endpoint_groups": ";".join(site_endpoint_groups),
                "endpoint_linked_site_classes": ";".join(endpoint_linked_site_classes),
                "site_class_actions": ";".join(site_context["site_class_actions"]),
                "site_detection_status": site_context["site_detection_status"],
                "closure_status": row.get("closure_status"),
                "strict_endpoint_status": status,
                "exact_intake_status": "pending" if plan_id in pending_ids else "not_pending",
                "blocked_cross_endpoint_count": len([endpoint for endpoint in available if endpoint != required]),
                "review_action": row.get("review_action"),
                "decision_needed": (
                    "collect_required_endpoint_only"
                    if status == "strict_exact_endpoint_pending"
                    else "keep_cross_endpoint_blocked"
                    if status == "cross_endpoint_blocked"
                    else "manual_governance_record_only"
                    if status == "manual_remap_recorded_not_automatic"
                    else "none"
                ),
                "source_artifact": "measurement_feedback_gap_closure",
            }
        )
        for site_row in site_context["site_policy_rows"]:
            site_row.update(
                {
                    "measurement_plan_id": plan_id,
                    "candidate_id": row.get("candidate_id"),
                    "queue_id": row.get("queue_id"),
                    "required_endpoint_group": required,
                    "strict_endpoint_status": status,
                }
            )
            site_policy_rows.append(site_row)
        compared = available or ([required] if required else [])
        for available_endpoint in compared:
            is_cross_endpoint = bool(required and available_endpoint != required)
            if status == "deferred" and is_cross_endpoint:
                pair_status = "deferred_cross_endpoint"
            else:
                pair_status = "strict_match" if required and available_endpoint == required else "blocked_cross_endpoint"
            pair_rows.append(
                {
                    "measurement_plan_id": plan_id,
                    "candidate_id": row.get("candidate_id"),
                    "required_endpoint_group": required,
                    "available_endpoint_group": available_endpoint,
                    "pair_status": pair_status,
                    "automatic_mapping_allowed": False if is_cross_endpoint else bool(required),
                }
            )
    status_counts = Counter(str(row.get("strict_endpoint_status") or "unknown") for row in rows)
    required_counts = Counter(str(row.get("required_endpoint_group") or "unknown") for row in rows)
    site_class_counts = Counter(
        site_class
        for row in rows
        for site_class in _split_endpoints(row.get("site_classes"))
    )
    site_endpoint_action_count = sum(1 for row in rows if row.get("site_classes"))
    blocked_pair_count = sum(1 for row in pair_rows if row.get("pair_status") == "blocked_cross_endpoint")
    pending_count = status_counts.get("strict_exact_endpoint_pending", 0)
    blocked_count = status_counts.get("cross_endpoint_blocked", 0)
    status = "empty" if not rows else "attention_required" if pending_count or blocked_count else "ready"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "non_experimental_endpoint_governance",
        "project_name": project_name,
        "row_count": len(rows),
        "pair_row_count": len(pair_rows),
        "site_policy_row_count": len(site_policy_rows),
        "governed_endpoint_groups": GOVERNED_ENDPOINT_GROUPS,
        "required_endpoint_counts": dict(required_counts.most_common()),
        "strict_endpoint_status_counts": dict(status_counts.most_common()),
        "site_class_counts": dict(site_class_counts.most_common()),
        "site_class_endpoint_action_count": site_endpoint_action_count,
        "strict_exact_pending_count": pending_count,
        "cross_endpoint_blocked_count": blocked_count,
        "blocked_cross_endpoint_pair_count": blocked_pair_count,
        "exact_intake_status": exact_intake.get("status") or "missing",
        "gap_closure_status": gap_closure.get("status") or "missing",
        "real_experiment_feedback_used": False,
        "rows": rows,
        "endpoint_pair_rows": pair_rows,
        "site_policy_rows": site_policy_rows,
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase", "real_experiment_feedback"],
        "recommended_next_actions": [
            "Keep endpoint closure strict: required_endpoint_group must equal the imported/local endpoint_group.",
            "Use exact-intake rows only as local governance placeholders until a project-approved data source exists.",
            "Treat cross-endpoint pairs as blocked unless a separate manual governance record says otherwise.",
            "Route methoxy, ester, basic amine, and terminal-tail site classes to endpoint-specific local review actions.",
        ],
    }


def write_measurement_gap_endpoint_governance(
    report: dict,
    output_path: str | Path = DEFAULT_MEASUREMENT_GAP_ENDPOINT_GOVERNANCE_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_MEASUREMENT_GAP_ENDPOINT_GOVERNANCE_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    fieldnames = [
        "measurement_plan_id",
        "candidate_id",
        "queue_id",
        "required_endpoint_group",
        "available_endpoint_groups",
        "site_classes",
        "site_class_endpoint_groups",
        "endpoint_linked_site_classes",
        "site_class_actions",
        "site_detection_status",
        "closure_status",
        "strict_endpoint_status",
        "exact_intake_status",
        "blocked_cross_endpoint_count",
        "review_action",
        "decision_needed",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.get("rows") or []:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
