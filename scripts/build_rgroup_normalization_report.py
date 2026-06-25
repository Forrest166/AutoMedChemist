from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.database import initialize_database, insert_rgroup_replacements, rebuild_normalized_rgroup_replacements  # noqa: E402
from localmedchem.rgroup_normalization import build_rgroup_normalization_report  # noqa: E402
from localmedchem.ring_library import DEFAULT_RGROUP_REPLACEMENTS_PATH, load_yaml_collection  # noqa: E402


def _render_markdown(report: dict) -> str:
    lines = [
        "# R-group Normalization Report",
        "",
        f"- Input records: {report.get('input_count', 0)}",
        f"- Normalized records: {report.get('normalized_count', 0)}",
        f"- Deduplicated directional pairs: {report.get('deduplicated_count', 0)}",
        f"- Duplicate groups: {report.get('duplicate_group_count', 0)}",
        f"- Duplicate records collapsed: {report.get('duplicate_record_count', 0)}",
        f"- Invalid or blank endpoint rows: {report.get('invalid_or_blank_endpoint_count', 0)}",
        "",
        "## Top Duplicate Groups",
        "",
        "| Pair key | Records | Aggregate weight | Layers | Confidence tiers | Sources |",
        "|---|---:|---:|---|---|---|",
    ]
    for row in report.get("top_duplicate_groups") or []:
        lines.append(
            "| {pair} | {count} | {weight} | {layers} | {confidence} | {sources} |".format(
                pair=str(row.get("normalized_pair_key") or "").replace("|", "\\|"),
                count=row.get("source_record_count") or 0,
                weight=row.get("aggregate_edge_weight") or 0,
                layers=str(row.get("layers") or "").replace("|", "\\|"),
                confidence=str(row.get("source_confidence_tiers") or "").replace("|", "\\|"),
                sources=str(row.get("source_names") or "").replace("|", "\\|"),
            )
        )
    if not report.get("top_duplicate_groups"):
        lines.append("| None | 0 | 0 |  |  |  |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build R-group endpoint normalization and de-duplication report.")
    parser.add_argument("--rgroup-replacements", default=str(DEFAULT_RGROUP_REPLACEMENTS_PATH))
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--json-out", default=str(ROOT / "data" / "substituents" / "rgroup_normalization_report.json"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs" / "rgroup_normalization_report.md"))
    parser.add_argument("--write-db", action="store_true", help="Refresh the normalized R-group SQLite table from raw rows.")
    parser.add_argument("--refresh-raw-db", action="store_true", help="Replace raw R-group SQLite rows from the YAML file before normalization.")
    args = parser.parse_args()

    rows = load_yaml_collection(args.rgroup_replacements, "rgroup_replacements")
    report = build_rgroup_normalization_report(rows)
    if args.write_db:
        conn = initialize_database(args.db_path)
        try:
            if args.refresh_raw_db:
                conn.execute("DELETE FROM rgroup_replacement_normalized")
                conn.execute("DELETE FROM rgroup_replacement")
                conn.commit()
                insert_rgroup_replacements(conn, rows)
                report["sqlite_raw_refresh"] = {"raw_count": len(rows)}
            report["sqlite_refresh"] = rebuild_normalized_rgroup_replacements(conn)
        finally:
            conn.close()

    json_path = Path(args.json_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path = Path(args.markdown_out)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
