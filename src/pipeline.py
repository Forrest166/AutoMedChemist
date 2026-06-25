from __future__ import annotations

from pathlib import Path

from rdkit import Chem

from .analog_series import annotate_queue_analog_series_delta_prior, build_analog_series_report
from .assay_learning import annotate_endpoint_gates, build_assay_learning_report
from .chemistry import calculate_descriptors, mol_from_smiles, standardize_molecule
from .enumeration import enumerate_candidates
from .evidence_confidence import annotate_evidence_confidence_calibration
from .evidence_scoring import annotate_evidence_consistency
from .export import export_csv, export_sdf
from .functional_groups import enumerate_functional_group_replacements, load_functional_group_rules
from .analysis import annotate_diverse_top_n, cluster_candidates, group_summary, property_summary
from .batch_design import route_batch_summary, write_route_batch_exports
from .candidate_explanations import annotate_candidate_explanations
from .library import SubstituentIndex, load_yaml_records
from .mmp import load_mmp_evidence
from .multi_objective import multi_objective_score_for_candidate
from .novelty_batch import annotate_novelty_diversity_batch, novelty_batch_summary
from .replacement_network import (
    enumerate_replacement_network_candidates,
    load_rgroup_replacement_records,
    load_ring_replacement_records,
    replacement_network_summary,
)
from .residual_profile_adjustments import endpoint_family_residual_adjustment_for_candidate
from .enumeration import Candidate
from .ring_search import annotate_ring_replacement_buckets, score_candidate_ring_evidence
from .ring_outcome_overlay import annotate_ring_outcome_learning_overlay
from .ring_library_enumeration import enumerate_ring_library_candidates, enumerate_ring_rgroup_joint_candidates
from .scaffold_calibration import apply_scaffold_context_calibration, calibration_lookup, load_scaffold_calibration_report
from .scaffold_local_evidence import annotate_scaffold_local_evidence
from .scaffold_rule_review import (
    apply_scaffold_rule_review_to_row,
    apply_scaffold_rule_reviews_to_rules,
    load_scaffold_rule_reviews,
    scaffold_rule_review_lookup,
)
from .scaffold_replacements import enumerate_scaffold_replacements, load_scaffold_replacements
from .scoring import (
    component_weights,
    direction_include_tags,
    final_score,
    load_direction_rules,
    recommendation_reason,
    score_direction,
    score_property_profile,
    score_risk,
    score_similarity,
    score_synthetic_access,
    tanimoto_similarity,
)
from .sar_neighborhood import annotate_sar_neighborhoods, load_sar_neighborhood_data
from .site_class_guidance import annotate_rows_with_site_class_guidance, site_class_guidance_for_site
from .sites import detect_modification_sites
from .strategy_learning import annotate_strategy_learning_prior
from .synthesis import load_synthesis_routes, route_summary, score_synthesis_route
from .transform_evidence import annotate_mmp_precedents, evidence_from_prior
from .transform_activity_scoring import load_transform_activity_report, score_transform_activity, transform_activity_lookup
from .transform_priors import load_transform_priors, score_transform_prior, transform_prior_lookup
from .vendor import availability_summary, score_vendor_availability
from .profiles import load_scoring_profile, profile_weights
from .public_sar import annotate_public_strategy_signal


def _candidate_source_priority(candidate: Candidate) -> int:
    priority = {
        "substituent_scan": 0,
        "functional_group_replacement": 1,
        "scaffold_replacement": 2,
        "rgroup_network_replacement": 3,
        "ring_network_replacement": 3,
        "ring_library_recommendation": 4,
        "ring_rgroup_joint_recommendation": 5,
    }
    return priority.get(candidate.enumeration_type, 9)


def deduplicate_candidates_with_evidence(candidates: list[Candidate]) -> tuple[list[Candidate], dict[str, dict]]:
    grouped: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.smiles, []).append(candidate)
    deduped: list[Candidate] = []
    evidence: dict[str, dict] = {}
    for smiles, items in grouped.items():
        primary = sorted(items, key=_candidate_source_priority)[0]
        deduped.append(primary)
        if len(items) > 1:
            evidence[primary.candidate_id] = {
                "duplicate_candidate_ids": ";".join(item.candidate_id for item in items if item.candidate_id != primary.candidate_id),
                "enumeration_sources": ";".join(dict.fromkeys(item.enumeration_type for item in items)),
                "evidence_trails": [
                    {
                        "candidate_id": item.candidate_id,
                        "substituent_id": item.substituent_id,
                        "replacement_label": item.replacement_label,
                        "enumeration_type": item.enumeration_type,
                        "functional_rule_id": item.functional_rule_id,
                    }
                    for item in items
                ],
            }
    deduped.sort(key=lambda item: (_candidate_source_priority(item), item.candidate_id))
    return deduped, evidence


def run_mvp(
    smiles: str,
    direction: str,
    library_path: str | Path = "data/substituents/core_substituent_library.yaml",
    direction_rules_path: str | Path = "data/rules/direction_rules.yaml",
    functional_rules_path: str | Path = "data/rules/functional_group_replacements.yaml",
    transform_priors_path: str | Path = "data/rules/transform_priors.yaml",
    transform_activity_report_path: str | Path = "data/substituents/transform_activity_report.json",
    evidence_confidence_report_path: str | Path = "data/substituents/evidence_confidence_report.json",
    public_strategy_signal_report_path: str | Path = "data/substituents/public_strategy_signal_report.json",
    ring_outcome_learning_report_path: str | Path = "data/projects/demo/ring_outcome_learning_report.json",
    ring_outcome_overlay_review_path: str | Path | None = "data/profiles/calibrated/ring_outcome_overlay_reviews.csv",
    queue_analog_series_delta_path: str | Path | None = "data/projects/closed_loop/queue_analog_series_delta.json",
    queue_analog_series_policy_path: str | Path | None = "data/rules/queue_analog_series_policy.yaml",
    target_context_profiles_path: str | Path = "data/rules/target_context_profiles.yaml",
    strategy_learning_policy_path: str | Path = "data/rules/strategy_learning_policy.yaml",
    mmp_evidence_path: str | Path = "data/mmp/chembl_mmp_transform_evidence.yaml",
    synthesis_routes_path: str | Path = "data/vendor/synthesis_route_templates.yaml",
    rgroup_replacements_path: str | Path = "data/replacements/rgroup_replacements.yaml",
    ring_replacements_path: str | Path = "data/replacements/ring_replacements.yaml",
    scaffold_replacements_path: str | Path = "data/rules/scaffold_replacements.yaml",
    scaffold_rule_reviews_path: str | Path = "data/rules/scaffold_rule_reviews.yaml",
    scaffold_calibration_report_path: str | Path = "data/substituents/scaffold_calibration_report.json",
    scoring_profile_path: str | Path | None = None,
    db_path: str | Path = "data/localmedchem.sqlite",
    project_name: str | None = None,
    target_context: dict | None = None,
    site_index: int = 0,
    max_substituents: int = 80,
    max_candidates: int = 80,
    max_fragment_mw: float | None = None,
    include_risky: bool = False,
    include_advanced: bool = False,
    include_substituent_scan: bool = True,
    include_functional_replacements: bool = True,
    include_replacement_network: bool = True,
    include_scaffold_replacements: bool = True,
    include_ring_library_recommendations: bool = True,
    include_ring_rgroup_joint: bool = True,
    replacement_network_source_fragment: str | None = None,
    max_network_replacements: int = 25,
    max_scaffold_replacements: int = 20,
    max_ring_library_recommendations: int = 12,
    max_ring_library_source_rank: int | None = 5000,
    max_ring_library_per_diversity_bucket: int | None = 2,
    max_ring_library_similarity: float | None = 0.86,
    max_ring_rgroup_joint_candidates: int = 8,
    ring_recommendation_cache_path: str | Path | None = "data/substituents/ring_recommendation_cache.json",
    ring_recommendation_cache_ttl_seconds: int | float | None = 86400,
    score_weights: dict | None = None,
    diverse_top_n: int = 20,
    per_cluster_limit: int = 1,
    novelty_batch_size: int = 24,
    novelty_batch_per_bucket_limit: int = 3,
    output_dir: str | Path | None = None,
) -> dict:
    parent = standardize_molecule(smiles)
    parent_props = calculate_descriptors(parent).to_dict()
    sites = detect_modification_sites(parent)
    if not sites:
        raise ValueError("No supported modification sites found.")
    if site_index >= len(sites):
        raise ValueError(f"site_index {site_index} out of range; found {len(sites)} sites.")
    site = sites[site_index]

    rules = load_direction_rules(direction_rules_path)
    include_tags = direction_include_tags(direction, rules)
    profile = load_scoring_profile(scoring_profile_path) if scoring_profile_path else {}
    if profile:
        profile = {**profile, "path": str(scoring_profile_path)}
    if target_context:
        profile = {**profile, "target_context": {key: value for key, value in target_context.items() if value}}
    merged_score_weights = {**profile_weights(profile), **(score_weights or {})}
    weights = component_weights(rules, overrides=merged_score_weights)
    priors_path = Path(transform_priors_path)
    transform_priors = transform_prior_lookup(load_transform_priors(priors_path)) if priors_path.exists() else {}
    activity_report_path = Path(transform_activity_report_path)
    transform_activity = (
        transform_activity_lookup(load_transform_activity_report(activity_report_path))
        if activity_report_path.exists()
        else {}
    )
    synthesis_routes = load_synthesis_routes(synthesis_routes_path)
    library_records = load_yaml_records(library_path)
    if site.enumeration_ready and include_substituent_scan:
        substituents = SubstituentIndex(library_records).query(
            direction_tags=include_tags,
            site_type=site.site_type,
            compatible_connection_types=site.compatible_connection_types,
            max_fragment_mw=max_fragment_mw,
            include_risky=include_risky,
            include_advanced=include_advanced,
            limit=max_substituents,
        )
        candidates, enumeration_errors = enumerate_candidates(parent, site, substituents, max_candidates=max_candidates)
    else:
        substituents = []
        candidates = []
        enumeration_errors = []

    functional_candidates = []
    functional_errors = []
    functional_scoring_records = []
    network_candidates = []
    network_errors = []
    network_scoring_records = []
    scaffold_candidates = []
    scaffold_errors = []
    scaffold_scoring_records = []
    ring_library_candidates = []
    ring_library_errors = []
    ring_library_scoring_records = []
    ring_library_report = {}
    ring_rgroup_joint_candidates = []
    ring_rgroup_joint_errors = []
    ring_rgroup_joint_scoring_records = []
    rgroup_replacements = load_rgroup_replacement_records(rgroup_replacements_path) if Path(rgroup_replacements_path).exists() else []
    ring_replacements = load_ring_replacement_records(ring_replacements_path) if Path(ring_replacements_path).exists() else []
    ring_sampling_config = profile.get("ring_sampling") or {}
    if ring_replacements:
        ring_replacements = annotate_ring_replacement_buckets(
            ring_replacements,
            db_path=db_path,
            preferred_novelty_buckets=ring_sampling_config.get("preferred_novelty_buckets") or [],
            preferred_diversity_buckets=ring_sampling_config.get("preferred_diversity_buckets") or [],
        )
    network_summary = replacement_network_summary(rgroup_replacements=rgroup_replacements, ring_replacements=ring_replacements)
    if include_replacement_network and site.enumeration_ready:
        network_candidates, network_errors, network_scoring_records = enumerate_replacement_network_candidates(
            parent,
            site,
            rgroup_replacements=rgroup_replacements,
            ring_replacements=ring_replacements,
            source_fragment=replacement_network_source_fragment,
            direction_tags=include_tags,
            max_candidates=max_network_replacements,
        )
        candidates.extend(network_candidates)
        enumeration_errors.extend(network_errors)

    if include_ring_library_recommendations:
        ring_library_candidates, ring_library_errors, ring_library_scoring_records, ring_library_report = enumerate_ring_library_candidates(
            parent,
            site,
            db_path=db_path,
            direction_tags=include_tags,
            max_candidates=max_ring_library_recommendations,
            max_source_rank=max_ring_library_source_rank,
            max_per_diversity_bucket=max_ring_library_per_diversity_bucket,
            max_ring_similarity=max_ring_library_similarity,
            cache_path=ring_recommendation_cache_path,
            cache_ttl_seconds=ring_recommendation_cache_ttl_seconds,
        )
        candidates.extend(ring_library_candidates)
        enumeration_errors.extend(ring_library_errors)

    if include_ring_rgroup_joint and ring_library_candidates:
        ring_rgroup_joint_candidates, ring_rgroup_joint_errors, ring_rgroup_joint_scoring_records = enumerate_ring_rgroup_joint_candidates(
            parent,
            ring_library_candidates,
            ring_library_scoring_records,
            library_records,
            direction_tags=include_tags,
            max_candidates=max_ring_rgroup_joint_candidates,
            include_risky=include_risky,
            include_advanced=include_advanced,
        )
        candidates.extend(ring_rgroup_joint_candidates)
        enumeration_errors.extend(ring_rgroup_joint_errors)

    scaffold_review_data = load_scaffold_rule_reviews(scaffold_rule_reviews_path)
    scaffold_review_lookup = scaffold_rule_review_lookup(scaffold_review_data)
    if include_scaffold_replacements:
        scaffold_rules = apply_scaffold_rule_reviews_to_rules(
            load_scaffold_replacements(scaffold_replacements_path),
            scaffold_review_data,
        )
        scaffold_calibration = {}
        if Path(scaffold_calibration_report_path).exists():
            scaffold_calibration = calibration_lookup(load_scaffold_calibration_report(scaffold_calibration_report_path))
        scaffold_candidates, scaffold_errors, scaffold_scoring_records = enumerate_scaffold_replacements(
            parent,
            site,
            scaffold_rules,
            direction_tags=include_tags,
            include_advanced=include_advanced,
            max_candidates=max_scaffold_replacements,
            calibration_lookup=scaffold_calibration,
        )
        candidates.extend(scaffold_candidates)
        enumeration_errors.extend(scaffold_errors)

    if include_functional_replacements:
        functional_rules = load_functional_group_rules(functional_rules_path)
        functional_candidates, functional_errors, functional_scoring_records = enumerate_functional_group_replacements(
            parent,
            site,
            functional_rules,
            direction_tags=include_tags,
        )
        candidates.extend(functional_candidates)
        enumeration_errors.extend(functional_errors)

    candidates, dedupe_evidence = deduplicate_candidates_with_evidence(candidates)

    if not candidates:
        message = site.support_note if not site.enumeration_ready else "No candidates matched the selected site, direction, and filters."
        selected_site_guidance = site_class_guidance_for_site(site)
        return {
            "parent_smiles": Chem.MolToSmiles(parent, canonical=True),
            "parent_properties": parent_props,
            "sites": [site.to_dict() for site in sites],
            "selected_site": site.to_dict(),
            "selected_site_guidance": selected_site_guidance,
            "substituent_count": len(substituents),
            "functional_replacement_count": len(functional_candidates),
            "network_replacement_count": len(network_candidates),
            "scaffold_replacement_count": len(scaffold_candidates),
            "ring_library_recommendation_count": len(ring_library_candidates),
            "ring_rgroup_joint_recommendation_count": len(ring_rgroup_joint_candidates),
            "replacement_network_summary": network_summary,
            "ring_library_summary": {
                "returned_count": ring_library_report.get("returned_count", 0),
                "total_matching_count": ring_library_report.get("total_matching_count", 0),
                "cache": ring_library_report.get("cache"),
                "diversity_selection": ring_library_report.get("diversity_selection", {}),
            },
            "candidate_count": 0,
            "enumeration_errors": enumeration_errors,
            "candidates": [],
            "score_weights": weights,
            "scoring_profile": profile
            or {
                "profile_id": "default",
                "name": "Default",
                "path": None,
            },
            "status_message": message,
        }

    rows: list[dict] = []
    lookup = {record["substituent_id"]: record for record in substituents}
    lookup.update({record["substituent_id"]: record for record in functional_scoring_records})
    lookup.update({record["substituent_id"]: record for record in network_scoring_records})
    lookup.update({record["substituent_id"]: record for record in scaffold_scoring_records})
    lookup.update({record["substituent_id"]: record for record in ring_library_scoring_records})
    lookup.update({record["substituent_id"]: record for record in ring_rgroup_joint_scoring_records})
    for candidate in candidates:
        mol = mol_from_smiles(candidate.smiles)
        props = calculate_descriptors(mol).to_dict()
        substituent = lookup[candidate.substituent_id]
        direction_score = score_direction(direction, parent_props, props, substituent, rules=rules)
        property_score = score_property_profile(props)
        similarity = tanimoto_similarity(parent, mol)
        similarity_score = score_similarity(similarity)
        synthetic_score = score_synthetic_access(substituent)
        risk = score_risk(substituent)
        transform_prior = transform_priors.get(str(candidate.functional_rule_id)) if candidate.functional_rule_id else None
        transform_prior_score = score_transform_prior(candidate.functional_rule_id, transform_priors)
        transform_activity_evidence = score_transform_activity(candidate.functional_rule_id, transform_activity, profile=profile)
        vendor_score = score_vendor_availability(substituent)
        route_score = score_synthesis_route(substituent, site.site_type, synthesis_routes)
        route = route_summary(substituent, site.site_type, synthesis_routes)
        availability = availability_summary(substituent, site.site_type)
        candidate_payload = candidate.to_dict()
        candidate_metadata = candidate_payload.pop("metadata", {}) or {}
        ring_frequency_score = score_candidate_ring_evidence(candidate_payload, substituent)
        classes = substituent.get("class") or []
        replacement_class = None
        if isinstance(classes, list):
            replacement_class = next((str(item) for item in classes if item and item != candidate.enumeration_type), None)
        elif classes:
            replacement_class = str(classes)
        replacement_class = (
            candidate_metadata.get("replacement_class")
            or (substituent.get("ring_evidence") or {}).get("replacement_class")
            or replacement_class
        )
        row = {
            **candidate_payload,
            **candidate_metadata,
            "direction": direction,
            "replacement_class": replacement_class,
            "mw": props["mw"],
            "delta_mw": round(props["mw"] - parent_props["mw"], 4),
            "clogp": props["clogp"],
            "delta_clogp": round(props["clogp"] - parent_props["clogp"], 4),
            "tpsa": props["tpsa"],
            "delta_tpsa": round(props["tpsa"] - parent_props["tpsa"], 4),
            "hbd": props["hbd"],
            "hba": props["hba"],
            "rotatable_bonds": props["rotatable_bonds"],
            "similarity": round(similarity, 4),
            "direction_score": round(direction_score, 2),
            "property_score": round(property_score, 2),
            "similarity_score": round(similarity_score, 2),
            "synthetic_score": round(synthetic_score, 2),
            "risk_score": round(risk, 2),
            "transform_prior_score": round(transform_prior_score, 2) if transform_prior_score is not None else None,
            "vendor_score": round(vendor_score, 2) if vendor_score is not None else None,
            **availability,
            "route_score": round(route_score, 2) if route_score is not None else None,
            "route_template_id": route.get("template_id") if route else None,
            "route_routine_level": route.get("routine_level") if route else None,
            "route_notes": route.get("notes") if route else None,
            "ring_frequency_score": round(ring_frequency_score, 2) if ring_frequency_score is not None else None,
            **dedupe_evidence.get(candidate.candidate_id, {}),
            **evidence_from_prior(transform_prior),
            **transform_activity_evidence,
            "score": None,
            "recommendation_reason": recommendation_reason(direction, parent_props, props, substituent),
        }
        if row.get("scaffold_context_score") is not None:
            original_context_score = row.get("scaffold_context_score")
            calibrated_context_score = apply_scaffold_context_calibration(original_context_score, profile=profile, row=row)
            row["scaffold_context_score"] = calibrated_context_score
            if calibrated_context_score != original_context_score:
                row["scaffold_context_score_raw"] = original_context_score
        if row.get("enumeration_type") == "scaffold_replacement":
            row = apply_scaffold_rule_review_to_row(row, scaffold_review_lookup)
        if candidate_metadata.get("scaffold_context_flags"):
            row["recommendation_reason"] += f"; scaffold flags: {candidate_metadata['scaffold_context_flags']}"
        rows.append(row)

    selected_site_guidance = site_class_guidance_for_site(site)
    rows = annotate_rows_with_site_class_guidance(rows, site)

    mmp_rows = load_mmp_evidence(mmp_evidence_path) if Path(mmp_evidence_path).exists() else []
    rows = annotate_mmp_precedents(rows, selected_site=site.to_dict(), mmp_rows=mmp_rows)
    sar_data = load_sar_neighborhood_data(rgroup_replacements_path, ring_replacements_path)
    rows = annotate_sar_neighborhoods(rows, sar_data)
    rows = annotate_scaffold_local_evidence(
        rows,
        ring_replacements_path=ring_replacements_path,
        rgroup_replacements_path=rgroup_replacements_path,
        mmp_evidence_path=mmp_evidence_path,
        target_context=profile.get("target_context") or {},
    )
    rows = annotate_evidence_consistency(rows, db_path=db_path, project_name=project_name, profile=profile)
    rows = annotate_evidence_confidence_calibration(
        rows,
        report_path=evidence_confidence_report_path,
        db_path=db_path,
        project_name=project_name,
        target_context=profile.get("target_context") or {},
    )
    rows = annotate_public_strategy_signal(
        rows,
        report_path=public_strategy_signal_report_path,
        db_path=db_path,
        target_context=profile.get("target_context") or {},
    )
    runtime_target_context = profile.get("target_context") or {"endpoint_group": direction}
    rows = annotate_ring_outcome_learning_overlay(
        rows,
        report_path=ring_outcome_learning_report_path,
        review_path=ring_outcome_overlay_review_path,
        target_context=runtime_target_context,
    )
    rows = annotate_strategy_learning_prior(
        rows,
        db_path=db_path,
        project_name=project_name,
        target_context=runtime_target_context,
        policy_path=strategy_learning_policy_path,
    )
    rows = annotate_queue_analog_series_delta_prior(
        rows,
        report_path=queue_analog_series_delta_path,
        policy_path=queue_analog_series_policy_path,
        target_context=runtime_target_context,
    )
    for row in rows:
        score_without_strategy = final_score(
            row["direction_score"],
            row["property_score"],
            row["similarity_score"],
            row["synthetic_score"],
            row["risk_score"],
            transform_prior_score=row.get("transform_prior_score"),
            transform_activity_score=row.get("transform_activity_score"),
            mmp_precedent_score=row.get("mmp_precedent_score"),
            evidence_consistency_score=row.get("evidence_consistency_score"),
            evidence_confidence_calibration_score=row.get("evidence_confidence_calibration_score"),
            sar_neighborhood_score=row.get("sar_neighborhood_score"),
            ring_frequency_score=row.get("ring_frequency_score"),
            scaffold_context_score=row.get("scaffold_context_score"),
            scaffold_local_evidence_score=row.get("scaffold_local_evidence_score"),
            strategy_learning_prior_score=None,
            public_strategy_signal_score=row.get("public_strategy_signal_score"),
            vendor_score=row.get("vendor_score"),
            route_score=row.get("route_score"),
            weights=weights,
        )
        score_before_adjustment = final_score(
            row["direction_score"],
            row["property_score"],
            row["similarity_score"],
            row["synthetic_score"],
            row["risk_score"],
            transform_prior_score=row.get("transform_prior_score"),
            transform_activity_score=row.get("transform_activity_score"),
            mmp_precedent_score=row.get("mmp_precedent_score"),
            evidence_consistency_score=row.get("evidence_consistency_score"),
            evidence_confidence_calibration_score=row.get("evidence_confidence_calibration_score"),
            sar_neighborhood_score=row.get("sar_neighborhood_score"),
            ring_frequency_score=row.get("ring_frequency_score"),
            scaffold_context_score=row.get("scaffold_context_score"),
            scaffold_local_evidence_score=row.get("scaffold_local_evidence_score"),
            strategy_learning_prior_score=row.get("strategy_learning_prior_score"),
            public_strategy_signal_score=row.get("public_strategy_signal_score"),
            vendor_score=row.get("vendor_score"),
            route_score=row.get("route_score"),
            weights=weights,
        )
        strategy_adjustment = float(row.get("strategy_learning_score_adjustment") or 0.0)
        score_after_strategy = max(0.0, min(100.0, score_before_adjustment + strategy_adjustment))
        queue_series_adjustment = float(row.get("queue_analog_series_delta_score_adjustment") or 0.0)
        row.update(
            multi_objective_score_for_candidate(
                row,
                target_context=runtime_target_context,
                profiles_path=target_context_profiles_path,
                base_score=score_after_strategy,
            )
        )
        multi_objective_adjustment = float(row.get("multi_objective_score_adjustment") or 0.0)
        row.update(
            endpoint_family_residual_adjustment_for_candidate(
                row,
                profile=profile,
                target_context=runtime_target_context,
            )
        )
        residual_adjustment = float(row.get("endpoint_family_residual_score_adjustment") or 0.0)
        ring_outcome_adjustment = float(row.get("ring_outcome_learning_score_adjustment") or 0.0)
        final = max(
            0.0,
            min(
                100.0,
                score_after_strategy
                + queue_series_adjustment
                + multi_objective_adjustment
                + residual_adjustment
                + ring_outcome_adjustment,
            ),
        )
        row["score_without_strategy_prior"] = score_without_strategy
        row["score_before_strategy_adjustment"] = score_before_adjustment
        row["score_after_strategy_adjustment"] = round(score_after_strategy, 2)
        row["score"] = round(final, 2)
        row["strategy_learning_score_delta"] = round(score_after_strategy - score_without_strategy, 4)
        row["queue_analog_series_delta_score_delta"] = round(queue_series_adjustment, 4)
        row["score_after_queue_analog_series_delta"] = round(score_after_strategy + queue_series_adjustment, 2)
        row["multi_objective_score_delta"] = round(multi_objective_adjustment, 4)
        row["endpoint_family_residual_score_delta"] = round(residual_adjustment, 4)
        row["score_after_endpoint_family_residual_adjustment"] = round(
            score_after_strategy + queue_series_adjustment + multi_objective_adjustment + residual_adjustment,
            2,
        )
        row["ring_outcome_learning_score_delta"] = round(ring_outcome_adjustment, 4)
        row["score_after_ring_outcome_learning"] = round(
            score_after_strategy
            + queue_series_adjustment
            + multi_objective_adjustment
            + residual_adjustment
            + ring_outcome_adjustment,
            2,
        )
    learning_report = build_assay_learning_report(db_path=db_path, project_name=project_name)
    endpoint_group = (profile.get("target_context") or {}).get("endpoint_group") or direction
    rows = annotate_endpoint_gates(rows, learning_report, endpoint_group=endpoint_group)
    rows.sort(key=lambda row: row["score"], reverse=True)
    rows = cluster_candidates(rows)
    rows = annotate_diverse_top_n(rows, top_n=diverse_top_n, per_cluster_limit=per_cluster_limit)
    for idx, row in enumerate(rows, start=1):
        row["rank"] = idx
    rows = annotate_novelty_diversity_batch(
        rows,
        max_rows=novelty_batch_size,
        per_bucket_limit=novelty_batch_per_bucket_limit,
    )
    analog_series_summary = build_analog_series_report(rows=rows, db_path=db_path, project_name=project_name)
    rows = annotate_candidate_explanations(rows)

    if output_dir is not None:
        output_dir = Path(output_dir)
        export_csv(rows, output_dir / "candidates.csv")
        export_sdf(rows, output_dir / "candidates.sdf")
        write_route_batch_exports(rows, output_dir / "route_batches")

    return {
        "parent_smiles": Chem.MolToSmiles(parent, canonical=True),
        "parent_properties": parent_props,
        "sites": [site.to_dict() for site in sites],
        "selected_site": site.to_dict(),
        "selected_site_guidance": selected_site_guidance,
        "substituent_count": len(substituents),
        "functional_replacement_count": len(functional_candidates),
        "network_replacement_count": len(network_candidates),
        "scaffold_replacement_count": len(scaffold_candidates),
        "ring_library_recommendation_count": len(ring_library_candidates),
        "ring_rgroup_joint_recommendation_count": len(ring_rgroup_joint_candidates),
        "replacement_network_summary": network_summary,
        "ring_library_summary": {
            "returned_count": ring_library_report.get("returned_count", 0),
            "total_matching_count": ring_library_report.get("total_matching_count", 0),
            "cache": ring_library_report.get("cache"),
            "summary": ring_library_report.get("summary", {}),
            "diversity_selection": ring_library_report.get("diversity_selection", {}),
        },
        "candidate_count": len(rows),
        "enumeration_errors": enumeration_errors,
        "score_weights": weights,
        "scoring_profile": profile
        or {
            "profile_id": "default",
            "name": "Default",
            "path": None,
        },
        "analysis": {
            "property_summary": property_summary(rows),
            "cluster_summary": group_summary(rows, "cluster_id"),
            "enumeration_summary": group_summary(rows, "enumeration_type"),
            "site_summary": group_summary(rows, "site_type"),
            "route_batch_summary": route_batch_summary(rows),
            "diverse_top_n": [
                row
                for row in sorted(
                    (item for item in rows if item.get("diverse_pick")),
                    key=lambda item: item.get("diverse_rank") or 9999,
                )
            ],
            "novelty_diversity_batch": [
                row
                for row in sorted(
                    (item for item in rows if item.get("novelty_batch_pick")),
                    key=lambda item: item.get("novelty_batch_rank") or 9999,
                )
            ],
            "novelty_diversity_batch_summary": novelty_batch_summary(rows),
            "analog_series_summary": analog_series_summary,
        },
        "assay_learning_gate": {
            "project_name": project_name,
            "endpoint_group": endpoint_group,
            "endpoint_count": learning_report.get("endpoint_count"),
            "event_count": learning_report.get("event_count"),
        },
        "candidates": rows,
        "status_message": "ok",
    }
