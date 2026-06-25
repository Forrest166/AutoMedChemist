from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.database import (  # noqa: E402
    initialize_database,
    insert_literature_substituents,
    insert_rgroup_replacements,
    insert_ring_replacements,
    insert_ring_systems,
)
from localmedchem.ring_library import (  # noqa: E402
    deduplicate_records,
    file_sha256,
    load_ertl_ring_records,
    load_import_state,
    load_natural_product_substituents,
    load_rgroup_replacements,
    load_ring_replacements,
    load_shearer_ring_records,
    load_yaml_collection,
    merge_records_by_key,
    save_import_state,
    save_structures,
    validate_ring_substituent_collections,
)


RAW = ROOT / "data" / "raw" / "literature"


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize literature ring/substituent/R-group resources into governed YAML and SQLite.")
    parser.add_argument("--raw-dir", default=str(RAW))
    parser.add_argument("--ertl-ring-limit", type=int, default=12000)
    parser.add_argument("--ertl-ring-offset", type=int, default=0)
    parser.add_argument("--full-ertl-rings", action="store_true", help="Read the full Ertl ring file. Use with --db-only for large imports.")
    parser.add_argument("--append-existing", action="store_true", help="Merge this page with existing YAML outputs instead of replacing them.")
    parser.add_argument("--db-only", action="store_true", help="Write normalized rows to SQLite and report files without rewriting large YAML outputs.")
    parser.add_argument("--ring-replacement-limit", type=int, default=5000)
    parser.add_argument("--rgroup-replacement-limit", type=int, default=5000)
    parser.add_argument("--ring-out", default=str(ROOT / "data" / "rings" / "ring_system_library.yaml"))
    parser.add_argument("--substituent-out", default=str(ROOT / "data" / "substituents" / "literature_substituent_library.yaml"))
    parser.add_argument("--ring-replacements-out", default=str(ROOT / "data" / "replacements" / "ring_replacements.yaml"))
    parser.add_argument("--rgroup-replacements-out", default=str(ROOT / "data" / "replacements" / "rgroup_replacements.yaml"))
    parser.add_argument("--report-out", default=str(ROOT / "data" / "substituents" / "ring_substituent_quality_report.json"))
    parser.add_argument("--state-out", default=str(ROOT / "data" / "substituents" / "ring_import_state.json"))
    parser.add_argument("--db-out", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--write-db", action="store_true")
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    ertl_limit = 0 if args.full_ertl_rings else args.ertl_ring_limit
    if args.full_ertl_rings and not args.db_only:
        raise SystemExit("--full-ertl-rings must be used with --db-only to avoid writing a very large YAML file.")

    shearer_rings = load_shearer_ring_records(
        raw_dir / "shearer_drug_ring_systems_2020.txt",
        raw_dir / "shearer_clinical_ring_systems_2020.txt",
    )
    ertl_rings = load_ertl_ring_records(raw_dir / "ertl_4m_rings.zip", limit=ertl_limit, offset=args.ertl_ring_offset)
    ring_records = deduplicate_records([*shearer_rings, *ertl_rings], "canonical_smiles")
    literature_substituents = load_natural_product_substituents(raw_dir / "ertl_natural_product_substituents.txt")
    ring_replacements = load_ring_replacements(
        raw_dir / "ertl_ring_replacements_rrr_data.txt",
        limit=args.ring_replacement_limit,
    )
    rgroup_replacements = load_rgroup_replacements(
        raw_dir / "bajorath_top500_R_replacements.xml",
        limit=args.rgroup_replacement_limit,
    )

    if args.append_existing:
        ring_records = merge_records_by_key(
            load_yaml_collection(args.ring_out, "ring_systems"),
            ring_records,
            "canonical_smiles",
        )
        literature_substituents = merge_records_by_key(
            load_yaml_collection(args.substituent_out, "literature_substituents"),
            literature_substituents,
            "canonical_smiles",
        )
        ring_replacements = merge_records_by_key(
            load_yaml_collection(args.ring_replacements_out, "ring_replacements"),
            ring_replacements,
            "replacement_id",
        )
        rgroup_replacements = merge_records_by_key(
            load_yaml_collection(args.rgroup_replacements_out, "rgroup_replacements"),
            rgroup_replacements,
            "replacement_id",
        )

    if not args.db_only:
        save_structures(
            ring_records=ring_records,
            literature_substituents=literature_substituents,
            ring_replacements=ring_replacements,
            rgroup_replacements=rgroup_replacements,
            ring_out=args.ring_out,
            substituent_out=args.substituent_out,
            ring_replacements_out=args.ring_replacements_out,
            rgroup_replacements_out=args.rgroup_replacements_out,
        )
    report = validate_ring_substituent_collections(
        ring_records,
        literature_substituents,
        ring_replacements,
        rgroup_replacements,
    )
    ertl_next_offset = max((int(row.get("source_rank") or 0) for row in ertl_rings), default=args.ertl_ring_offset)
    report.update(
        {
            "shearer_ring_count": len(shearer_rings),
            "ertl_ring_count": len(ertl_rings),
            "ertl_ring_offset": args.ertl_ring_offset,
            "ertl_ring_limit": ertl_limit,
            "ertl_ring_next_offset": ertl_next_offset,
            "ertl_ring_source_sha256": file_sha256(raw_dir / "ertl_4m_rings.zip"),
            "db_only": bool(args.db_only),
            "outputs": {
                "ring_library": str(Path(args.ring_out).resolve()),
                "literature_substituents": str(Path(args.substituent_out).resolve()),
                "ring_replacements": str(Path(args.ring_replacements_out).resolve()),
                "rgroup_replacements": str(Path(args.rgroup_replacements_out).resolve()),
            },
        }
    )
    Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report_out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    state = {
        **load_import_state(args.state_out),
        "ertl_4m_ring_systems": {
            "source_path": str((raw_dir / "ertl_4m_rings.zip").resolve()),
            "source_sha256": report["ertl_ring_source_sha256"],
            "last_offset": args.ertl_ring_offset,
            "last_limit": ertl_limit,
            "last_imported_count": len(ertl_rings),
            "next_offset": report["ertl_ring_next_offset"],
            "full_import_requested": bool(args.full_ertl_rings),
            "db_only": bool(args.db_only),
        },
    }
    save_import_state(state, args.state_out)

    if args.write_db:
        conn = initialize_database(args.db_out)
        try:
            insert_ring_systems(conn, ring_records)
            insert_literature_substituents(conn, literature_substituents)
            insert_ring_replacements(conn, ring_replacements)
            insert_rgroup_replacements(conn, rgroup_replacements)
        finally:
            conn.close()

    print(json.dumps({key: value for key, value in report.items() if key != "issues"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
