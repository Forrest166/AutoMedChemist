from __future__ import annotations

import json
from pathlib import Path

import yaml
from rdkit.Chem import AllChem

from .chemistry import canonicalize_smiles
from .activity import load_activity_evidence, validate_activity_evidence
from .functional_groups import load_functional_group_rules
from .library import ensure_list, load_records, load_yaml_records, validate_library
from .mmp import load_mmp_evidence, validate_mmp_evidence
from .ring_library import load_yaml_collection, validate_ring_substituent_collections
from .review import REVIEW_STATUSES
from .scaffold_calibration import calibrate_scaffold_rules, load_scaffold_calibration_cases
from .scaffold_replacements import load_scaffold_replacements, validate_scaffold_replacements
from .synthesis import load_synthesis_routes, validate_synthesis_routes
from .transform_governance import load_transform_rules, validate_transform_rules
from .transform_priors import load_transform_priors, validate_transform_priors
from .vendor import load_vendor_overlay


DEFAULT_PATHS = {
    "seed_libraries": [
        Path("data/seeds/core_substituent_seed.yaml"),
        Path("data/seeds/pubchem_expansion_seed.yaml"),
    ],
    "built_library": Path("data/substituents/core_substituent_library.yaml"),
    "site_rules": Path("data/rules/site_smarts.yaml"),
    "direction_rules": Path("data/rules/direction_rules.yaml"),
    "functional_rules": Path("data/rules/functional_group_replacements.yaml"),
    "transform_priors": Path("data/rules/transform_priors.yaml"),
    "mmp_evidence": Path("data/mmp/chembl_mmp_transform_evidence.yaml"),
    "chembl_activity": Path("data/activity/chembl_activity_evidence.yaml"),
    "transform_activity_report": Path("data/substituents/transform_activity_report.json"),
    "ring_library": Path("data/rings/ring_system_library.yaml"),
    "literature_substituents": Path("data/substituents/literature_substituent_library.yaml"),
    "ring_replacements": Path("data/replacements/ring_replacements.yaml"),
    "rgroup_replacements": Path("data/replacements/rgroup_replacements.yaml"),
    "vendor_overlay": Path("data/vendor/reagent_availability_overlay.csv"),
    "synthesis_routes": Path("data/vendor/synthesis_route_templates.yaml"),
    "scaffold_replacements": Path("data/rules/scaffold_replacements.yaml"),
    "scaffold_calibration_set": Path("data/rules/scaffold_calibration_set.yaml"),
    "warning_policy": Path("data/rules/quality_warning_policy.yaml"),
    "pubchem_metadata": Path("data/raw/pubchem_substituent_metadata.json"),
}


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")) or {}


def _add_issue(issues: list[dict], severity: str, check: str, message: str, item_id: str | None = None) -> None:
    issues.append({"severity": severity, "check": check, "message": message, "item_id": item_id})


def _load_warning_policy(path: Path) -> dict:
    if not path.exists():
        return {"accepted_warnings": [], "must_fix_warnings": [], "default_warning_status": "must_fix"}
    return _load_yaml(path)


def _policy_lookup(policy: dict, section: str) -> dict[str, dict]:
    return {str(item.get("check")): item for item in policy.get(section) or [] if item.get("check")}


def apply_warning_governance(report: dict, policy: dict) -> dict:
    accepted = _policy_lookup(policy, "accepted_warnings")
    must_fix = _policy_lookup(policy, "must_fix_warnings")
    default_status = str(policy.get("default_warning_status") or "must_fix")
    accepted_count = 0
    must_fix_count = 0
    governed = []
    for issue in report.get("issues") or []:
        if issue.get("severity") != "warning":
            governed.append(issue)
            continue
        check = str(issue.get("check") or "")
        if check in accepted:
            policy_item = accepted[check]
            status = "accepted"
            accepted_count += 1
        elif check in must_fix:
            policy_item = must_fix[check]
            status = "must_fix"
            must_fix_count += 1
        else:
            policy_item = {}
            status = default_status
            if status == "accepted":
                accepted_count += 1
            else:
                must_fix_count += 1
        governed.append(
            {
                **issue,
                "governance_status": status,
                "governance_category": policy_item.get("category") or "uncategorized",
                "governance_rationale": policy_item.get("rationale"),
            }
        )
    raw_warning_count = sum(1 for issue in governed if issue.get("severity") == "warning")
    return {
        **report,
        "issues": governed,
        "raw_warning_count": raw_warning_count,
        "accepted_warning_count": accepted_count,
        "must_fix_warning_count": must_fix_count,
        "warning_count": must_fix_count,
        "warning_governance": {
            "policy_version": policy.get("version"),
            "raw_warning_count": raw_warning_count,
            "accepted_warning_count": accepted_count,
            "must_fix_warning_count": must_fix_count,
        },
    }


def validate_data_quality(root: str | Path = ".", paths: dict | None = None) -> dict:
    root = Path(root)
    paths = {**DEFAULT_PATHS, **(paths or {})}

    def resolve(value):
        if isinstance(value, list):
            return [resolve(item) for item in value if Path(item).exists() or (root / item).exists()]
        path = Path(value)
        return root / path if not path.is_absolute() else path

    paths = {key: resolve(value) for key, value in paths.items()}
    warning_policy = _load_warning_policy(paths["warning_policy"])
    issues: list[dict] = []

    site_rules = _load_yaml(paths["site_rules"])
    site_types = set((site_rules.get("site_types") or {}).keys())
    compatible_by_site = {
        site_type: set((definition or {}).get("compatible_connection_types") or [])
        for site_type, definition in (site_rules.get("site_types") or {}).items()
    }

    direction_rules = _load_yaml(paths["direction_rules"])
    direction_defs = direction_rules.get("directions") or {}
    direction_tags = set(direction_defs.keys())
    for definition in direction_defs.values():
        direction_tags.update(definition.get("include_tags") or [])

    seed_records = load_records(paths["seed_libraries"])
    built_records = load_yaml_records(paths["built_library"])
    _, seed_errors = validate_library(seed_records)
    _, built_errors = validate_library(built_records)
    for error in seed_errors:
        _add_issue(issues, "error", "seed_library_validation", "; ".join(error["errors"]), error.get("substituent_id"))
    for error in built_errors:
        _add_issue(issues, "error", "built_library_validation", "; ".join(error["errors"]), error.get("substituent_id"))

    seen_canonical: dict[str, str] = {}
    for record in built_records:
        sid = record.get("substituent_id")
        try:
            canonical = canonicalize_smiles(record["smiles"])
        except Exception as exc:
            _add_issue(issues, "error", "canonicalize", str(exc), sid)
            continue
        if canonical in seen_canonical:
            _add_issue(issues, "error", "duplicate_canonical", f"Duplicate with {seen_canonical[canonical]}", sid)
        seen_canonical[canonical] = sid

        connection_type = record.get("connection_type")
        for site_type in ensure_list(record.get("allowed_site_types")):
            if site_type not in site_types:
                _add_issue(issues, "error", "unknown_site_type", site_type, sid)
                continue
            compatible = compatible_by_site.get(site_type, set())
            if compatible and connection_type not in compatible:
                review_or_rule_site = site_type in {"ester_region", "acid_region", "basic_amine", "methoxy_position"}
                severity = "warning" if review_or_rule_site else "error"
                _add_issue(
                    issues,
                    severity,
                    "connection_site_incompatibility",
                    f"{connection_type} is not compatible with {site_type}",
                    sid,
                )

        for tag in ensure_list(record.get("direction_tags")):
            if tag not in direction_tags:
                _add_issue(issues, "warning", "unknown_direction_tag", tag, sid)

        review = record.get("review") or {}
        if review.get("status") not in REVIEW_STATUSES:
            _add_issue(issues, "error", "review_status", f"Invalid status {review.get('status')}", sid)
        if not review.get("use_cases"):
            _add_issue(issues, "warning", "review_use_cases", "Missing use_cases", sid)
        if not review.get("avoid_contexts"):
            _add_issue(issues, "warning", "review_avoid_contexts", "Missing avoid_contexts", sid)
        if not record.get("version_history"):
            _add_issue(issues, "error", "version_history", "Missing version history", sid)
        if not (record.get("source", {}).get("pubchem", {}) or {}).get("properties"):
            _add_issue(issues, "warning", "pubchem_metadata", "Missing PubChem properties", sid)

    functional_rules = load_functional_group_rules(paths["functional_rules"])
    for rule in functional_rules:
        rid = rule.get("rule_id")
        for required in ["rule_id", "name", "strategy", "site_types", "direction_tags", "priority"]:
            if not rule.get(required):
                _add_issue(issues, "error", "functional_rule_required_field", f"Missing {required}", rid)
        for site_type in ensure_list(rule.get("site_types")):
            if site_type not in site_types:
                _add_issue(issues, "error", "functional_rule_site_type", f"Unknown site type {site_type}", rid)
        if rule.get("strategy") == "reaction_smarts":
            try:
                rxn = AllChem.ReactionFromSmarts(rule.get("reaction_smarts", ""))
                if rxn is None:
                    _add_issue(issues, "error", "functional_rule_reaction_smarts", "RDKit returned None", rid)
            except Exception as exc:
                _add_issue(issues, "error", "functional_rule_reaction_smarts", str(exc), rid)

    transform_report = validate_transform_rules(load_transform_rules(paths["functional_rules"]))
    for issue in transform_report["issues"]:
        _add_issue(issues, issue["severity"], "transform_rule_governance", issue["message"], issue.get("rule_id"))

    prior_report = validate_transform_priors(
        load_transform_priors(paths["transform_priors"]),
        known_rule_ids={rule.get("rule_id") for rule in functional_rules},
    )
    for issue in prior_report["issues"]:
        _add_issue(issues, issue["severity"], "transform_prior_governance", issue["message"], issue.get("rule_id"))

    mmp_rows = load_mmp_evidence(paths["mmp_evidence"])
    mmp_report = validate_mmp_evidence(mmp_rows)
    for issue in mmp_report["issues"]:
        _add_issue(issues, issue["severity"], issue["check"], issue["message"], issue.get("item_id"))

    activity_rows = load_activity_evidence(paths["chembl_activity"])
    activity_report = validate_activity_evidence(activity_rows)
    for issue in activity_report["issues"]:
        _add_issue(issues, issue["severity"], issue["check"], issue["message"], issue.get("item_id"))
    transform_activity_report = _load_json(paths["transform_activity_report"])
    transform_activity_summaries = list(transform_activity_report.get("summaries") or [])
    for summary in transform_activity_summaries:
        summary_id = summary.get("summary_id")
        if not summary_id:
            _add_issue(issues, "error", "transform_activity_summary_id", "Missing summary_id")
        if summary.get("activity_cliff_count", 0) > summary.get("target_summary_count", 0):
            _add_issue(issues, "error", "transform_activity_counts", "activity_cliff_count exceeds target_summary_count", summary_id)

    ring_records = load_yaml_collection(paths["ring_library"], "ring_systems")
    literature_substituents = load_yaml_collection(paths["literature_substituents"], "literature_substituents")
    ring_replacements = load_yaml_collection(paths["ring_replacements"], "ring_replacements")
    rgroup_replacements = load_yaml_collection(paths["rgroup_replacements"], "rgroup_replacements")
    ring_substituent_report = validate_ring_substituent_collections(
        ring_records,
        literature_substituents,
        ring_replacements,
        rgroup_replacements,
    )
    for issue in ring_substituent_report["issues"]:
        _add_issue(issues, issue["severity"], issue["check"], issue["message"], issue.get("item_id"))

    vendor_rows = load_vendor_overlay(paths["vendor_overlay"])
    for idx, row in enumerate(vendor_rows, start=1):
        if not row.get("record_key"):
            _add_issue(issues, "error", "vendor_overlay_record_key", "Missing record_key", str(idx))
        if row.get("availability_tier") not in {"in_stock", "building_block", "reagent_route", "custom_route", "unknown", "unavailable"}:
            _add_issue(issues, "warning", "vendor_overlay_tier", f"Unexpected availability_tier {row.get('availability_tier')}", str(idx))

    synthesis_report = validate_synthesis_routes(load_synthesis_routes(paths["synthesis_routes"]))
    for issue in synthesis_report["issues"]:
        _add_issue(issues, issue["severity"], issue["check"], issue["message"], issue.get("item_id"))

    scaffold_report = validate_scaffold_replacements(load_scaffold_replacements(paths["scaffold_replacements"]))
    for issue in scaffold_report["issues"]:
        _add_issue(issues, issue["severity"], issue["check"], issue["message"], issue.get("item_id"))
    scaffold_calibration_cases = load_scaffold_calibration_cases(paths["scaffold_calibration_set"])
    scaffold_rule_ids = {rule.get("scaffold_rule_id") for rule in load_scaffold_replacements(paths["scaffold_replacements"])}
    for case in scaffold_calibration_cases:
        if case.get("scaffold_rule_id") not in scaffold_rule_ids:
            _add_issue(issues, "error", "scaffold_calibration_rule_id", "Unknown scaffold_rule_id in calibration case.", case.get("case_id"))
    scaffold_calibration_report = calibrate_scaffold_rules(scaffold_calibration_cases)

    error_count = sum(1 for issue in issues if issue["severity"] == "error")
    raw_warning_count = sum(1 for issue in issues if issue["severity"] == "warning")
    report = {
        "ok": error_count == 0,
        "error_count": error_count,
        "warning_count": raw_warning_count,
        "seed_count": len(seed_records),
        "built_count": len(built_records),
        "functional_rule_count": len(functional_rules),
        "transform_prior_count": prior_report["prior_count"],
        "mmp_evidence_count": mmp_report["evidence_count"],
        "chembl_activity_count": activity_report["activity_count"],
        "transform_activity_summary_count": len(transform_activity_summaries),
        "ring_system_count": ring_substituent_report["ring_count"],
        "literature_substituent_count": ring_substituent_report["literature_substituent_count"],
        "ring_replacement_count": ring_substituent_report["ring_replacement_count"],
        "rgroup_replacement_count": ring_substituent_report["rgroup_replacement_count"],
        "vendor_overlay_count": len(vendor_rows),
        "synthesis_route_count": synthesis_report["route_count"],
        "scaffold_replacement_count": scaffold_report["scaffold_replacement_count"],
        "scaffold_calibration_case_count": scaffold_calibration_report["case_count"],
        "site_type_count": len(site_types),
        "issues": issues,
    }
    return apply_warning_governance(report, warning_policy)


def save_quality_report(report: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
