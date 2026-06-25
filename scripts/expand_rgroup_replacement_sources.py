from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.mmp import DEFAULT_MMP_EVIDENCE_PATH  # noqa: E402
from localmedchem.data_foundation import validate_source_expansion_acceptance  # noqa: E402
from localmedchem.rgroup_expansion import expand_rgroup_replacement_sources, write_rgroup_expansion_outputs  # noqa: E402
from localmedchem.ring_library import DEFAULT_RGROUP_REPLACEMENTS_PATH  # noqa: E402


DEFAULT_EXTRA_RGROUP_SOURCES = [
    ROOT / "data" / "replacements" / "rgroup_additional_replacements.yaml",
    ROOT / "data" / "replacements" / "rgroup_mined_replacement_feed.csv",
]
DEFAULT_EXTRA_RGROUP_SOURCE_GLOBS = [
    str(ROOT / "data" / "replacements" / "feeds" / "*.yaml"),
    str(ROOT / "data" / "replacements" / "feeds" / "*.yml"),
    str(ROOT / "data" / "replacements" / "feeds" / "*.json"),
    str(ROOT / "data" / "replacements" / "feeds" / "*.csv"),
    str(ROOT / "data" / "replacements" / "feeds" / "*.tsv"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Expand R-group replacements with public MMP-derived and governed seed rows.")
    parser.add_argument("--rgroup-replacements", default=str(DEFAULT_RGROUP_REPLACEMENTS_PATH))
    parser.add_argument("--bajorath-xml", default=str(ROOT / "data" / "raw" / "literature" / "bajorath_top500_R_replacements.xml"))
    parser.add_argument("--mmp-evidence", default=str(DEFAULT_MMP_EVIDENCE_PATH))
    parser.add_argument("--yaml-out", default=str(DEFAULT_RGROUP_REPLACEMENTS_PATH))
    parser.add_argument("--json-out", default=str(ROOT / "data" / "substituents" / "rgroup_source_expansion_report.json"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs" / "rgroup_source_expansion_report.md"))
    parser.add_argument(
        "--extra-rgroup-source",
        action="append",
        default=[str(path) for path in DEFAULT_EXTRA_RGROUP_SOURCES if path.exists()],
        help="Additional governed seed source in YAML, JSON, CSV, or TSV format. May be repeated.",
    )
    parser.add_argument(
        "--extra-rgroup-source-glob",
        action="append",
        default=DEFAULT_EXTRA_RGROUP_SOURCE_GLOBS,
        help="Glob for bulk governed feed files. Defaults to data/replacements/feeds/*.{yaml,yml,json,csv,tsv}.",
    )
    parser.add_argument("--no-reverse", action="store_true", help="Only add the MMP transform orientation as mined.")
    parser.add_argument("--require-source-acceptance", action="store_true")
    parser.add_argument("--require-source-governance", action="store_true")
    parser.add_argument("--acceptance-table", default="rgroup_replacement")
    args = parser.parse_args()

    extra_paths = list(args.extra_rgroup_source or [])
    for pattern in args.extra_rgroup_source_glob or []:
        extra_paths.extend(sorted(glob.glob(pattern)))
    extra_paths = list(dict.fromkeys(str(Path(path)) for path in extra_paths if Path(path).exists()))

    report = expand_rgroup_replacement_sources(
        rgroup_path=args.rgroup_replacements,
        rgroup_xml_path=args.bajorath_xml,
        mmp_path=args.mmp_evidence,
        extra_paths=extra_paths,
        include_reverse=not args.no_reverse,
    )
    report["extra_source_paths"] = extra_paths
    base_count = max(int(report.get("base_count") or 0), 1)
    change_fraction = (int(report.get("merged_count") or 0) - int(report.get("base_count") or 0)) / base_count
    acceptance = validate_source_expansion_acceptance(
        table=args.acceptance_table,
        check="unexpected_count_jump",
        change_fraction=change_fraction,
        root=ROOT,
    )
    report["source_acceptance"] = acceptance
    if args.require_source_acceptance and not acceptance.get("accepted"):
        raise SystemExit(
            "Source expansion is missing an active source acceptance manifest entry "
            f"for table {args.acceptance_table} with jump_fraction={change_fraction:.4f}."
        )
    if args.require_source_governance and int(report.get("source_governance_blocker_count") or 0):
        raise SystemExit("Rejected or retired source rows reappeared in expanded R-group outputs.")
    write_rgroup_expansion_outputs(
        report,
        yaml_path=args.yaml_out,
        json_path=args.json_out,
        markdown_path=args.markdown_out,
    )
    print(json.dumps({key: value for key, value in report.items() if key != "rgroup_replacements"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
