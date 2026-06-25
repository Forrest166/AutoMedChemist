from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SITE_CLASS_POLICY_PACK_JSON = Path("data/projects/demo/site_class_policy_pack.json")
DEFAULT_SITE_CLASS_POLICY_PACK_CSV = Path("data/projects/demo/site_class_policy_pack.csv")

SITE_CLASS_ENDPOINT_POLICIES: dict[str, dict[str, Any]] = {
    "methoxy_position": {
        "site_class": "methoxy_soft_spot",
        "linked_endpoint_groups": ["metabolic_stability", "clearance", "permeability"],
        "governance_action": "review_methoxy_soft_spot_without_cross_endpoint_closure",
        "risk_note": "Aryl methoxy can be a metabolic soft spot; metabolic-stability evidence cannot close a permeability gap.",
        "candidate_guidance": "Prefer OMe bioisosteres or blocked O-dealkylation scans, then keep clearance and permeability evidence separate.",
        "suitable_directions": ["metabolism_blocking", "reduce_lipophilicity", "increase_polarity"],
        "review_required_when": [
            "metabolic-stability gain is used to justify a permeability gap",
            "clearance risk is inferred without an exact local endpoint record",
        ],
        "example_smiles": ["COc1ccc(Cl)cc1", "COc1ccc(F)cc1"],
    },
    "ester_region": {
        "site_class": "ester",
        "linked_endpoint_groups": ["metabolic_stability", "clearance", "solubility"],
        "governance_action": "review_ester_hydrolysis_risk_without_endpoint_remap",
        "risk_note": "Ester hydrolysis risk is endpoint-specific and should stay separate from permeability closure.",
        "candidate_guidance": "Prioritize amide, oxadiazole-like, or polarity-balanced replacements and keep hydrolysis closure explicit.",
        "suitable_directions": ["reduce_hydrolysis", "metabolism_blocking", "improve_solubility"],
        "review_required_when": [
            "ester removal changes ionization or passive permeability assumptions",
            "hydrolysis risk is closed from a non-hydrolysis endpoint",
        ],
        "example_smiles": ["COC(=O)c1ccccc1", "CCOC(=O)c1ccc(F)cc1"],
    },
    "basic_amine": {
        "site_class": "basic_amine",
        "linked_endpoint_groups": ["solubility", "permeability", "hERG", "toxicity"],
        "governance_action": "review_basicity_tradeoff_without_endpoint_remap",
        "risk_note": "Basic amine changes often trade solubility, permeability, and off-target risk; keep each endpoint explicit.",
        "candidate_guidance": "Use pKa-lowering, dealkylation, N-oxide, or capping scans with explicit solubility/permeability/off-target tradeoff labels.",
        "suitable_directions": ["reduce_basicity", "improve_solubility", "reduce_lipophilicity"],
        "review_required_when": [
            "solubility improvement is assumed to imply permeability improvement",
            "basicity reduction may change hERG or toxicity risk",
        ],
        "example_smiles": ["CCN(CC)CC", "CCNC"],
    },
    "alkyl_terminal": {
        "site_class": "terminal_tail",
        "linked_endpoint_groups": ["metabolic_stability", "permeability", "clearance"],
        "governance_action": "review_terminal_tail_soft_spot_without_endpoint_remap",
        "risk_note": "Terminal tails can drive soft-spot and permeability changes; endpoint gaps remain strict.",
        "candidate_guidance": "Prefer tail shortening, terminal fluorination, or polarity capping scans and avoid automatic endpoint remapping.",
        "suitable_directions": ["increase_polarity", "metabolism_blocking", "reduce_lipophilicity"],
        "review_required_when": [
            "tail polarity is used to close clearance without exact endpoint evidence",
            "terminal soft-spot block changes permeability assumptions",
        ],
        "example_smiles": ["CCCCc1ccccc1", "CCCOc1ccccc1"],
    },
}


def site_class_guidance_for_site(site: Any) -> dict[str, Any]:
    site_type = getattr(site, "site_type", None)
    if isinstance(site, dict):
        site_type = site.get("site_type")
    policy = SITE_CLASS_ENDPOINT_POLICIES.get(str(site_type or ""))
    if not policy:
        return {
            "site_class": str(site_type or ""),
            "site_class_endpoint_groups": "",
            "site_class_governance_action": "",
            "site_class_risk_note": "",
            "site_class_candidate_guidance": "",
            "site_class_requires_review": False,
        }
    return {
        "site_class": policy["site_class"],
        "site_class_endpoint_groups": ";".join(policy["linked_endpoint_groups"]),
        "site_class_governance_action": policy["governance_action"],
        "site_class_risk_note": policy["risk_note"],
        "site_class_candidate_guidance": policy["candidate_guidance"],
        "site_class_requires_review": True,
    }


def annotate_rows_with_site_class_guidance(rows: list[dict], site: Any) -> list[dict]:
    guidance = site_class_guidance_for_site(site)
    for row in rows:
        row.update(guidance)
        reason = str(row.get("recommendation_reason") or "")
        note = str(guidance.get("site_class_candidate_guidance") or "")
        if note and note not in reason:
            row["recommendation_reason"] = f"{reason}; site-class guidance: {note}" if reason else f"site-class guidance: {note}"
    return rows


def build_site_class_policy_pack(root: str | Path = ".") -> dict:
    root_path = Path(root)
    rows = []
    for site_type, policy in SITE_CLASS_ENDPOINT_POLICIES.items():
        rows.append(
            {
                "site_type": site_type,
                "site_class": policy["site_class"],
                "linked_endpoint_groups": ";".join(policy["linked_endpoint_groups"]),
                "governance_action": policy["governance_action"],
                "risk_note": policy["risk_note"],
                "candidate_guidance": policy["candidate_guidance"],
                "suitable_directions": ";".join(policy["suitable_directions"]),
                "review_required_when": ";".join(policy["review_required_when"]),
                "example_smiles": ";".join(policy["example_smiles"]),
                "review_status": "curated_non_experimental_policy",
                "version": "site_class_policy_pack_v1",
                "change_log": "v1: added candidate-facing guidance for methoxy, ester, basic amine, and terminal tail governance.",
            }
        )
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready",
        "mode": "non_experimental_site_class_policy_pack",
        "row_count": len(rows),
        "site_classes": [row["site_class"] for row in rows],
        "real_experiment_feedback_used": False,
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
        "rows": rows,
    }


def write_site_class_policy_pack(
    report: dict,
    json_path: str | Path = DEFAULT_SITE_CLASS_POLICY_PACK_JSON,
    csv_path: str | Path = DEFAULT_SITE_CLASS_POLICY_PACK_CSV,
) -> None:
    json_file = Path(json_path)
    csv_file = Path(csv_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    rows = report.get("rows") or []
    fieldnames = list(rows[0].keys()) if rows else [
        "site_type",
        "site_class",
        "linked_endpoint_groups",
        "governance_action",
        "risk_note",
        "candidate_guidance",
        "suitable_directions",
        "review_required_when",
        "example_smiles",
        "review_status",
        "version",
        "change_log",
    ]
    with csv_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
