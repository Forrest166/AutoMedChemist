from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


DEFAULT_SOURCE_EXPANSION_GOVERNANCE_JSON = Path("data/substituents/source_expansion_governance.json")
DEFAULT_SOURCE_EXPANSION_GOVERNANCE_CSV = Path("data/substituents/source_expansion_governance.csv")
DEFAULT_SOURCE_EXPANSION_GOVERNANCE_MD = Path("docs/source_expansion_governance.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_yaml(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _int(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _row(gate_id: str, label: str, status: str, details: str, *, artifact_path: str | Path = "", next_action: str = "") -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "label": label,
        "status": status,
        "details": details,
        "artifact_path": str(artifact_path or ""),
        "next_action": next_action,
    }


def build_source_expansion_governance(*, root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    acceptance = _read_yaml(root_path / "data/rules/source_acceptance_manifest.yaml")
    metadata = _read_json(root_path / "data/substituents/rgroup_feed_metadata_report.json")
    feed_audit = _read_json(root_path / "data/substituents/feed_absorption_audit.json")
    feed_diff = _read_json(root_path / "data/substituents/feed_absorption_diff_navigator.json")
    foundation = _read_json(root_path / "data/substituents/data_foundation_report.json")
    ring_library = root_path / "data/rings/ring_system_library.yaml"
    rgroup_library = root_path / "data/replacements/rgroup_replacements.yaml"
    literature_library = root_path / "data/substituents/literature_substituent_library.yaml"
    allowed_sources = acceptance.get("sources") or acceptance.get("allowed_sources") or []
    totals = foundation.get("totals") or {}
    missing_assets = _int(totals.get("missing_asset_count"))
    warning_count = _int(totals.get("warning_count"))
    feed_blockers = _int(feed_audit.get("blocker_count")) + _int(feed_diff.get("blocker_count"))
    rows = [
        _row(
            "source_acceptance_manifest",
            "Source acceptance manifest",
            "ready" if acceptance else "missing",
            f"sources={len(allowed_sources) if isinstance(allowed_sources, list) else len(allowed_sources or {})}",
            artifact_path=root_path / "data/rules/source_acceptance_manifest.yaml",
            next_action="Register every new source family before row-level promotion.",
        ),
        _row(
            "rgroup_feed_manifest",
            "R-group feed manifest",
            "ready" if metadata and _int(metadata.get("allowlist_issue_count")) == 0 else "blocked",
            f"feeds={metadata.get('feed_count')}; rows={metadata.get('row_count')}; allowlist={metadata.get('allowlist_issue_count')}; freshness={metadata.get('freshness_issue_count')}",
            artifact_path=root_path / "data/substituents/rgroup_feed_metadata_report.json",
            next_action="Fix allowlist or freshness issues before expanding R-group rows.",
        ),
        _row(
            "feed_absorption_governance",
            "Feed absorption governance",
            "ready" if feed_audit.get("status") in {"ready", "ready_with_open_staging"} and feed_blockers == 0 else "blocked",
            f"audit={feed_audit.get('status')}; diff={feed_diff.get('status')}; blockers={feed_blockers}; warnings={_int(feed_audit.get('warning_count')) + _int(feed_diff.get('warning_count'))}",
            artifact_path=root_path / "data/substituents/feed_absorption_audit.json",
            next_action="Use audit and diff navigator before new feed rows influence scoring.",
        ),
        _row(
            "data_foundation",
            "Data foundation",
            "ready" if foundation and missing_assets == 0 and warning_count == 0 else "watch",
            f"assets={totals.get('asset_count')}; missing={missing_assets}; warnings={warning_count}",
            artifact_path=root_path / "data/substituents/data_foundation_report.json",
            next_action="Add every new governed artifact to the data foundation inventory.",
        ),
        _row(
            "ring_data_scope",
            "Ring data scope",
            "ready" if ring_library.exists() else "missing",
            f"path={ring_library}; exists={ring_library.exists()}",
            artifact_path=ring_library,
            next_action="Expand ring systems only through curated library/import gates.",
        ),
        _row(
            "rgroup_data_scope",
            "R-group data scope",
            "ready" if rgroup_library.exists() else "missing",
            f"path={rgroup_library}; exists={rgroup_library.exists()}",
            artifact_path=rgroup_library,
            next_action="Expand R-group replacements only through normalized, reviewed feeds.",
        ),
        _row(
            "literature_substituent_scope",
            "Literature substituent scope",
            "ready" if literature_library.exists() else "missing",
            f"path={literature_library}; exists={literature_library.exists()}",
            artifact_path=literature_library,
            next_action="Expand literature substituents only with provenance and review fields.",
        ),
    ]
    blocked = [row for row in rows if row["status"] in {"blocked", "missing"}]
    status = "blocked" if blocked else "ready"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "source_expansion_governance",
        "row_count": len(rows),
        "blocked_gate_count": len(blocked),
        "allowed_expansion_scopes": ["ring_system", "rgroup_replacement", "literature_substituent", "substituent"],
        "ungated_expansion_allowed": False,
        "rows": rows,
        "recommended_next_actions": [
            "Expand the data foundation only through manifest-backed, provenance-complete, locally reviewed source rows.",
            "Keep procurement, supplier purchase, and automatic real experiment feedback import out of source expansion workflows.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_source_expansion_governance_markdown(report: dict) -> str:
    lines = [
        "# Source Expansion Governance",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Ungated expansion allowed: `{report.get('ungated_expansion_allowed')}`",
        "",
        "| Gate | Status | Details | Next Action |",
        "| --- | --- | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("gate_id") or ""),
                    str(row.get("status") or ""),
                    str(row.get("details") or "").replace("|", "/"),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_source_expansion_governance(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_SOURCE_EXPANSION_GOVERNANCE_JSON,
    csv_path: str | Path | None = DEFAULT_SOURCE_EXPANSION_GOVERNANCE_CSV,
    markdown_path: str | Path | None = DEFAULT_SOURCE_EXPANSION_GOVERNANCE_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = ["gate_id", "label", "status", "details", "artifact_path", "next_action"]
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
        md_file.write_text(render_source_expansion_governance_markdown(report), encoding="utf-8")
