from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml


DEFAULT_FEED_DIR = Path("data/replacements/feeds")
DEFAULT_FEED_MANIFEST_PATH = Path("data/replacements/feed_source_manifest.yaml")
DEFAULT_FEED_METADATA_REPORT_PATH = Path("data/substituents/rgroup_feed_metadata_report.json")
DEFAULT_FEED_REVIEW_COVERAGE_PATH = Path("data/substituents/rgroup_feed_review_coverage.json")
DEFAULT_PAIR_DECISION_SUMMARY_PATH = Path("data/substituents/rgroup_normalized_pair_contradiction_decisions.json")
DEFAULT_PAIR_OWNER_PACKET_PATH = Path("data/substituents/rgroup_pair_conflict_owner_review_packet.json")
DEFAULT_FEED_ONBOARDING_GATE_PATH = Path("data/substituents/rgroup_feed_onboarding_gate.json")
DEFAULT_FEED_ONBOARDING_GATE_CSV_PATH = Path("data/substituents/rgroup_feed_onboarding_gate.csv")
DEFAULT_FEED_ONBOARDING_TEMPLATE_PATH = Path("data/replacements/feed_onboarding_template.csv")
DEFAULT_FEED_DROP_STAGING_DIR = Path("data/replacements/feed_drops/next_rgroup_feed_drop")
DEFAULT_FEED_DROP_STAGING_REPORT_PATH = Path("data/substituents/rgroup_next_feed_drop_staging.json")
DEFAULT_FEED_DROP_STAGING_CSV_PATH = Path("data/substituents/rgroup_next_feed_drop_staging.csv")
DEFAULT_FEED_DROP_STAGING_GATE_PATH = Path("data/substituents/rgroup_next_feed_drop_staging_gate.json")
DEFAULT_FEED_DROP_STAGING_GATE_CSV_PATH = Path("data/substituents/rgroup_next_feed_drop_staging_gate.csv")
DEFAULT_FEED_DROP_PROMOTION_REPORT_PATH = Path("data/substituents/rgroup_next_feed_drop_promotion.json")
DEFAULT_FEED_DROP_PROMOTION_CSV_PATH = Path("data/substituents/rgroup_next_feed_drop_promotion.csv")
DEFAULT_FEED_DROP_PROMOTION_DIFF_PATH = Path("data/substituents/rgroup_next_feed_drop_promotion_diff.json")
DEFAULT_FEED_DROP_PROMOTION_DIFF_CSV_PATH = Path("data/substituents/rgroup_next_feed_drop_promotion_diff.csv")

REQUIRED_FEED_COLUMNS = [
    "replacement_id",
    "source_smiles",
    "target_smiles",
    "edge_weight",
    "source_name",
]
RECOMMENDED_GOVERNANCE_COLUMNS = [
    "source_dataset",
    "source_owner",
    "source_license",
    "provenance_level",
    "provenance_review_status",
    "provenance_note",
    "source_reference",
    "source_confidence_tier",
    "source_confidence_score",
    "source_confidence_basis",
    "row_sha256",
]
OPTIONAL_CONTEXT_COLUMNS = [
    "replacement_class",
    "endpoint_group",
    "direction",
    "source_record_id",
    "notes",
]
ONBOARDING_TEMPLATE_COLUMNS = REQUIRED_FEED_COLUMNS + OPTIONAL_CONTEXT_COLUMNS + RECOMMENDED_GOVERNANCE_COLUMNS


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_manifest(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def _csv_info(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    missing_required = [field for field in REQUIRED_FEED_COLUMNS if field not in fieldnames]
    missing_governance = [field for field in RECOMMENDED_GOVERNANCE_COLUMNS if field not in fieldnames]
    missing_sha_count = sum(1 for row in rows if not str(row.get("row_sha256") or "").strip())
    return {
        "path": str(path),
        "feed_name": path.name,
        "row_count": len(rows),
        "column_count": len(fieldnames),
        "missing_required_columns": missing_required,
        "missing_recommended_governance_columns": missing_governance,
        "missing_row_sha256_count": missing_sha_count,
    }


def _manifest_file_map(manifest: dict) -> dict[str, str]:
    files = {}
    for name, source in (manifest.get("files") or {}).items():
        files[str(name)] = str(source)
    for name, entry in (manifest.get("file_manifests") or {}).items():
        if isinstance(entry, dict) and entry.get("source_dataset"):
            files[str(name)] = str(entry["source_dataset"])
    return files


def build_rgroup_feed_onboarding_gate(
    *,
    feed_dir: str | Path = DEFAULT_FEED_DIR,
    manifest_path: str | Path = DEFAULT_FEED_MANIFEST_PATH,
    metadata_report_path: str | Path = DEFAULT_FEED_METADATA_REPORT_PATH,
    review_coverage_path: str | Path = DEFAULT_FEED_REVIEW_COVERAGE_PATH,
    pair_decision_summary_path: str | Path = DEFAULT_PAIR_DECISION_SUMMARY_PATH,
    pair_owner_packet_path: str | Path = DEFAULT_PAIR_OWNER_PACKET_PATH,
    next_drop_label: str = "next_rgroup_feed_drop",
) -> dict:
    feed_root = Path(feed_dir)
    manifest = _read_manifest(manifest_path)
    manifest_files = _manifest_file_map(manifest)
    feed_files = sorted(path for path in feed_root.glob("*.csv") if path.is_file()) if feed_root.exists() else []
    feed_rows = []
    blockers: list[str] = []
    warnings: list[str] = []

    for path in feed_files:
        info = _csv_info(path)
        source_dataset = manifest_files.get(path.name, "")
        info["manifest_source_dataset"] = source_dataset
        info["manifest_status"] = "covered" if source_dataset else "missing"
        if not source_dataset:
            blockers.append(f"unmanifested_feed:{path.name}")
        if info["missing_required_columns"]:
            blockers.append(f"missing_required_columns:{path.name}")
        if info["missing_recommended_governance_columns"]:
            warnings.append(f"missing_recommended_governance_columns:{path.name}")
        feed_rows.append(info)

    metadata = _read_json(metadata_report_path)
    coverage = _read_json(review_coverage_path)
    pair_decisions = _read_json(pair_decision_summary_path)
    owner_packet = _read_json(pair_owner_packet_path)
    allowlist_issues = int(metadata.get("allowlist_issue_count") or 0)
    freshness_issues = int(metadata.get("freshness_issue_count") or 0)
    no_review_count = int(coverage.get("no_review_count") or 0)
    low_coverage_count = int(coverage.get("low_coverage_count") or 0)
    open_high = int(pair_decisions.get("open_high_priority_count") or 0)
    blocking_unresolved = int(pair_decisions.get("blocking_unresolved_count") or 0)
    deferred_owner_count = int(owner_packet.get("deferred_conflict_count") or 0)
    pending_owner_count = int(owner_packet.get("pending_owner_review_count", deferred_owner_count) or 0)
    recorded_owner_count = int(owner_packet.get("owner_decision_recorded_count") or max(0, deferred_owner_count - pending_owner_count))

    if allowlist_issues:
        blockers.append("feed_allowlist_issues")
    if open_high:
        blockers.append("open_high_priority_pair_conflicts")
    if blocking_unresolved:
        blockers.append("blocking_pair_conflicts_unresolved")
    if freshness_issues:
        warnings.append("feed_freshness_issues")
    if no_review_count or low_coverage_count:
        warnings.append("sample_review_coverage_gaps")
    if pending_owner_count:
        warnings.append("deferred_source_owner_review_backlog")

    if blockers:
        status = "blocked"
    elif not feed_files:
        status = "awaiting_new_feed_drop"
    elif pending_owner_count:
        status = "ready_with_deferred_source_owner_review"
    else:
        status = "ready_for_next_feed_drop"

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "next_drop_label": next_drop_label,
        "feed_dir": str(feed_root),
        "manifest_path": str(manifest_path),
        "feed_file_count": len(feed_files),
        "feed_row_count": sum(int(row.get("row_count") or 0) for row in feed_rows),
        "manifest_covered_file_count": sum(1 for row in feed_rows if row.get("manifest_status") == "covered"),
        "unmanifested_file_count": sum(1 for row in feed_rows if row.get("manifest_status") == "missing"),
        "missing_required_file_count": sum(1 for row in feed_rows if row.get("missing_required_columns")),
        "allowlist_issue_count": allowlist_issues,
        "freshness_issue_count": freshness_issues,
        "review_no_review_count": no_review_count,
        "review_low_coverage_count": low_coverage_count,
        "pair_open_high_priority_count": open_high,
        "pair_blocking_unresolved_count": blocking_unresolved,
        "deferred_source_owner_review_count": deferred_owner_count,
        "pending_source_owner_review_count": pending_owner_count,
        "recorded_source_owner_review_count": recorded_owner_count,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "rows": feed_rows,
        "onboarding_template_path": str(DEFAULT_FEED_ONBOARDING_TEMPLATE_PATH),
        "next_drop_commands": [
            "python scripts/govern_rgroup_feed_metadata.py --write --require-allowlist --require-freshness --sample-strategy stratified",
            "python scripts/build_rgroup_feed_review_coverage.py",
            "python scripts/expand_rgroup_replacement_sources.py --require-source-acceptance --require-source-governance",
            "python scripts/build_rgroup_normalization_report.py --write-db --refresh-raw-db",
            "python scripts/build_rgroup_normalized_pair_contradictions.py --fail-on-blocking",
            "python scripts/build_rgroup_pair_conflict_owner_review_packet.py",
            "python scripts/run_production_ci.py",
        ],
        "recommended_next_actions": [
            "Place the next source-specific CSV files under data/replacements/feeds and add every file to feed_source_manifest.yaml.",
            "Use feed_onboarding_template.csv columns so provenance, confidence tier, and row checksums survive expansion.",
            "Run the onboarding gate before expansion; unresolved source-owner review backlog stays traceable but does not become a positive scoring prior.",
        ],
    }


def write_rgroup_feed_onboarding_gate(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_FEED_ONBOARDING_GATE_PATH,
    csv_path: str | Path | None = DEFAULT_FEED_ONBOARDING_GATE_CSV_PATH,
) -> None:
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if not csv_path:
        return
    rows = [dict(row) for row in report.get("rows") or []]
    fields = [
        "feed_name",
        "path",
        "row_count",
        "column_count",
        "manifest_status",
        "manifest_source_dataset",
        "missing_required_columns",
        "missing_recommended_governance_columns",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: ";".join(row.get(field) or []) if isinstance(row.get(field), list) else row.get(field, "") for field in fields})


def write_rgroup_feed_onboarding_template(
    path: str | Path = DEFAULT_FEED_ONBOARDING_TEMPLATE_PATH,
    *,
    include_example: bool = False,
) -> dict:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    if include_example:
        rows.append(
            {
                "replacement_id": "NEW-FEED-0001",
                "source_smiles": "[*:1]C(=O)O",
                "target_smiles": "[*:1]C(=O)N",
                "edge_weight": "1",
                "source_name": "example source, remove before production",
                "source_dataset": "literature_bioisostere_seed",
                "provenance_review_status": "deferred_review",
            }
        )
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ONBOARDING_TEMPLATE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in ONBOARDING_TEMPLATE_COLUMNS})
    return {
        "status": "written",
        "path": str(out),
        "column_count": len(ONBOARDING_TEMPLATE_COLUMNS),
        "example_row_count": len(rows),
        "columns": ONBOARDING_TEMPLATE_COLUMNS,
    }


def build_rgroup_feed_drop_staging_package(
    *,
    output_dir: str | Path = DEFAULT_FEED_DROP_STAGING_DIR,
    drop_label: str = "next_rgroup_feed_drop",
    source_datasets: list[str] | tuple[str, ...] | None = None,
    include_example: bool = False,
    overwrite: bool = False,
) -> dict:
    """Create source-specific empty feed templates for the next larger drop."""
    source_datasets = list(source_datasets or ["analog_series_seed", "literature_bioisostere_seed", "patent_mined_seed"])
    staging_dir = Path(output_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    manifest_files = {}
    for source_dataset in source_datasets:
        file_name = f"{drop_label}_{source_dataset}.csv"
        path = staging_dir / file_name
        if path.exists() and not overwrite:
            info = _csv_info(path)
            template = {
                "status": "existing_preserved",
                "path": str(path),
                "column_count": info.get("column_count"),
                "example_row_count": 0,
                "row_count": info.get("row_count"),
                "columns": [],
            }
        else:
            template = write_rgroup_feed_onboarding_template(path, include_example=include_example)
        manifest_files[file_name] = source_dataset
        rows.append(
            {
                "drop_label": drop_label,
                "source_dataset": source_dataset,
                "template_path": str(path),
                "template_column_count": template.get("column_count"),
                "example_row_count": template.get("example_row_count"),
                "row_count": template.get("row_count", template.get("example_row_count", 0)),
                "template_status": template.get("status"),
                "manifest_status": "staged_for_manifest",
            }
        )
    manifest = {
        "version": f"{drop_label}-staging-0.1",
        "drop_label": drop_label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": manifest_files,
        "recommended_next_actions": [
            "Fill each source-specific CSV with real reviewed rows.",
            "Copy the files into data/replacements/feeds or add this staging path to the expansion glob.",
            "Copy the files mapping into data/replacements/feed_source_manifest.yaml before running feed governance.",
        ],
    }
    manifest_path = staging_dir / "feed_drop_manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return {
        "created_at": manifest["created_at"],
        "status": "staged",
        "drop_label": drop_label,
        "staging_dir": str(staging_dir),
        "manifest_path": str(manifest_path),
        "source_dataset_count": len(source_datasets),
        "template_file_count": len(rows),
        "rows": rows,
        "recommended_next_actions": manifest["recommended_next_actions"],
    }


def write_rgroup_feed_drop_staging_report(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_FEED_DROP_STAGING_REPORT_PATH,
    csv_path: str | Path | None = DEFAULT_FEED_DROP_STAGING_CSV_PATH,
) -> None:
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if not csv_path:
        return
    rows = [dict(row) for row in report.get("rows") or []]
    fields = [
        "drop_label",
        "source_dataset",
        "template_path",
        "template_column_count",
        "example_row_count",
        "row_count",
        "template_status",
        "manifest_status",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_rgroup_feed_drop_staging_gate(
    *,
    staging_report_path: str | Path = DEFAULT_FEED_DROP_STAGING_REPORT_PATH,
    staging_dir: str | Path = DEFAULT_FEED_DROP_STAGING_DIR,
    require_rows: bool = False,
) -> dict:
    """Validate staged feed-drop CSVs without moving them into production feeds."""
    staging = _read_json(staging_report_path)
    rows = [dict(row) for row in staging.get("rows") or []]
    if not rows:
        root = Path(staging_dir)
        rows = [
            {
                "drop_label": root.name,
                "source_dataset": "",
                "template_path": str(path),
                "manifest_status": "discovered_without_report",
            }
            for path in sorted(root.glob("*.csv"))
        ] if root.exists() else []
    blockers: list[str] = []
    warnings: list[str] = []
    gate_rows: list[dict] = []
    total_rows = 0
    total_missing_sha = 0
    for row in rows:
        path = Path(row.get("template_path") or "")
        expected_source = str(row.get("source_dataset") or "").strip()
        gate_row = dict(row)
        gate_row["exists"] = path.exists()
        if not path.exists():
            blockers.append(f"missing_staged_file:{path.name}")
            gate_rows.append(gate_row)
            continue
        info = _csv_info(path)
        total_rows += int(info.get("row_count") or 0)
        total_missing_sha += int(info.get("missing_row_sha256_count") or 0)
        gate_row.update(info)
        source_values: set[str] = set()
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for csv_row in reader:
                source = str(csv_row.get("source_dataset") or "").strip()
                if source:
                    source_values.add(source)
        gate_row["source_dataset_values"] = ";".join(sorted(source_values))
        gate_row["source_dataset_match"] = not source_values or not expected_source or source_values == {expected_source}
        if info.get("missing_required_columns"):
            blockers.append(f"missing_required_columns:{path.name}")
        if info.get("missing_recommended_governance_columns"):
            warnings.append(f"missing_recommended_governance_columns:{path.name}")
        if int(info.get("row_count") or 0) == 0:
            message = f"empty_staged_file:{path.name}"
            if require_rows:
                blockers.append(message)
            else:
                warnings.append(message)
        if source_values and expected_source and source_values != {expected_source}:
            blockers.append(f"source_dataset_mismatch:{path.name}")
        if int(info.get("row_count") or 0) and int(info.get("missing_row_sha256_count") or 0):
            blockers.append(f"missing_row_sha256:{path.name}")
        gate_rows.append(gate_row)

    if blockers:
        status = "blocked"
    elif total_rows <= 0:
        status = "awaiting_filled_staging_rows"
    else:
        status = "ready_for_promotion"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "staging_report_path": str(staging_report_path),
        "staging_dir": str(staging_dir),
        "staged_file_count": len(gate_rows),
        "filled_file_count": sum(1 for row in gate_rows if int(row.get("row_count") or 0) > 0),
        "staged_row_count": total_rows,
        "missing_row_sha256_count": total_missing_sha,
        "blocker_count": len(set(blockers)),
        "warning_count": len(set(warnings)),
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "rows": gate_rows,
        "promotion_commands": [
            "Copy filled staged CSV files into data/replacements/feeds/.",
            "Copy feed_drop_manifest.yaml file mappings into data/replacements/feed_source_manifest.yaml.",
            "Run python scripts/run_production_ci.py before accepting the feed drop.",
        ],
        "recommended_next_actions": [
            "Keep staged templates empty until real reviewed feed rows are available.",
            "Require source_dataset, source_owner, license, provenance, review status, source confidence, and row_sha256 on every filled row.",
            "Promote only when this gate reaches ready_for_promotion and production CI passes.",
        ],
    }


def write_rgroup_feed_drop_staging_gate(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_FEED_DROP_STAGING_GATE_PATH,
    csv_path: str | Path | None = DEFAULT_FEED_DROP_STAGING_GATE_CSV_PATH,
) -> None:
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if not csv_path:
        return
    rows = [dict(row) for row in report.get("rows") or []]
    fields = [
        "drop_label",
        "source_dataset",
        "template_path",
        "exists",
        "row_count",
        "column_count",
        "missing_required_columns",
        "missing_recommended_governance_columns",
        "missing_row_sha256_count",
        "source_dataset_values",
        "source_dataset_match",
        "manifest_status",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: ";".join(row.get(field) or []) if isinstance(row.get(field), list) else row.get(field, "") for field in fields})


def promote_rgroup_feed_drop_from_staging(
    *,
    staging_gate_path: str | Path = DEFAULT_FEED_DROP_STAGING_GATE_PATH,
    staging_report_path: str | Path = DEFAULT_FEED_DROP_STAGING_REPORT_PATH,
    staging_dir: str | Path = DEFAULT_FEED_DROP_STAGING_DIR,
    feed_dir: str | Path = DEFAULT_FEED_DIR,
    manifest_path: str | Path = DEFAULT_FEED_MANIFEST_PATH,
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict:
    """Promote a validated staged feed drop into the governed feed directory.

    This is intentionally a no-op unless the staging gate is already
    ready_for_promotion. Empty templates stay in staging and are never copied
    into production feeds by this function.
    """
    gate = _read_json(staging_gate_path)
    if not gate:
        gate = build_rgroup_feed_drop_staging_gate(
            staging_report_path=staging_report_path,
            staging_dir=staging_dir,
            require_rows=True,
        )
    blockers = list(gate.get("blockers") or [])
    warnings = list(gate.get("warnings") or [])
    rows = [dict(row) for row in gate.get("rows") or []]
    promoted_rows: list[dict] = []
    feed_root = Path(feed_dir)
    manifest_file = Path(manifest_path)
    manifest = _read_manifest(manifest_file)
    manifest.setdefault("files", {})
    manifest.setdefault("file_manifests", {})

    if gate.get("status") != "ready_for_promotion":
        status = str(gate.get("status") or "blocked")
        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "dry_run": dry_run,
            "staging_gate_path": str(staging_gate_path),
            "feed_dir": str(feed_root),
            "manifest_path": str(manifest_file),
            "promoted_file_count": 0,
            "promoted_row_count": 0,
            "blockers": blockers or [f"staging_gate_not_ready:{status}"],
            "warnings": warnings,
            "rows": [],
            "recommended_next_actions": [
                "Fill staged CSV templates with real reviewed rows before promotion.",
                "Run validate_rgroup_feed_drop_staging.py --require-rows --fail-on-blocked before promotion.",
            ],
        }

    feed_root.mkdir(parents=True, exist_ok=True)
    for row in rows:
        if int(row.get("row_count") or 0) <= 0:
            continue
        source_path = Path(row.get("template_path") or row.get("path") or "")
        target_path = feed_root / source_path.name
        source_dataset = str(row.get("source_dataset") or "").strip()
        promote_row = {
            "source_path": str(source_path),
            "target_path": str(target_path),
            "source_dataset": source_dataset,
            "row_count": int(row.get("row_count") or 0),
            "status": "pending",
        }
        if not source_path.exists():
            promote_row["status"] = "blocked_missing_source"
            blockers.append(f"missing_staged_file:{source_path.name}")
        elif target_path.exists() and not overwrite:
            promote_row["status"] = "blocked_target_exists"
            blockers.append(f"target_feed_exists:{target_path.name}")
        else:
            promote_row["status"] = "dry_run" if dry_run else "promoted"
            if not dry_run:
                shutil.copy2(source_path, target_path)
                manifest["files"][target_path.name] = source_dataset
                manifest["file_manifests"][target_path.name] = {
                    "source_dataset": source_dataset,
                    "source_owner_note": f"Promoted from staged feed drop {Path(staging_dir).name}.",
                }
        promoted_rows.append(promote_row)

    if blockers:
        status = "blocked"
    elif promoted_rows:
        status = "dry_run_ready" if dry_run else "promoted"
    else:
        status = "awaiting_filled_staging_rows"
    if not dry_run and status == "promoted":
        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        manifest_file.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "dry_run": dry_run,
        "staging_gate_path": str(staging_gate_path),
        "feed_dir": str(feed_root),
        "manifest_path": str(manifest_file),
        "promoted_file_count": sum(1 for row in promoted_rows if row.get("status") in {"promoted", "dry_run"}),
        "promoted_row_count": sum(int(row.get("row_count") or 0) for row in promoted_rows if row.get("status") in {"promoted", "dry_run"}),
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "rows": promoted_rows,
        "recommended_next_actions": [
            "Run govern_rgroup_feed_metadata.py --write --require-allowlist --require-freshness after promotion.",
            "Run expand_rgroup_replacement_sources.py --require-source-acceptance --require-source-governance before normalization.",
            "Run run_production_ci.py before accepting the promoted feed drop.",
        ],
    }


def write_rgroup_feed_drop_promotion_report(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_FEED_DROP_PROMOTION_REPORT_PATH,
    csv_path: str | Path | None = DEFAULT_FEED_DROP_PROMOTION_CSV_PATH,
) -> None:
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if not csv_path:
        return
    rows = [dict(row) for row in report.get("rows") or []]
    fields = ["source_path", "target_path", "source_dataset", "row_count", "status"]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_rgroup_feed_drop_promotion_diff(
    *,
    staging_gate_path: str | Path = DEFAULT_FEED_DROP_STAGING_GATE_PATH,
    promotion_report_path: str | Path = DEFAULT_FEED_DROP_PROMOTION_REPORT_PATH,
    feed_dir: str | Path = DEFAULT_FEED_DIR,
) -> dict:
    """Build a dry review packet showing exactly what a staged feed would change."""
    gate = _read_json(staging_gate_path)
    promotion = _read_json(promotion_report_path)
    feed_root = Path(feed_dir)
    rows: list[dict] = []
    blockers: list[str] = list(gate.get("blockers") or [])
    warnings: list[str] = list(gate.get("warnings") or [])
    if promotion.get("status") == "blocked":
        blockers.extend(str(item) for item in promotion.get("blockers") or [])
    else:
        warnings.extend(str(item) for item in promotion.get("blockers") or [])

    for gate_row in gate.get("rows") or []:
        source_path = Path(str(gate_row.get("template_path") or gate_row.get("path") or ""))
        target_path = feed_root / source_path.name if source_path.name else Path("")
        source_exists = source_path.exists()
        target_exists = target_path.exists() if target_path.name else False
        source_info = _csv_info(source_path) if source_exists else {}
        target_info = _csv_info(target_path) if target_exists else {}
        staged_row_count = int(gate_row.get("row_count") or source_info.get("row_count") or 0)
        target_row_count = int(target_info.get("row_count") or 0)
        missing_sha = int(gate_row.get("missing_row_sha256_count") or source_info.get("missing_row_sha256_count") or 0)
        missing_required = list(gate_row.get("missing_required_columns") or source_info.get("missing_required_columns") or [])
        source_dataset = str(gate_row.get("source_dataset") or "").strip()

        if not source_exists:
            diff_status = "blocked_missing_source"
            blockers.append(f"missing_staged_file:{source_path.name}")
            action = "restore_or_regenerate_staged_template"
        elif missing_required:
            diff_status = "blocked_missing_required_columns"
            blockers.append(f"missing_required_columns:{source_path.name}")
            action = "fix_required_columns_before_promotion"
        elif missing_sha:
            diff_status = "blocked_missing_row_sha256"
            blockers.append(f"missing_row_sha256:{source_path.name}")
            action = "add_row_sha256_before_promotion"
        elif staged_row_count <= 0:
            diff_status = "awaiting_filled_rows"
            action = "fill_with_real_reviewed_rows"
        elif target_exists:
            diff_status = "target_exists_review_overwrite"
            warnings.append(f"target_feed_exists:{target_path.name}")
            action = "review_existing_target_or_use_overwrite"
        elif gate.get("status") == "ready_for_promotion":
            diff_status = "ready_to_promote"
            action = "promote_after_operator_review"
        else:
            diff_status = f"waiting_for_gate:{gate.get('status') or 'missing'}"
            action = "run_staging_gate_until_ready"

        rows.append(
            {
                "source_dataset": source_dataset,
                "source_path": str(source_path) if source_path.name else "",
                "target_path": str(target_path) if target_path.name else "",
                "source_exists": source_exists,
                "target_exists": target_exists,
                "staged_row_count": staged_row_count,
                "target_row_count": target_row_count,
                "missing_row_sha256_count": missing_sha,
                "missing_required_columns": missing_required,
                "source_dataset_values": gate_row.get("source_dataset_values", ""),
                "source_dataset_match": gate_row.get("source_dataset_match", ""),
                "diff_status": diff_status,
                "action": action,
            }
        )

    ready_count = sum(1 for row in rows if row.get("diff_status") == "ready_to_promote")
    awaiting_count = sum(1 for row in rows if row.get("diff_status") == "awaiting_filled_rows")
    overwrite_review_count = sum(1 for row in rows if row.get("diff_status") == "target_exists_review_overwrite")
    blocked_count = sum(1 for row in rows if str(row.get("diff_status") or "").startswith("blocked_"))
    if blocked_count or any(str(item).startswith(("missing_", "source_dataset_mismatch")) for item in blockers):
        status = "blocked"
    elif ready_count:
        status = "review_ready"
    elif rows and awaiting_count == len(rows):
        status = "awaiting_filled_staging_rows"
    elif rows:
        status = "review_required"
    else:
        status = "missing_staging_gate"

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "staging_gate_status": gate.get("status") or "missing",
        "promotion_status": promotion.get("status") or "missing",
        "feed_dir": str(feed_root),
        "staged_file_count": len(rows),
        "ready_to_promote_file_count": ready_count,
        "awaiting_filled_file_count": awaiting_count,
        "overwrite_review_file_count": overwrite_review_count,
        "blocked_file_count": blocked_count,
        "staged_row_count": sum(int(row.get("staged_row_count") or 0) for row in rows),
        "target_existing_row_count": sum(int(row.get("target_row_count") or 0) for row in rows),
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "rows": rows,
        "recommended_next_actions": [
            "Fill staged CSVs only with real reviewed rows and row_sha256 values.",
            "Review target_exists rows before overwrite; promotion should be an explicit operator action.",
            "Rebuild feed governance, normalization, owner ledger, production dashboard, and production CI after promotion.",
        ],
    }


def write_rgroup_feed_drop_promotion_diff(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_FEED_DROP_PROMOTION_DIFF_PATH,
    csv_path: str | Path | None = DEFAULT_FEED_DROP_PROMOTION_DIFF_CSV_PATH,
) -> None:
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if not csv_path:
        return
    fields = [
        "source_dataset",
        "source_path",
        "target_path",
        "source_exists",
        "target_exists",
        "staged_row_count",
        "target_row_count",
        "missing_row_sha256_count",
        "missing_required_columns",
        "source_dataset_values",
        "source_dataset_match",
        "diff_status",
        "action",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in report.get("rows") or []:
            writer.writerow({field: ";".join(row.get(field) or []) if isinstance(row.get(field), list) else row.get(field, "") for field in fields})
