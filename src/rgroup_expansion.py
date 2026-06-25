from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import yaml

from .mmp import load_mmp_evidence
from .ring_library import load_rgroup_replacements, load_yaml_collection, normalize_attachment_smiles
from .rgroup_normalization import build_rgroup_normalization_report


def _edge_weight(row: dict) -> int:
    candidates = (
        row.get("pair_count"),
        row.get("mmp_pair_count"),
        row.get("core_count"),
        row.get("mmp_core_count"),
        row.get("example_count"),
        row.get("mmp_example_count"),
        row.get("edge_weight"),
    )
    try:
        return max(1, int(float(next((value for value in candidates if value is not None and value != ""), 1))))
    except (TypeError, ValueError):
        return 1


def _normalize_endpoint(value: str | None) -> str | None:
    try:
        return normalize_attachment_smiles(str(value or ""))
    except Exception:
        return None


def _digest_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}-{digest}"


def _row_sha256(row: dict) -> str:
    payload = {key: value for key, value in row.items() if key != "row_sha256"}
    text = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _confidence_annotation(row: dict) -> dict:
    source_dataset = str(row.get("source_dataset") or "").lower()
    source_name = str(row.get("source_name") or "").lower()
    layer = str(row.get("layer") or "").lower()
    pair_count = _edge_weight(row)
    if source_dataset == "chembl_mmp_transform_evidence" or layer == "public_mmp":
        if pair_count >= 8:
            return {
                "source_confidence_tier": "public_mmp_high",
                "source_confidence_score": 0.76,
                "source_confidence_basis": "Public rdMMPA transform with repeated pair support.",
            }
        if pair_count >= 3:
            return {
                "source_confidence_tier": "public_mmp_medium",
                "source_confidence_score": 0.68,
                "source_confidence_basis": "Public rdMMPA transform with moderate pair support.",
            }
        return {
            "source_confidence_tier": "public_mmp_provisional",
            "source_confidence_score": 0.58,
            "source_confidence_basis": "Public rdMMPA transform retained as provisional single/few-pair evidence.",
        }
    if "bajorath" in source_name or "r-group replacement database" in source_name:
        return {
            "source_confidence_tier": "curated_rgroup_network_seed",
            "source_confidence_score": 0.82,
            "source_confidence_basis": "Reviewed Bajorath/Takeuchi/Kunimoto R-group replacement seed network.",
        }
    if "literature" in source_dataset or "bioisostere" in source_dataset or "meanwell" in source_name:
        return {
            "source_confidence_tier": "literature_bioisostere_seed",
            "source_confidence_score": 0.72,
            "source_confidence_basis": "Literature-derived bioisostere seed retained with curated-source provenance.",
        }
    if "analog" in source_dataset or "analog" in source_name:
        return {
            "source_confidence_tier": "analog_series_seed",
            "source_confidence_score": 0.66,
            "source_confidence_basis": "Analog-series replacement seed retained for calibration before promotion.",
        }
    if "patent" in source_dataset or "patent" in source_name:
        return {
            "source_confidence_tier": "patent_mined_seed",
            "source_confidence_score": 0.62,
            "source_confidence_basis": "Patent/literature-mined replacement seed retained as governed provisional evidence.",
        }
    return {
        "source_confidence_tier": "unclassified_source",
        "source_confidence_score": 0.5,
        "source_confidence_basis": "Source loaded but not yet assigned to a governed confidence tier.",
    }


SOURCE_ENDPOINT_FIELDS = ("source_smiles", "from_smiles", "source_fragment", "from_fragment", "rgroup_from", "from")
TARGET_ENDPOINT_FIELDS = ("target_smiles", "to_smiles", "target_fragment", "to_fragment", "rgroup_to", "to")
ADDITIONAL_SOURCE_KEYS = (
    "rgroup_replacements",
    "additional_rgroup_replacements",
    "analog_series_replacements",
    "patent_replacements",
    "literature_replacements",
    "bioisostere_replacements",
    "replacements",
)
SOURCE_PROVENANCE_FIELDS = (
    "row_sha256",
    "source_owner",
    "source_license",
    "provenance_level",
    "provenance_review_status",
)
EXCLUDED_REVIEW_STATUSES = {"rejected", "retired", "excluded"}


def _first_present(row: dict, fields: tuple[str, ...]) -> object | None:
    for field in fields:
        value = row.get(field)
        if value not in {None, ""}:
            return value
    return None


def _rows_from_payload(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        if _first_present(payload, SOURCE_ENDPOINT_FIELDS) is not None and _first_present(payload, TARGET_ENDPOINT_FIELDS) is not None:
            return [dict(payload)]
        for key in ADDITIONAL_SOURCE_KEYS:
            rows = payload.get(key)
            if isinstance(rows, list):
                return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def _structured_source_rows(path: str | Path) -> tuple[list[dict], str]:
    source_path = Path(path)
    if not source_path.exists():
        return [], "missing"
    suffix = source_path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle, delimiter=delimiter)], "table"
    if suffix == ".json":
        return _rows_from_payload(json.loads(source_path.read_text(encoding="utf-8"))), "json"
    if suffix in {".yaml", ".yml"}:
        with source_path.open("r", encoding="utf-8") as handle:
            return _rows_from_payload(yaml.safe_load(handle) or {}), "yaml"
    return [], "unsupported_format"


def _source_dataset_for_path(path: str | Path, row: dict) -> str:
    explicit = row.get("source_dataset") or row.get("dataset") or row.get("source_type")
    if explicit:
        return str(explicit)
    text = " ".join([Path(path).stem, str(row.get("source_name") or ""), str(row.get("source_reference") or "")]).lower()
    if "patent" in text:
        return "patent_mined_seed"
    if "analog" in text or "series" in text:
        return "analog_series_seed"
    if "literature" in text or "bioisostere" in text or "meanwell" in text:
        return "literature_bioisostere_seed"
    return "additional_rgroup_seed"


def _source_name_for_path(path: str | Path, row: dict, source_dataset: str) -> str:
    if row.get("source_name"):
        return str(row["source_name"])
    labels = {
        "analog_series_seed": "Governed analog-series R-group feed",
        "patent_mined_seed": "Governed patent-mined R-group feed",
        "literature_bioisostere_seed": "Governed literature bioisostere feed",
    }
    return labels.get(source_dataset, f"Additional governed R-group feed: {Path(path).name}")


def _provenance_defaults(source_dataset: str) -> dict:
    defaults = {
        "analog_series_seed": {
            "source_owner": "AutoMedChemist curated analog-series feed",
            "source_license": "internal_reviewed_reference",
            "provenance_level": "curated_seed",
            "provenance_review_status": "reviewed",
        },
        "literature_bioisostere_seed": {
            "source_owner": "AutoMedChemist literature curation",
            "source_license": "literature_derived_summary",
            "provenance_level": "literature_curated_seed",
            "provenance_review_status": "reviewed",
        },
        "patent_mined_seed": {
            "source_owner": "AutoMedChemist patent/literature mining",
            "source_license": "provisional_patent_derived_summary",
            "provenance_level": "provisional_mined_seed",
            "provenance_review_status": "provisional_reviewed",
        },
    }
    return defaults.get(
        source_dataset,
        {
            "source_owner": "AutoMedChemist local governed feed",
            "source_license": "local_governed_reference",
            "provenance_level": "local_seed",
            "provenance_review_status": "needs_review",
        },
    )


def annotate_source_confidence(rows: list[dict]) -> list[dict]:
    annotated = []
    for row in rows:
        item = dict(row)
        if not item.get("source_confidence_tier"):
            item.update(_confidence_annotation(item))
        annotated.append(item)
    return annotated


def mmp_rows_to_rgroup_replacements(mmp_rows: list[dict], *, include_reverse: bool = True) -> list[dict]:
    """Convert public single-cut MMP variable-fragment rows into R-group replacement rows."""
    out: list[dict] = []
    for row in mmp_rows:
        source = _normalize_endpoint(row.get("variable_from_smiles"))
        target = _normalize_endpoint(row.get("variable_to_smiles"))
        if not source or not target or source == target:
            continue
        base = {
            "edge_weight": _edge_weight(row),
            "layer": "public_mmp",
            "center_smiles": "",
            "source_name": row.get("source_name") or "ChEMBL rdMMPA",
            "source_reference": "local ChEMBL rdMMPA mined transform evidence",
            "source_dataset": "chembl_mmp_transform_evidence",
            "source_transform_id": row.get("transform_id"),
            "mmp_pair_count": row.get("pair_count"),
            "mmp_core_count": row.get("core_count"),
            "mmp_example_count": row.get("example_count"),
            "mmp_example_molecule_ids": row.get("example_molecule_ids") or [],
        }
        out.append(
            {
                **base,
                "replacement_id": _digest_id("RG-MMP", row.get("transform_id"), source, target, "forward"),
                "source_smiles": source,
                "target_smiles": target,
                "source_canonical_smiles": source,
                "target_canonical_smiles": target,
                "orientation": "forward",
            }
        )
        if include_reverse:
            out.append(
                {
                    **base,
                    "replacement_id": _digest_id("RG-MMP", row.get("transform_id"), target, source, "reverse"),
                    "source_smiles": target,
                    "target_smiles": source,
                    "source_canonical_smiles": target,
                    "target_canonical_smiles": source,
                    "orientation": "reverse",
                }
            )
    return out


def _additional_source_rows(path: str | Path) -> list[dict]:
    rows, _ = _structured_source_rows(path)
    return rows


def load_additional_rgroup_replacement_report(paths: list[str | Path] | tuple[str | Path, ...]) -> dict:
    """Load governed R-group seed feeds, normalize endpoints, and report rejects by source."""
    replacements: list[dict] = []
    path_reports = []
    invalid_rows = []
    excluded_rows = []
    for path in paths:
        raw_rows, source_format = _structured_source_rows(path)
        source_path = Path(path)
        accepted = []
        invalid = []
        missing_metadata_count = 0
        row_checksum_count = 0
        for index, raw_row in enumerate(raw_rows, start=1):
            row = dict(raw_row)
            review_status = str(row.get("provenance_review_status") or "").strip().lower()
            review_decision = str(row.get("source_review_decision") or "").strip().lower()
            if review_status in EXCLUDED_REVIEW_STATUSES or review_decision in EXCLUDED_REVIEW_STATUSES:
                source = _normalize_endpoint(_first_present(row, SOURCE_ENDPOINT_FIELDS))
                target = _normalize_endpoint(_first_present(row, TARGET_ENDPOINT_FIELDS))
                source_dataset = _source_dataset_for_path(source_path, row)
                excluded = {
                    "path": str(source_path),
                    "row_number": index,
                    "replacement_id": row.get("replacement_id"),
                    "row_sha256": row.get("row_sha256"),
                    "source_dataset": source_dataset,
                    "source_smiles": source,
                    "target_smiles": target,
                    "reason": "review_rejected_or_retired",
                }
                invalid.append(excluded)
                excluded_rows.append(excluded)
                continue
            source = _normalize_endpoint(_first_present(row, SOURCE_ENDPOINT_FIELDS))
            target = _normalize_endpoint(_first_present(row, TARGET_ENDPOINT_FIELDS))
            if not source or not target or source == target:
                reason = "missing_or_invalid_endpoint" if source != target else "self_replacement"
                invalid.append({"path": str(source_path), "row_number": index, "reason": reason})
                continue
            source_dataset = _source_dataset_for_path(source_path, row)
            if any(not str(row.get(field) or "").strip() for field in SOURCE_PROVENANCE_FIELDS):
                missing_metadata_count += 1
            if str(row.get("row_sha256") or "").strip():
                row_checksum_count += 1
            item = dict(row)
            provenance = _provenance_defaults(source_dataset)
            item.update(
                {
                    "replacement_id": item.get("replacement_id")
                    or _digest_id("RG-SEED", source_dataset, source, target, index, source_path.name),
                    "source_smiles": source,
                    "target_smiles": target,
                    "source_canonical_smiles": source,
                    "target_canonical_smiles": target,
                    "edge_weight": _edge_weight(item),
                    "layer": item.get("layer") or "additional_seed",
                    "center_smiles": item.get("center_smiles") or "",
                    "source_name": _source_name_for_path(source_path, item, source_dataset),
                    "source_dataset": source_dataset,
                    "source_reference": item.get("source_reference") or f"local governed seed file: {source_path.name}",
                    "parser_source_path": str(source_path),
                    "parser_row_number": index,
                    "source_record_id": item.get("source_record_id") or item.get("record_id") or item.get("patent_id") or item.get("series_id"),
                    "source_owner": item.get("source_owner") or provenance["source_owner"],
                    "source_license": item.get("source_license") or provenance["source_license"],
                    "provenance_level": item.get("provenance_level") or provenance["provenance_level"],
                    "provenance_review_status": item.get("provenance_review_status") or provenance["provenance_review_status"],
                    "provenance_note": item.get("provenance_note") or item.get("evidence_note") or "",
                }
            )
            item["row_sha256"] = item.get("row_sha256") or _row_sha256(item)
            accepted.append(item)
            replacements.append(item)
        invalid_rows.extend(invalid)
        path_reports.append(
            {
                "path": str(source_path),
                "format": source_format,
                "input_row_count": len(raw_rows),
                "accepted_count": len(accepted),
                "invalid_count": len(invalid),
                "missing_metadata_count": missing_metadata_count,
                "row_checksum_count": row_checksum_count,
                "source_counts": dict(Counter(str(row.get("source_dataset") or "unknown") for row in accepted).most_common()),
            }
        )
    return {
        "rows": replacements,
        "path_reports": path_reports,
        "invalid_rows": invalid_rows,
        "invalid_count": len(invalid_rows),
        "excluded_rows": excluded_rows,
        "excluded_count": len(excluded_rows),
        "missing_metadata_count": sum(int(report.get("missing_metadata_count") or 0) for report in path_reports),
        "row_checksum_count": sum(int(report.get("row_checksum_count") or 0) for report in path_reports),
    }


def load_additional_rgroup_replacement_rows(paths: list[str | Path] | tuple[str | Path, ...]) -> list[dict]:
    """Load governed non-XML R-group seeds and normalize attachment endpoints."""
    return list(load_additional_rgroup_replacement_report(paths).get("rows") or [])


def merge_rgroup_replacements(base_rows: list[dict], extra_rows: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: dict[str, int] = {}
    for row in [*base_rows, *extra_rows]:
        replacement_id = str(row.get("replacement_id") or "")
        if not replacement_id:
            continue
        item = dict(row)
        seen[replacement_id] = seen.get(replacement_id, 0) + 1
        if seen[replacement_id] > 1:
            item["original_replacement_id"] = replacement_id
            item["replacement_id"] = f"{replacement_id}-D{seen[replacement_id]:04d}"
        merged.append(item)
    return merged


def expand_rgroup_replacement_sources(
    *,
    rgroup_path: str | Path,
    rgroup_xml_path: str | Path | None = None,
    mmp_path: str | Path | None = None,
    extra_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
    include_reverse: bool = True,
) -> dict:
    base_rows = (
        load_rgroup_replacements(rgroup_xml_path, limit=5000)
        if rgroup_xml_path is not None and Path(rgroup_xml_path).exists()
        else load_yaml_collection(rgroup_path, "rgroup_replacements")
    )
    mmp_rows = load_mmp_evidence(mmp_path)
    mmp_replacements = mmp_rows_to_rgroup_replacements(mmp_rows, include_reverse=include_reverse)
    additional_report = load_additional_rgroup_replacement_report(list(extra_paths or []))
    additional_replacements = list(additional_report.get("rows") or [])
    merged = annotate_source_confidence(merge_rgroup_replacements(base_rows, [*mmp_replacements, *additional_replacements]))
    excluded_ids = {
        str(row.get("replacement_id"))
        for row in additional_report.get("excluded_rows") or []
        if row.get("replacement_id")
    }
    excluded_hashes = {
        str(row.get("row_sha256"))
        for row in additional_report.get("excluded_rows") or []
        if row.get("row_sha256")
    }
    blocked_reentries = [
        {
            "replacement_id": row.get("replacement_id"),
            "row_sha256": row.get("row_sha256"),
            "source_dataset": row.get("source_dataset"),
            "source_smiles": row.get("source_smiles") or row.get("source_canonical_smiles"),
            "target_smiles": row.get("target_smiles") or row.get("target_canonical_smiles"),
            "reason": "excluded_source_row_reappeared",
        }
        for row in merged
        if (row.get("replacement_id") and str(row.get("replacement_id")) in excluded_ids)
        or (row.get("row_sha256") and str(row.get("row_sha256")) in excluded_hashes)
    ]
    source_counts = Counter(str(row.get("source_dataset") or row.get("source_name") or "unknown") for row in merged)
    confidence_counts = Counter(str(row.get("source_confidence_tier") or "unknown") for row in merged)
    normalization = build_rgroup_normalization_report(merged)
    return {
        "base_count": len(base_rows),
        "mmp_transform_count": len(mmp_rows),
        "mmp_replacement_count": len(mmp_replacements),
        "additional_seed_count": len(additional_replacements),
        "additional_source_reports": additional_report.get("path_reports") or [],
        "additional_invalid_count": additional_report.get("invalid_count") or 0,
        "additional_invalid_rows": additional_report.get("invalid_rows") or [],
        "additional_excluded_count": additional_report.get("excluded_count") or 0,
        "additional_excluded_rows": additional_report.get("excluded_rows") or [],
        "blocked_reentry_count": len(blocked_reentries),
        "blocked_reentries": blocked_reentries,
        "source_governance_blocker_count": len(blocked_reentries),
        "additional_missing_metadata_count": additional_report.get("missing_metadata_count") or 0,
        "additional_row_checksum_count": additional_report.get("row_checksum_count") or 0,
        "merged_count": len(merged),
        "source_counts": dict(source_counts.most_common()),
        "source_confidence_counts": dict(confidence_counts.most_common()),
        "normalization": normalization,
        "rgroup_replacements": merged,
    }


def write_rgroup_expansion_outputs(report: dict, *, yaml_path: str | Path, json_path: str | Path, markdown_path: str | Path) -> None:
    rows = report.get("rgroup_replacements") or []
    yaml_file = Path(yaml_path)
    yaml_file.parent.mkdir(parents=True, exist_ok=True)
    yaml_file.write_text(
        yaml.safe_dump(
            {
                "version": "rgroup-replacements-expanded-0.2",
                "description": "R-group replacement network with Bajorath seed rows, public MMP-derived variable-fragment replacements, and governed literature/analog/patent seeds.",
                "rgroup_replacements": rows,
            },
            sort_keys=False,
            allow_unicode=False,
        ),
        encoding="utf-8",
    )
    compact = {key: value for key, value in report.items() if key != "rgroup_replacements"}
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(compact, indent=2, sort_keys=True), encoding="utf-8")
    md_file = Path(markdown_path)
    md_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# R-group Source Expansion",
        "",
        f"- Base rows before merge: `{report.get('base_count')}`",
        f"- MMP transforms read: `{report.get('mmp_transform_count')}`",
        f"- MMP-derived directional rows: `{report.get('mmp_replacement_count')}`",
        f"- Additional governed seed rows: `{report.get('additional_seed_count')}`",
        f"- Additional governed invalid rows: `{report.get('additional_invalid_count')}`",
        f"- Additional rejected/retired rows excluded: `{report.get('additional_excluded_count')}`",
        f"- Blocked rejected/retired row re-entry count: `{report.get('blocked_reentry_count')}`",
        f"- Additional feed rows missing governance metadata before defaults: `{report.get('additional_missing_metadata_count')}`",
        f"- Additional feed rows with row checksum: `{report.get('additional_row_checksum_count')}`",
        f"- Merged R-group rows: `{report.get('merged_count')}`",
        f"- Normalized directional pairs: `{(report.get('normalization') or {}).get('deduplicated_count')}`",
        "",
        "## Additional Source Feeds",
        "",
        "| Source file | Format | Input rows | Accepted | Invalid |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for source_report in report.get("additional_source_reports") or []:
        lines.append(
            "| `{path}` | `{fmt}` | `{input_count}` | `{accepted}` | `{invalid}` |".format(
                path=source_report.get("path"),
                fmt=source_report.get("format"),
                input_count=source_report.get("input_row_count"),
                accepted=source_report.get("accepted_count"),
                invalid=source_report.get("invalid_count"),
            )
        )
    lines.extend(
        [
            "",
            "## Source Counts",
            "",
        ]
    )
    for source, count in (report.get("source_counts") or {}).items():
        lines.append(f"- `{source}`: `{count}`")
    lines.extend(["", "## Source Confidence Tiers", ""])
    for tier, count in (report.get("source_confidence_counts") or {}).items():
        lines.append(f"- `{tier}`: `{count}`")
    lines.append("")
    md_file.write_text("\n".join(lines), encoding="utf-8")
