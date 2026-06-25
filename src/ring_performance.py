from __future__ import annotations

import csv
import json
import sqlite3
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")

RECOMMENDED_RING_INDEXES = {
    "idx_ring_system_dataset_rank": "CREATE INDEX IF NOT EXISTS idx_ring_system_dataset_rank ON ring_system(source_dataset, source_rank)",
    "idx_ring_system_dataset_class_heavy": (
        "CREATE INDEX IF NOT EXISTS idx_ring_system_dataset_class_heavy "
        "ON ring_system(source_dataset, ring_class, heavy_atom_count)"
    ),
    "idx_ring_system_dataset_class_rank": (
        "CREATE INDEX IF NOT EXISTS idx_ring_system_dataset_class_rank "
        "ON ring_system(source_dataset, ring_class, source_rank)"
    ),
}


def ensure_ring_performance_indexes(conn: sqlite3.Connection) -> list[str]:
    """Create indexes used by large ring-system browse and import status queries."""
    created_or_present = []
    for name, sql in RECOMMENDED_RING_INDEXES.items():
        conn.execute(sql)
        created_or_present.append(name)
    conn.commit()
    return created_or_present


def _existing_indexes(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("PRAGMA index_list(ring_system)").fetchall()
    return sorted(str(row[1]) for row in rows)


def _time_query(conn: sqlite3.Connection, sql: str, params: tuple[object, ...] = (), *, repetitions: int = 3) -> dict:
    conn.execute(sql, params).fetchall()
    timings = []
    row_count = 0
    for _ in range(max(5, repetitions)):
        start = time.perf_counter()
        rows = conn.execute(sql, params).fetchall()
        timings.append((time.perf_counter() - start) * 1000.0)
        row_count = len(rows)
    return {
        "row_count": row_count,
        "avg_ms": round(sum(timings) / len(timings), 4),
        "median_ms": round(statistics.median(timings), 4),
        "min_ms": round(min(timings), 4),
        "max_ms": round(max(timings), 4),
    }


def build_ring_db_performance_report(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    apply_maintenance: bool = False,
    repetitions: int = 3,
    warn_ms: float = 250.0,
    limit: int = 25,
    cache_path: str | Path | None = None,
    cache_ttl_seconds: int | float | None = 86400,
) -> dict:
    """Measure common ring-system queries and surface missing performance indexes."""
    conn = sqlite3.connect(db_path)
    try:
        if apply_maintenance:
            ensure_ring_performance_indexes(conn)
            conn.execute("ANALYZE")
            conn.execute("PRAGMA optimize")
        conn.row_factory = sqlite3.Row
        indexes = _existing_indexes(conn)
        missing_indexes = [name for name in RECOMMENDED_RING_INDEXES if name not in indexes]
        ring_count = int(conn.execute("SELECT COUNT(*) FROM ring_system").fetchone()[0])
        ertl_count = int(
            conn.execute("SELECT COUNT(*) FROM ring_system WHERE source_dataset='ertl_4m_ring_systems'").fetchone()[0]
        )
        max_rank = int(
            conn.execute(
                "SELECT COALESCE(MAX(source_rank), 0) FROM ring_system WHERE source_dataset='ertl_4m_ring_systems'"
            ).fetchone()[0]
            or 0
        )
        top_class = conn.execute(
            """
            SELECT COALESCE(ring_class, 'unclassified') AS ring_class
            FROM ring_system
            WHERE source_dataset='ertl_4m_ring_systems'
            GROUP BY COALESCE(ring_class, 'unclassified')
            ORDER BY COUNT(*) DESC
            LIMIT 1
            """
        ).fetchone()
        ring_class = str(top_class["ring_class"]) if top_class else "aromatic_heterocycle"
        rank_floor = max(0, max_rank - 1000)
        queries = {
            "count_ertl": _time_query(
                conn,
                "SELECT COUNT(*) AS n FROM ring_system WHERE source_dataset='ertl_4m_ring_systems'",
                repetitions=repetitions,
            ),
            "top_ertl_rank": _time_query(
                conn,
                """
                SELECT ring_id, source_rank, canonical_smiles
                FROM ring_system INDEXED BY idx_ring_system_dataset_rank
                WHERE source_dataset='ertl_4m_ring_systems'
                ORDER BY source_rank
                LIMIT ?
                """,
                (int(limit),),
                repetitions=repetitions,
            ),
            "class_heavy_filter": _time_query(
                conn,
                """
                SELECT ring_id, source_rank, canonical_smiles
                FROM ring_system INDEXED BY idx_ring_system_dataset_class_rank
                WHERE source_dataset='ertl_4m_ring_systems'
                  AND ring_class=?
                  AND heavy_atom_count BETWEEN 5 AND 18
                ORDER BY source_rank
                LIMIT ?
                """,
                (ring_class, int(limit)),
                repetitions=repetitions,
            ),
            "source_rank_window": _time_query(
                conn,
                """
                SELECT ring_id, source_rank, canonical_smiles
                FROM ring_system
                WHERE source_dataset='ertl_4m_ring_systems'
                  AND source_rank BETWEEN ? AND ?
                ORDER BY source_rank
                LIMIT ?
                """,
                (rank_floor, max_rank, int(limit)),
                repetitions=repetitions,
            ),
        }
    finally:
        conn.close()

    cache_benchmark = {"enabled": bool(cache_path)}
    if cache_path:
        try:
            from .ring_recommender import recommend_ring_systems

            cold = recommend_ring_systems(
                db_path=db_path,
                source_dataset="ertl_4m_ring_systems",
                ring_class=ring_class,
                min_heavy_atom_count=5,
                max_heavy_atom_count=18,
                limit=limit,
                cache_path=cache_path,
                cache_ttl_seconds=cache_ttl_seconds,
            )
            warm = recommend_ring_systems(
                db_path=db_path,
                source_dataset="ertl_4m_ring_systems",
                ring_class=ring_class,
                min_heavy_atom_count=5,
                max_heavy_atom_count=18,
                limit=limit,
                cache_path=cache_path,
                cache_ttl_seconds=cache_ttl_seconds,
            )
            cache_benchmark.update(
                {
                    "cold_cache_hit": bool((cold.get("cache") or {}).get("hit")),
                    "warm_cache_hit": bool((warm.get("cache") or {}).get("hit")),
                    "cold_query_elapsed_ms": cold.get("query_elapsed_ms"),
                    "returned_count": warm.get("returned_count"),
                    "cache_path": str(Path(cache_path).resolve()),
                }
            )
        except Exception as exc:
            cache_benchmark.update({"error": str(exc)})

    issues = []
    for index_name in missing_indexes:
        issues.append(
            {
                "issue_type": "missing_index",
                "severity": "high",
                "object_name": index_name,
                "message": f"Recommended ring-system index is missing: {index_name}.",
            }
        )
    for query_name, stats in queries.items():
        if float(stats["median_ms"]) > float(warn_ms):
            issues.append(
                {
                    "issue_type": "slow_query",
                    "severity": "medium",
                    "query_name": query_name,
                    "avg_ms": stats["avg_ms"],
                    "median_ms": stats["median_ms"],
                    "warn_ms": warn_ms,
                    "message": f"Ring query {query_name} median latency is above the warning threshold.",
                }
            )
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(Path(db_path).resolve()),
        "ring_system_count": ring_count,
        "ertl_ring_system_count": ertl_count,
        "ertl_max_source_rank": max_rank,
        "ring_class_sample": ring_class,
        "indexes": indexes,
        "recommended_indexes": sorted(RECOMMENDED_RING_INDEXES),
        "missing_recommended_indexes": missing_indexes,
        "query_timings": queries,
        "ring_recommender_cache": cache_benchmark,
        "issue_count": len(issues),
        "issues": issues,
        "maintenance_applied": bool(apply_maintenance),
    }


def write_ring_db_performance_report(report: dict, json_path: str | Path, csv_path: str | Path | None = None) -> None:
    path = Path(json_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    rows = []
    for name, stats in (report.get("query_timings") or {}).items():
        rows.append({"query_name": name, **stats})
    csv_file = Path(csv_path)
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["query_name", "row_count", "avg_ms", "median_ms", "min_ms", "max_ms"]
    with csv_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
