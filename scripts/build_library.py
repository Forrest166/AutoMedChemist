from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.database import (  # noqa: E402
    initialize_database,
    insert_build_manifest,
    insert_candidate_promotions,
    insert_candidate_substituents,
    insert_mmp_transform_evidence,
    insert_chembl_activity_evidence,
    insert_transform_activity_summaries,
    insert_literature_substituents,
    insert_rgroup_replacements,
    insert_ring_replacements,
    insert_ring_systems,
    insert_scaffold_replacements,
    insert_transform_mmp_mappings,
    insert_vendor_overlays,
    insert_quality_issues,
    insert_substituent_records,
    insert_transform_quality_issues,
    reset_library_tables,
)
from localmedchem.governance import govern_records  # noqa: E402
from localmedchem.library import enrich_substituent_record, load_records, save_csv, save_yaml, validate_library  # noqa: E402
from localmedchem.manifest import build_manifest, save_manifest  # noqa: E402
from localmedchem.release import compare_libraries, write_release_markdown, write_release_report  # noqa: E402
from localmedchem.review import review_queue_row  # noqa: E402
from localmedchem.staging import load_staging_candidates  # noqa: E402
from localmedchem.mmp import load_mmp_evidence, validate_mmp_evidence  # noqa: E402
from localmedchem.activity import load_activity_evidence, save_activity_report, save_transform_activity_report, transform_activity_summaries  # noqa: E402
from localmedchem.ring_library import load_yaml_collection, validate_ring_substituent_collections  # noqa: E402
from localmedchem.scaffold_replacements import load_scaffold_replacements, validate_scaffold_replacements  # noqa: E402
from localmedchem.synthesis import load_synthesis_routes, validate_synthesis_routes  # noqa: E402
from localmedchem.transform_mmp_mapping import load_transform_mmp_mappings, map_mmp_to_transform_rules, validate_transform_mmp_mappings  # noqa: E402
from localmedchem.transform_governance import load_transform_rules, validate_transform_rules  # noqa: E402
from localmedchem.transform_priors import load_transform_priors, validate_transform_priors  # noqa: E402
from localmedchem.transform_evidence import build_transform_evidence_report, write_transform_evidence_markdown, write_transform_evidence_report  # noqa: E402
from localmedchem.vendor import apply_vendor_overlay, load_vendor_overlay  # noqa: E402


DEFAULT_SEEDS = [
    ROOT / "data" / "seeds" / "core_substituent_seed.yaml",
    ROOT / "data" / "seeds" / "pubchem_expansion_seed.yaml",
]

DEFAULT_STAGING_CANDIDATES = [
    ROOT / "data" / "sources" / "substituent_expansion_candidates.yaml",
    ROOT / "data" / "sources" / "patent_mined_candidates.yaml",
    ROOT / "data" / "sources" / "chembl_fragment_candidates.yaml",
    ROOT / "data" / "sources" / "surechembl_patent_candidates.yaml",
]


def parse_seed_paths(value: str) -> list[Path]:
    return [Path(part.strip()) for part in value.replace(";", ",").split(",") if part.strip()]


def load_metadata(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_review_queue(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [review_queue_row(record) for record in records]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def save_changelog(records: list[dict], path: Path) -> None:
    entries = []
    for record in records:
        for entry in record.get("version_history", []):
            entries.append(
                {
                    "substituent_id": record.get("substituent_id"),
                    "name": record.get("name"),
                    **entry,
                }
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, sort_keys=True), encoding="utf-8")


def save_quality_issues(issues: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["substituent_id", "name", "severity", "category", "field", "value", "message"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(issues)


def save_transform_quality_issues(issues: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["rule_id", "name", "severity", "category", "field", "value", "message"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(issues)


def save_transform_prior_quality_issues(issues: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["rule_id", "replacement_label", "severity", "category", "field", "value", "message"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(issues)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build releaseable substituent library artifacts.")
    parser.add_argument("--seed", default=";".join(str(path) for path in DEFAULT_SEEDS))
    parser.add_argument("--pubchem", default=str(ROOT / "data" / "raw" / "pubchem_substituent_metadata.json"))
    parser.add_argument("--yaml-out", default=str(ROOT / "data" / "substituents" / "core_substituent_library.yaml"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "substituents" / "medchem_common_substituents.csv"))
    parser.add_argument("--db-out", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--report-out", default=str(ROOT / "data" / "substituents" / "library_build_report.json"))
    parser.add_argument("--review-queue-out", default=str(ROOT / "data" / "substituents" / "review_queue.csv"))
    parser.add_argument("--changelog-out", default=str(ROOT / "data" / "substituents" / "library_changelog.json"))
    parser.add_argument("--quality-report-out", default=str(ROOT / "data" / "substituents" / "data_quality_report.json"))
    parser.add_argument("--quality-issues-out", default=str(ROOT / "data" / "substituents" / "data_quality_issues.csv"))
    parser.add_argument("--staging-candidates", default=";".join(str(path) for path in DEFAULT_STAGING_CANDIDATES))
    parser.add_argument("--functional-rules", default=str(ROOT / "data" / "rules" / "functional_group_replacements.yaml"))
    parser.add_argument("--transform-priors", default=str(ROOT / "data" / "rules" / "transform_priors.yaml"))
    parser.add_argument("--transform-mmp-mapping", default=str(ROOT / "data" / "rules" / "transform_mmp_mapping.yaml"))
    parser.add_argument("--mmp-evidence", default=str(ROOT / "data" / "mmp" / "chembl_mmp_transform_evidence.yaml"))
    parser.add_argument("--chembl-activity", default=str(ROOT / "data" / "activity" / "chembl_activity_evidence.yaml"))
    parser.add_argument("--ring-library", default=str(ROOT / "data" / "rings" / "ring_system_library.yaml"))
    parser.add_argument("--literature-substituents", default=str(ROOT / "data" / "substituents" / "literature_substituent_library.yaml"))
    parser.add_argument("--ring-replacements", default=str(ROOT / "data" / "replacements" / "ring_replacements.yaml"))
    parser.add_argument("--rgroup-replacements", default=str(ROOT / "data" / "replacements" / "rgroup_replacements.yaml"))
    parser.add_argument("--direction-rules", default=str(ROOT / "data" / "rules" / "direction_rules.yaml"))
    parser.add_argument("--site-rules", default=str(ROOT / "data" / "rules" / "site_smarts.yaml"))
    parser.add_argument("--property-profiles", default=str(ROOT / "data" / "rules" / "property_profiles.yaml"))
    parser.add_argument("--vendor-overlay", default=str(ROOT / "data" / "vendor" / "reagent_availability_overlay.csv"))
    parser.add_argument("--synthesis-routes", default=str(ROOT / "data" / "vendor" / "synthesis_route_templates.yaml"))
    parser.add_argument("--scaffold-replacements", default=str(ROOT / "data" / "rules" / "scaffold_replacements.yaml"))
    parser.add_argument("--transform-quality-report-out", default=str(ROOT / "data" / "substituents" / "transform_rule_quality_report.json"))
    parser.add_argument("--transform-quality-issues-out", default=str(ROOT / "data" / "substituents" / "transform_rule_quality_issues.csv"))
    parser.add_argument("--transform-prior-quality-report-out", default=str(ROOT / "data" / "substituents" / "transform_prior_quality_report.json"))
    parser.add_argument("--transform-prior-quality-issues-out", default=str(ROOT / "data" / "substituents" / "transform_prior_quality_issues.csv"))
    parser.add_argument("--mmp-evidence-quality-report-out", default=str(ROOT / "data" / "substituents" / "mmp_evidence_quality_report.json"))
    parser.add_argument("--synthesis-route-quality-report-out", default=str(ROOT / "data" / "substituents" / "synthesis_route_quality_report.json"))
    parser.add_argument("--chembl-activity-quality-report-out", default=str(ROOT / "data" / "substituents" / "chembl_activity_quality_report.json"))
    parser.add_argument("--transform-activity-report-out", default=str(ROOT / "data" / "substituents" / "transform_activity_report.json"))
    parser.add_argument("--ring-substituent-quality-report-out", default=str(ROOT / "data" / "substituents" / "ring_substituent_quality_report.json"))
    parser.add_argument("--scaffold-replacement-quality-report-out", default=str(ROOT / "data" / "substituents" / "scaffold_replacement_quality_report.json"))
    parser.add_argument("--transform-mmp-mapping-report-out", default=str(ROOT / "data" / "substituents" / "transform_mmp_mapping_report.json"))
    parser.add_argument("--transform-evidence-report-out", default=str(ROOT / "data" / "substituents" / "transform_evidence_report.json"))
    parser.add_argument("--transform-evidence-report-md-out", default=str(ROOT / "data" / "substituents" / "transform_evidence_report.md"))
    parser.add_argument("--manifest-out", default=str(ROOT / "data" / "substituents" / "build_manifest.json"))
    parser.add_argument("--release-report-out", default=str(ROOT / "data" / "substituents" / "library_release_report.json"))
    parser.add_argument("--release-report-md-out", default=str(ROOT / "data" / "substituents" / "library_release_report.md"))
    parser.add_argument(
        "--preserve-db-ring-tables",
        action="store_true",
        help="Keep existing SQLite ring_system rows during rebuilds, useful after DB-only full Ertl ring imports.",
    )
    args = parser.parse_args()

    previous_records = load_records([Path(args.yaml_out)]) if Path(args.yaml_out).exists() else []
    seed_paths = parse_seed_paths(args.seed)
    raw_records = load_records(seed_paths)
    valid_records, validation_errors = validate_library(raw_records)
    pre_enrichment_quality = govern_records(valid_records, check_metadata=False)
    blocked_ids = set(pre_enrichment_quality["blocked_substituent_ids"])
    governed_records = [record for record in valid_records if record.get("substituent_id") not in blocked_ids]
    pubchem = load_metadata(Path(args.pubchem))

    enriched = []
    enrichment_errors = []
    for record in governed_records:
        try:
            metadata = pubchem.get(record["substituent_id"])
            enriched.append(enrich_substituent_record(record, metadata))
        except Exception as exc:
            enrichment_errors.append(
                {
                    "substituent_id": record.get("substituent_id"),
                    "name": record.get("name"),
                    "errors": [str(exc)],
                }
            )

    vendor_rows = load_vendor_overlay(args.vendor_overlay)
    enriched = apply_vendor_overlay(enriched, vendor_rows)
    post_enrichment_quality = govern_records(enriched)
    quality_report = {
        "pre_enrichment": {key: value for key, value in pre_enrichment_quality.items() if key != "issues"},
        "post_enrichment": {key: value for key, value in post_enrichment_quality.items() if key != "issues"},
        "issues": pre_enrichment_quality["issues"] + post_enrichment_quality["issues"],
    }

    save_yaml(enriched, args.yaml_out)
    save_csv(enriched, args.csv_out)
    save_review_queue(enriched, Path(args.review_queue_out))
    save_changelog(enriched, Path(args.changelog_out))
    save_quality_issues(quality_report["issues"], Path(args.quality_issues_out))
    Path(args.quality_report_out).write_text(json.dumps(quality_report, indent=2, sort_keys=True), encoding="utf-8")
    transform_quality = validate_transform_rules(load_transform_rules(args.functional_rules))
    Path(args.transform_quality_report_out).write_text(json.dumps(transform_quality, indent=2, sort_keys=True), encoding="utf-8")
    save_transform_quality_issues(transform_quality["issues"], Path(args.transform_quality_issues_out))
    known_rule_ids = {str(rule.get("rule_id")) for rule in load_transform_rules(args.functional_rules)}
    transform_prior_quality = validate_transform_priors(load_transform_priors(args.transform_priors), known_rule_ids=known_rule_ids)
    Path(args.transform_prior_quality_report_out).write_text(json.dumps(transform_prior_quality, indent=2, sort_keys=True), encoding="utf-8")
    save_transform_prior_quality_issues(transform_prior_quality["issues"], Path(args.transform_prior_quality_issues_out))
    mmp_evidence = load_mmp_evidence(args.mmp_evidence)
    mmp_quality = validate_mmp_evidence(mmp_evidence)
    Path(args.mmp_evidence_quality_report_out).write_text(json.dumps(mmp_quality, indent=2, sort_keys=True), encoding="utf-8")
    activity_evidence = load_activity_evidence(args.chembl_activity)
    activity_quality = save_activity_report(activity_evidence, args.chembl_activity_quality_report_out)
    transform_mmp_mappings = map_mmp_to_transform_rules(
        mmp_evidence,
        load_transform_mmp_mappings(args.transform_mmp_mapping),
    )
    transform_mmp_mapping_quality = validate_transform_mmp_mappings(transform_mmp_mappings)
    transform_mmp_mapping_report = {**transform_mmp_mapping_quality, "mappings": transform_mmp_mappings}
    Path(args.transform_mmp_mapping_report_out).write_text(json.dumps(transform_mmp_mapping_report, indent=2, sort_keys=True), encoding="utf-8")
    transform_activity_rows = transform_activity_summaries(
        mmp_rows=mmp_evidence,
        mapping_rows=transform_mmp_mappings,
        activity_rows=activity_evidence,
    )
    transform_activity_report = save_transform_activity_report(transform_activity_rows, args.transform_activity_report_out)
    ring_records = load_yaml_collection(args.ring_library, "ring_systems")
    literature_substituents = load_yaml_collection(args.literature_substituents, "literature_substituents")
    ring_replacements = load_yaml_collection(args.ring_replacements, "ring_replacements")
    rgroup_replacements = load_yaml_collection(args.rgroup_replacements, "rgroup_replacements")
    ring_substituent_quality = validate_ring_substituent_collections(
        ring_records,
        literature_substituents,
        ring_replacements,
        rgroup_replacements,
    )
    Path(args.ring_substituent_quality_report_out).write_text(json.dumps(ring_substituent_quality, indent=2, sort_keys=True), encoding="utf-8")
    synthesis_routes = load_synthesis_routes(args.synthesis_routes)
    synthesis_route_quality = validate_synthesis_routes(synthesis_routes)
    Path(args.synthesis_route_quality_report_out).write_text(json.dumps(synthesis_route_quality, indent=2, sort_keys=True), encoding="utf-8")
    scaffold_replacements = load_scaffold_replacements(args.scaffold_replacements)
    scaffold_replacement_quality = validate_scaffold_replacements(scaffold_replacements)
    Path(args.scaffold_replacement_quality_report_out).write_text(json.dumps(scaffold_replacement_quality, indent=2, sort_keys=True), encoding="utf-8")
    transform_evidence_report = build_transform_evidence_report(
        priors_path=args.transform_priors,
        mmp_evidence_path=args.mmp_evidence,
        db_path=args.db_out,
    )
    write_transform_evidence_report(transform_evidence_report, args.transform_evidence_report_out)
    write_transform_evidence_markdown(transform_evidence_report, args.transform_evidence_report_md_out)
    release_report = compare_libraries(previous_records, enriched)
    write_release_report(release_report, args.release_report_out)
    write_release_markdown(release_report, args.release_report_md_out)
    staging_candidates = load_staging_candidates(parse_seed_paths(args.staging_candidates))

    manifest = build_manifest(
        seed_paths=seed_paths,
        rule_paths=[
            args.functional_rules,
            args.transform_priors,
            args.transform_mmp_mapping,
            args.direction_rules,
            args.site_rules,
            args.property_profiles,
            args.synthesis_routes,
            args.scaffold_replacements,
            *(ROOT / "data" / "profiles").glob("*.yaml"),
        ],
        raw_paths=[
            args.pubchem,
            args.vendor_overlay,
            args.mmp_evidence,
            args.chembl_activity,
            args.ring_library,
            args.literature_substituents,
            args.ring_replacements,
            args.rgroup_replacements,
            ROOT / "data" / "substituents" / "api_health_report.json",
            ROOT / "data" / "raw" / "chembl_molecule_records.json",
            ROOT / "data" / "raw" / "surechembl_api_probe.json",
            *parse_seed_paths(args.staging_candidates),
        ],
        output_paths=[
            args.yaml_out,
            args.csv_out,
            args.db_out,
            args.review_queue_out,
            args.changelog_out,
            args.quality_report_out,
            args.quality_issues_out,
            args.transform_quality_report_out,
            args.transform_quality_issues_out,
            args.transform_prior_quality_report_out,
            args.transform_prior_quality_issues_out,
            args.mmp_evidence_quality_report_out,
            args.synthesis_route_quality_report_out,
            args.chembl_activity_quality_report_out,
            args.transform_activity_report_out,
            args.ring_substituent_quality_report_out,
            args.scaffold_replacement_quality_report_out,
            args.transform_mmp_mapping_report_out,
            args.transform_evidence_report_out,
            args.transform_evidence_report_md_out,
            args.release_report_out,
            args.release_report_md_out,
        ],
        extra={
            "seed_count": len(raw_records),
            "enriched_count": len(enriched),
            "quality_error_count": quality_report["post_enrichment"]["error_count"],
            "quality_warning_count": quality_report["post_enrichment"]["warning_count"],
            "transform_error_count": transform_quality["error_count"],
            "transform_warning_count": transform_quality["warning_count"],
            "transform_prior_error_count": transform_prior_quality["error_count"],
            "transform_prior_warning_count": transform_prior_quality["warning_count"],
            "mmp_evidence_count": len(mmp_evidence),
            "chembl_activity_count": len(activity_evidence),
            "transform_mmp_mapping_count": len(transform_mmp_mappings),
            "transform_activity_summary_count": len(transform_activity_rows),
            "transform_activity_summary_with_activity_count": transform_activity_report["summaries_with_activity"],
            "transform_activity_target_family_summary_count": transform_activity_report["summaries_with_target_family_activity"],
            "transform_activity_judgment_counts": transform_activity_report["rule_activity_judgment_counts"],
            "ring_system_count": len(ring_records),
            "literature_substituent_count": len(literature_substituents),
            "ring_replacement_count": len(ring_replacements),
            "rgroup_replacement_count": len(rgroup_replacements),
            "transform_evidence_count": transform_evidence_report["transform_count"],
            "project_transform_evidence_count": transform_evidence_report["project_evidence_count"],
            "mmp_error_count": mmp_quality["error_count"],
            "chembl_activity_error_count": activity_quality["error_count"],
            "ring_substituent_error_count": ring_substituent_quality["error_count"],
            "synthesis_route_count": len(synthesis_routes),
            "synthesis_route_error_count": synthesis_route_quality["error_count"],
            "scaffold_replacement_count": len(scaffold_replacements),
            "scaffold_replacement_error_count": scaffold_replacement_quality["error_count"],
            "vendor_overlay_row_count": len(vendor_rows),
            "vendor_overlay_match_count": sum(1 for record in enriched if record.get("vendor")),
        },
    )
    save_manifest(manifest, args.manifest_out)

    conn = initialize_database(args.db_out)
    try:
        preserve_tables = {"ring_system"} if args.preserve_db_ring_tables else set()
        reset_library_tables(conn, preserve_tables=preserve_tables)
        insert_substituent_records(conn, enriched)
        insert_quality_issues(conn, quality_report["issues"])
        insert_candidate_substituents(conn, staging_candidates)
        insert_candidate_promotions(conn, enriched)
        insert_vendor_overlays(conn, enriched)
        insert_mmp_transform_evidence(conn, mmp_evidence)
        insert_transform_mmp_mappings(conn, transform_mmp_mappings)
        insert_chembl_activity_evidence(conn, activity_evidence)
        insert_transform_activity_summaries(conn, transform_activity_rows)
        insert_ring_systems(conn, ring_records)
        insert_literature_substituents(conn, literature_substituents)
        insert_ring_replacements(conn, ring_replacements)
        insert_rgroup_replacements(conn, rgroup_replacements)
        insert_scaffold_replacements(conn, scaffold_replacements)
        insert_transform_quality_issues(conn, transform_quality["issues"])
        insert_build_manifest(conn, manifest)
    finally:
        conn.close()

    report = {
        "seed_files": [str(path.resolve()) for path in seed_paths],
        "seed_count": len(raw_records),
        "valid_count": len(valid_records),
        "governed_count": len(governed_records),
        "enriched_count": len(enriched),
        "validation_error_count": len(validation_errors),
        "enrichment_error_count": len(enrichment_errors),
        "quality_error_count": quality_report["post_enrichment"]["error_count"],
        "quality_warning_count": quality_report["post_enrichment"]["warning_count"],
        "staging_candidate_count": len(staging_candidates),
        "transform_error_count": transform_quality["error_count"],
        "transform_warning_count": transform_quality["warning_count"],
        "transform_prior_error_count": transform_prior_quality["error_count"],
        "transform_prior_warning_count": transform_prior_quality["warning_count"],
        "mmp_evidence_count": len(mmp_evidence),
        "chembl_activity_count": len(activity_evidence),
        "transform_mmp_mapping_count": len(transform_mmp_mappings),
        "transform_activity_summary_count": len(transform_activity_rows),
        "transform_activity_summary_with_activity_count": transform_activity_report["summaries_with_activity"],
        "transform_activity_target_family_summary_count": transform_activity_report["summaries_with_target_family_activity"],
        "transform_activity_judgment_counts": transform_activity_report["rule_activity_judgment_counts"],
        "ring_system_count": len(ring_records),
        "literature_substituent_count": len(literature_substituents),
        "ring_replacement_count": len(ring_replacements),
        "rgroup_replacement_count": len(rgroup_replacements),
        "transform_evidence_count": transform_evidence_report["transform_count"],
        "project_transform_evidence_count": transform_evidence_report["project_evidence_count"],
        "mmp_error_count": mmp_quality["error_count"],
        "chembl_activity_error_count": activity_quality["error_count"],
        "ring_substituent_error_count": ring_substituent_quality["error_count"],
        "synthesis_route_count": len(synthesis_routes),
        "synthesis_route_error_count": synthesis_route_quality["error_count"],
        "scaffold_replacement_count": len(scaffold_replacements),
        "scaffold_replacement_error_count": scaffold_replacement_quality["error_count"],
        "vendor_overlay_row_count": len(vendor_rows),
        "vendor_overlay_match_count": sum(1 for record in enriched if record.get("vendor")),
        "validation_errors": validation_errors,
        "enrichment_errors": enrichment_errors,
        "outputs": {
            "yaml": str(Path(args.yaml_out).resolve()),
            "csv": str(Path(args.csv_out).resolve()),
            "sqlite": str(Path(args.db_out).resolve()),
            "review_queue": str(Path(args.review_queue_out).resolve()),
            "changelog": str(Path(args.changelog_out).resolve()),
            "quality_report": str(Path(args.quality_report_out).resolve()),
            "quality_issues": str(Path(args.quality_issues_out).resolve()),
            "transform_quality_report": str(Path(args.transform_quality_report_out).resolve()),
            "transform_quality_issues": str(Path(args.transform_quality_issues_out).resolve()),
            "transform_prior_quality_report": str(Path(args.transform_prior_quality_report_out).resolve()),
            "transform_prior_quality_issues": str(Path(args.transform_prior_quality_issues_out).resolve()),
            "mmp_evidence_quality_report": str(Path(args.mmp_evidence_quality_report_out).resolve()),
            "synthesis_route_quality_report": str(Path(args.synthesis_route_quality_report_out).resolve()),
            "chembl_activity_quality_report": str(Path(args.chembl_activity_quality_report_out).resolve()),
            "transform_activity_report": str(Path(args.transform_activity_report_out).resolve()),
            "ring_substituent_quality_report": str(Path(args.ring_substituent_quality_report_out).resolve()),
            "scaffold_replacement_quality_report": str(Path(args.scaffold_replacement_quality_report_out).resolve()),
            "transform_mmp_mapping_report": str(Path(args.transform_mmp_mapping_report_out).resolve()),
            "transform_evidence_report": str(Path(args.transform_evidence_report_out).resolve()),
            "transform_evidence_report_md": str(Path(args.transform_evidence_report_md_out).resolve()),
            "manifest": str(Path(args.manifest_out).resolve()),
            "release_report": str(Path(args.release_report_out).resolve()),
            "release_report_md": str(Path(args.release_report_md_out).resolve()),
        },
        "preserved_db_tables": sorted(preserve_tables),
    }
    Path(args.report_out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
