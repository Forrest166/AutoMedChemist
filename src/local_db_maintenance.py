from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .local_db_health import build_local_db_health_report
from .ring_performance import RECOMMENDED_RING_INDEXES, build_ring_db_performance_report


DEFAULT_DB_MAINTENANCE_JSON = Path("data/releases/local_db_maintenance_report.json")
DEFAULT_DB_MAINTENANCE_CSV = Path("data/releases/local_db_maintenance_report.csv")
DEFAULT_DB_MAINTENANCE_TREND_JSON = Path("data/releases/local_db_maintenance_trend_history.json")
DEFAULT_DB_MAINTENANCE_TREND_CSV = Path("data/releases/local_db_maintenance_trend_history.csv")


def _resolve(root: Path, path: str | Path) -> Path:
    item = Path(path)
    return item if item.is_absolute() else root / item


def _status_level(value: object) -> str:
    status = str(value or "").strip().lower()
    if status in {"healthy", "ready", "pass", "ok"}:
        return "pass"
    if status in {"missing", "error", "fail", "blocked"}:
        return "fail"
    return "warn"


def _latency_rows(performance: dict, warn_ms: float) -> list[dict[str, Any]]:
    rows = []
    for query_name, stats in (performance.get("query_timings") or {}).items():
        median = stats.get("median_ms")
        try:
            median_value = float(median)
        except (TypeError, ValueError):
            median_value = 0.0
        rows.append(
            {
                "row_type": "latency_budget",
                "name": query_name,
                "status": "pass" if median_value <= warn_ms else "warn",
                "metric": "median_ms",
                "value": median,
                "budget": warn_ms,
                "details": f"avg={stats.get('avg_ms')}; rows={stats.get('row_count')}",
            }
        )
    return rows


def _index_rows(performance: dict) -> list[dict[str, Any]]:
    existing = set(performance.get("indexes") or [])
    rows = []
    for name, sql in RECOMMENDED_RING_INDEXES.items():
        present = name in existing
        rows.append(
            {
                "row_type": "recommended_index",
                "name": name,
                "status": "pass" if present else "warn",
                "metric": "present",
                "value": present,
                "budget": True,
                "details": sql,
            }
        )
    return rows


def _cache_rows(performance: dict) -> list[dict[str, Any]]:
    cache = performance.get("ring_recommender_cache") or {}
    if not cache.get("enabled"):
        return [
            {
                "row_type": "cache_warm_status",
                "name": "ring_recommender_cache",
                "status": "warn",
                "metric": "enabled",
                "value": False,
                "budget": True,
                "details": "cache benchmark was not enabled",
            }
        ]
    return [
        {
            "row_type": "cache_warm_status",
            "name": "ring_recommender_cache",
            "status": "pass" if cache.get("warm_cache_hit") else "warn",
            "metric": "warm_cache_hit",
            "value": bool(cache.get("warm_cache_hit")),
            "budget": True,
            "details": f"cold_hit={cache.get('cold_cache_hit')}; elapsed_ms={cache.get('cold_query_elapsed_ms')}; returned={cache.get('returned_count')}; path={cache.get('cache_path')}",
        }
    ]


def build_local_db_maintenance_report(
    *,
    root: str | Path = ".",
    db_path: str | Path = "data/localmedchem.sqlite",
    cache_path: str | Path = "data/substituents/ring_recommendation_cache.json",
    apply_maintenance: bool = False,
    warn_ms: float = 250.0,
    repetitions: int = 1,
) -> dict[str, Any]:
    root_path = Path(root)
    db_file = _resolve(root_path, db_path)
    cache_file = _resolve(root_path, cache_path)
    health = build_local_db_health_report(root=root_path, db_path=db_file)
    rows: list[dict[str, Any]] = [
        {
            "row_type": "db_health",
            "name": "localmedchem_sqlite",
            "status": "pass" if health.get("status") == "healthy" else _status_level(health.get("status")),
            "metric": "status",
            "value": health.get("status"),
            "budget": "healthy",
            "details": f"size_bytes={health.get('size_bytes')}; ring_indexes={health.get('ring_index_count')}",
        }
    ]
    performance: dict[str, Any] = {}
    if db_file.exists() and health.get("connectable", True):
        try:
            performance = build_ring_db_performance_report(
                db_path=db_file,
                apply_maintenance=apply_maintenance,
                repetitions=repetitions,
                warn_ms=warn_ms,
                cache_path=cache_file,
            )
            rows.extend(_index_rows(performance))
            rows.extend(_latency_rows(performance, warn_ms))
            rows.extend(_cache_rows(performance))
        except Exception as exc:
            rows.append(
                {
                    "row_type": "performance_probe",
                    "name": "ring_performance",
                    "status": "warn",
                    "metric": "error",
                    "value": str(exc),
                    "budget": "",
                    "details": "Performance probe failed; health report remains available.",
                }
            )
            performance = {"error": str(exc)}
    fail_count = sum(1 for row in rows if row.get("status") == "fail")
    warn_count = sum(1 for row in rows if row.get("status") == "warn")
    status = "fail" if fail_count else "attention_required" if warn_count else "ready"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "db_path": str(db_file),
        "cache_path": str(cache_file),
        "apply_maintenance": bool(apply_maintenance),
        "warn_ms": warn_ms,
        "row_count": len(rows),
        "fail_count": fail_count,
        "warn_count": warn_count,
        "health": health,
        "performance": performance,
        "rows": rows,
        "recommended_next_actions": [
            "Run with --apply-maintenance only when you want to create recommended local indexes and run SQLite optimize.",
            "Keep latency budgets visible before running large ring-library recommendation jobs.",
            "Use cache warm status to decide whether to refresh local recommendation cache before user-facing review.",
        ],
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _max_latency_ms(report: dict) -> float:
    values = []
    for row in report.get("rows") or []:
        if row.get("row_type") != "latency_budget":
            continue
        try:
            values.append(float(row.get("value") or 0))
        except (TypeError, ValueError):
            continue
    return max(values or [0.0])


def _count_ertl_latency_ms(report: dict) -> float:
    timings = (report.get("performance") or {}).get("query_timings") or {}
    try:
        return float((timings.get("count_ertl") or {}).get("median_ms") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _trend_row(report: dict) -> dict[str, Any]:
    health = report.get("health") or {}
    performance = report.get("performance") or {}
    cache = performance.get("ring_recommender_cache") or {}
    return {
        "created_at": report.get("created_at") or datetime.now(timezone.utc).isoformat(),
        "status": report.get("status"),
        "warn_count": report.get("warn_count"),
        "fail_count": report.get("fail_count"),
        "row_count": report.get("row_count"),
        "db_size_bytes": health.get("size_bytes"),
        "ring_rows": (health.get("table_rows") or {}).get("ring_system"),
        "ring_index_count": health.get("ring_index_count"),
        "missing_index_count": len(performance.get("missing_recommended_indexes") or []),
        "max_latency_ms": round(_max_latency_ms(report), 4),
        "count_ertl_median_ms": round(_count_ertl_latency_ms(report), 4),
        "cache_enabled": bool(cache.get("enabled")),
        "warm_cache_hit": bool(cache.get("warm_cache_hit")),
        "cold_query_elapsed_ms": cache.get("cold_query_elapsed_ms"),
        "apply_maintenance": bool(report.get("apply_maintenance")),
    }


def update_local_db_maintenance_trend(
    report: dict,
    *,
    trend_json_path: str | Path = DEFAULT_DB_MAINTENANCE_TREND_JSON,
    trend_csv_path: str | Path | None = DEFAULT_DB_MAINTENANCE_TREND_CSV,
    max_rows: int = 120,
) -> dict[str, Any]:
    trend_file = Path(trend_json_path)
    existing = _read_json(trend_file)
    rows = list(existing.get("rows") or [])
    rows.append(_trend_row(report))
    rows = rows[-max(1, int(max_rows)) :]
    latest = rows[-1] if rows else {}
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "tracking",
        "row_count": len(rows),
        "latest": latest,
        "rows": rows,
        "recommended_next_actions": [
            "Review repeated latency-budget warnings before expanding large local ring queries.",
            "Use warm-cache trend to decide whether the local recommender cache needs a refresh before user-facing review.",
            "Keep maintenance application explicit; trend tracking does not create indexes by itself.",
        ],
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }
    trend_file.parent.mkdir(parents=True, exist_ok=True)
    trend_file.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    if trend_csv_path:
        csv_file = Path(trend_csv_path)
        csv_file.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "created_at",
            "status",
            "warn_count",
            "fail_count",
            "row_count",
            "db_size_bytes",
            "ring_rows",
            "ring_index_count",
            "missing_index_count",
            "max_latency_ms",
            "count_ertl_median_ms",
            "cache_enabled",
            "warm_cache_hit",
            "cold_query_elapsed_ms",
            "apply_maintenance",
        ]
        with csv_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fields})
    return payload


def write_local_db_maintenance_report(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_DB_MAINTENANCE_JSON,
    csv_path: str | Path | None = DEFAULT_DB_MAINTENANCE_CSV,
    trend_json_path: str | Path | None = None,
    trend_csv_path: str | Path | None = None,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if not csv_path:
        return
    fields = ["row_type", "name", "status", "metric", "value", "budget", "details"]
    csv_file = Path(csv_path)
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    with csv_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in report.get("rows") or []:
            writer.writerow({field: row.get(field, "") for field in fields})
    if trend_json_path:
        update_local_db_maintenance_trend(report, trend_json_path=trend_json_path, trend_csv_path=trend_csv_path)
