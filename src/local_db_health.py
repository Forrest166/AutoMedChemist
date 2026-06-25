from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")
DEFAULT_DB_HEALTH_PATH = Path("data/releases/local_db_health_report.json")
DEFAULT_DB_HEALTH_CSV_PATH = Path("data/releases/local_db_health_report.csv")

EXPECTED_TABLES = [
    "ring_system",
    "rgroup_replacement",
    "rgroup_replacement_normalized",
    "project_candidate",
    "data_foundation_snapshot",
]


def _resolve(root: Path, path: str | Path) -> Path:
    item = Path(path)
    return item if item.is_absolute() else root / item


def _count_rows(conn: sqlite3.Connection, table: str) -> int | None:
    try:
        return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    except Exception:
        return None


def build_local_db_health_report(
    root: str | Path = ".",
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    run_quick_check: bool = False,
) -> dict[str, Any]:
    root_path = Path(root)
    db_file = _resolve(root_path, db_path)
    report: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_file),
        "exists": db_file.exists(),
        "size_bytes": db_file.stat().st_size if db_file.exists() else 0,
        "expected_tables": EXPECTED_TABLES,
        "table_rows": {},
        "table_status_rows": [],
        "index_count": 0,
        "ring_index_count": 0,
        "status": "missing",
        "recommended_next_actions": [],
    }
    if not db_file.exists():
        report["recommended_next_actions"] = [
            "Keep candidate generation available without ring-library recommendations.",
            "Restore data/localmedchem.sqlite when full ring-search and project warehouse features are needed.",
        ]
        return report

    try:
        with sqlite3.connect(db_file) as conn:
            conn.row_factory = sqlite3.Row
            page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
            page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
            integrity = str(conn.execute("PRAGMA quick_check").fetchone()[0]) if run_quick_check else "skipped_light_health"
            indexes = conn.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index'").fetchall()
            table_names = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            report.update(
                {
                    "connectable": True,
                    "quick_check": integrity,
                    "quick_check_ran": run_quick_check,
                    "page_count": page_count,
                    "page_size": page_size,
                    "sqlite_size_bytes": page_count * page_size,
                    "index_count": len(indexes),
                    "ring_index_count": sum(1 for row in indexes if str(row["tbl_name"]) == "ring_system"),
                }
            )
            missing_tables = []
            for table in EXPECTED_TABLES:
                exists = table in table_names
                row_count = _count_rows(conn, table) if exists else None
                if not exists:
                    missing_tables.append(table)
                report["table_rows"][table] = row_count
                report["table_status_rows"].append(
                    {
                        "table": table,
                        "exists": exists,
                        "row_count": row_count,
                    }
                )
            if run_quick_check and integrity != "ok":
                report["status"] = "degraded"
                report["recommended_next_actions"].append("Run SQLite integrity repair or restore a known-good warehouse copy.")
            elif missing_tables:
                report["status"] = "degraded"
                report["recommended_next_actions"].append(f"Rebuild missing tables: {', '.join(missing_tables)}.")
            elif int(report.get("ring_index_count") or 0) == 0:
                report["status"] = "degraded"
                report["recommended_next_actions"].append("Apply ring-system indexes before large ring-library searches.")
            else:
                report["status"] = "healthy"
                report["recommended_next_actions"].append("Database is available for full local ring-search and project warehouse workflows.")
    except Exception as exc:
        report["connectable"] = False
        report["status"] = "error"
        report["error"] = str(exc)
        report["recommended_next_actions"].append("Check SQLite file permissions and retry local DB health smoke.")
    return report


def write_local_db_health_report(
    report: dict,
    json_path: str | Path = DEFAULT_DB_HEALTH_PATH,
    csv_path: str | Path = DEFAULT_DB_HEALTH_CSV_PATH,
) -> None:
    json_file = Path(json_path)
    csv_file = Path(csv_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    with csv_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["table", "exists", "row_count"])
        writer.writeheader()
        writer.writerows(report.get("table_status_rows") or [])
