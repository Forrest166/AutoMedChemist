from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RELEASE_GATE_JSON = Path("data/releases/local_db_maintenance_release_gate.json")
DEFAULT_RELEASE_GATE_CSV = Path("data/releases/local_db_maintenance_release_gate.csv")
DEFAULT_RELEASE_GATE_MD = Path("docs/local_db_maintenance_release_gate.md")


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _classify_row(row: dict[str, Any]) -> tuple[str, str]:
    row_type = str(row.get("row_type") or "")
    status = str(row.get("status") or "")
    name = str(row.get("name") or "")
    if status == "fail":
        return "release_stop", "Maintenance row is failing."
    if row_type == "db_health" and status != "pass":
        return "release_stop", "Local database is not healthy."
    if row_type == "recommended_index" and status != "pass":
        return "release_stop", "Recommended index is missing."
    if row_type == "latency_budget" and status == "warn":
        return "watch", f"Latency budget warning for {name}; keep visible but do not block release."
    if row_type == "cache_warm_status" and status == "warn":
        return "watch", "Cache is not warm; user-facing performance may improve after refresh."
    if status == "warn":
        return "watch", "Maintenance warning is tracked as a watch item."
    return "pass", "No release impact."


def build_local_db_maintenance_release_gate(*, root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    maintenance = _read_json(root_path / "data/releases/local_db_maintenance_report.json")
    daily_alert = _read_json(root_path / "data/substituents/daily_maintenance_alert.json")
    rows: list[dict[str, Any]] = []
    for index, source_row in enumerate(maintenance.get("rows") or [], start=1):
        release_class, reason = _classify_row(dict(source_row))
        rows.append(
            {
                "gate_row_id": f"LDBRG-{index:04d}",
                "source": "local_db_maintenance_report",
                "row_type": source_row.get("row_type", ""),
                "name": source_row.get("name", ""),
                "source_status": source_row.get("status", ""),
                "release_class": release_class,
                "metric": source_row.get("metric", ""),
                "value": source_row.get("value", ""),
                "budget": source_row.get("budget", ""),
                "reason": reason,
                "next_action": (
                    "Fix before release."
                    if release_class == "release_stop"
                    else "Keep as operator watch; refresh cache or rerun maintenance if it repeats."
                    if release_class == "watch"
                    else "No action."
                ),
            }
        )
    alert_level = str(daily_alert.get("alert_level") or "missing")
    if alert_level not in {"ok", "missing"}:
        rows.append(
            {
                "gate_row_id": f"LDBRG-{len(rows) + 1:04d}",
                "source": "daily_maintenance_alert",
                "row_type": "daily_alert",
                "name": "daily_maintenance_alert",
                "source_status": alert_level,
                "release_class": "release_stop" if alert_level == "error" else "watch",
                "metric": "alert_level",
                "value": alert_level,
                "budget": "ok",
                "reason": "Daily maintenance alert is not clear.",
                "next_action": "Inspect data/substituents/daily_maintenance_alert.json.",
            }
        )
    release_stop_count = sum(1 for row in rows if row.get("release_class") == "release_stop")
    watch_count = sum(1 for row in rows if row.get("release_class") == "watch")
    status = "blocked" if release_stop_count else "watch" if watch_count else "pass"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "local_db_maintenance_release_gate",
        "row_count": len(rows),
        "release_stop_count": release_stop_count,
        "watch_count": watch_count,
        "pass_count": sum(1 for row in rows if row.get("release_class") == "pass"),
        "daily_alert_level": alert_level,
        "local_db_maintenance_status": maintenance.get("status") or "missing",
        "rows": rows,
        "recommended_next_actions": [
            "Use release_stop_count as the production-smoke release blocker.",
            "Keep watch rows visible in operator trends without turning them into release-stop failures.",
        ],
    }


def render_local_db_maintenance_release_gate_markdown(report: dict) -> str:
    lines = [
        "# Local DB Maintenance Release Gate",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Release stops / watch: `{report.get('release_stop_count')}` / `{report.get('watch_count')}`",
        "",
        "| Source | Row Type | Name | Source Status | Class | Value | Reason |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("source") or ""),
                    str(row.get("row_type") or ""),
                    str(row.get("name") or ""),
                    str(row.get("source_status") or ""),
                    str(row.get("release_class") or ""),
                    str(row.get("value") or ""),
                    str(row.get("reason") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_local_db_maintenance_release_gate(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_RELEASE_GATE_JSON,
    csv_path: str | Path | None = DEFAULT_RELEASE_GATE_CSV,
    markdown_path: str | Path | None = DEFAULT_RELEASE_GATE_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = ["gate_row_id", "source", "row_type", "name", "source_status", "release_class", "metric", "value", "budget", "reason", "next_action"]
    if csv_path:
        csv_file = Path(csv_path)
        csv_file.parent.mkdir(parents=True, exist_ok=True)
        with csv_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in report.get("rows") or []:
                writer.writerow({field: row.get(field, "") for field in fields})
    if markdown_path:
        md_file = Path(markdown_path)
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(render_local_db_maintenance_release_gate_markdown(report), encoding="utf-8")
