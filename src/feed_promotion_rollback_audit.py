from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_AUDIT_JSON = Path("data/substituents/feed_promotion_rollback_audit.json")
DEFAULT_AUDIT_CSV = Path("data/substituents/feed_promotion_rollback_audit.csv")
DEFAULT_AUDIT_MD = Path("docs/feed_promotion_rollback_audit.md")


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolve(root_path: Path, value: object) -> Path:
    path = Path(str(value or ""))
    if not path:
        return path
    if path.is_absolute():
        return path
    return root_path / path


def _sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_feed_promotion_rollback_audit(*, root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    approval = _read_json(root_path / "data/substituents/rgroup_promotion_approval_ledger.json")
    promotion_diff = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_promotion_diff.json")
    staging = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_staging.json")
    manifest_path = _resolve(root_path, staging.get("manifest_path") or "data/replacements/feed_drops/next_rgroup_feed_drop/feed_drop_manifest.yaml")
    diff_by_source = {
        str(row.get("source_dataset") or ""): row
        for row in promotion_diff.get("rows") or []
        if row.get("source_dataset")
    }
    approved_rows = [row for row in approval.get("rows") or [] if row.get("approved_for_promotion") is True]
    rows: list[dict[str, Any]] = []
    for index, approval_row in enumerate(approved_rows, start=1):
        source_dataset = str(approval_row.get("source_dataset") or "")
        diff_row = diff_by_source.get(source_dataset, {})
        source_path = _resolve(root_path, approval_row.get("source_path") or diff_row.get("source_path"))
        target_path = _resolve(root_path, approval_row.get("target_path") or diff_row.get("target_path"))
        source_hash = _sha256(source_path)
        target_hash = _sha256(target_path)
        manifest_hash = _sha256(manifest_path)
        missing = [name for name, value in [("source_file_sha256", source_hash), ("manifest_sha256_before", manifest_hash)] if not value]
        audit_status = "ready" if not missing else "blocked"
        rows.append(
            {
                "audit_id": f"FPRB-{index:04d}",
                "approval_id": approval_row.get("approval_id", ""),
                "replacement_id": approval_row.get("replacement_id", ""),
                "row_sha256": approval_row.get("row_sha256", ""),
                "source_dataset": source_dataset,
                "source_path": str(source_path),
                "target_path": str(target_path),
                "source_file_sha256": source_hash,
                "target_file_sha256_before": target_hash,
                "manifest_path": str(manifest_path),
                "manifest_sha256_before": manifest_hash,
                "candidate_impact_snapshot": approval_row.get("matched_candidate_ids", ""),
                "promotion_approval_decision": approval_row.get("promotion_approval_decision", ""),
                "promotion_allowed": approval.get("promotion_allowed", False),
                "rollback_dry_run_supported": True,
                "rollback_replay_command": "python scripts/build_feed_promotion_rollback_audit.py --dry-run",
                "audit_status": audit_status,
                "missing_checkpoint_fields": ";".join(missing),
                "next_action": (
                    "Rollback checkpoint is ready; retain this hash before any non-dry-run feed copy."
                    if audit_status == "ready"
                    else "Rebuild staging manifest and source file hashes before allowing feed copy."
                ),
            }
        )
    status_counts = Counter(str(row.get("audit_status") or "") for row in rows)
    status = "blocked" if status_counts.get("blocked") else "ready" if rows else "awaiting_rows"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "feed_promotion_rollback_audit",
        "approved_row_count": len(approved_rows),
        "row_count": len(rows),
        "ready_count": status_counts.get("ready", 0),
        "blocked_count": status_counts.get("blocked", 0),
        "promotion_approval_status": approval.get("status", ""),
        "promotion_allowed": approval.get("promotion_allowed", False),
        "staging_manifest_dataset_count": staging.get("source_dataset_count", 0),
        "production_scoring_affected": False,
        "rows": rows,
        "recommended_next_actions": [
            "Keep this audit as the rollback replay checkpoint for the approved positive-control rows.",
            "Only perform a non-dry-run promotion after approval ledger promotion_allowed becomes true.",
        ],
    }


def render_feed_promotion_rollback_audit_markdown(report: dict) -> str:
    lines = [
        "# Feed Promotion Rollback Audit",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Approved rows audited: `{report.get('approved_row_count')}`",
        f"- Promotion allowed: `{report.get('promotion_allowed')}`",
        "",
        "| Audit | Approval | Replacement | Source | Status | Source Hash | Target Hash | Next Action |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("audit_id") or ""),
                    str(row.get("approval_id") or ""),
                    str(row.get("replacement_id") or ""),
                    str(row.get("source_dataset") or ""),
                    str(row.get("audit_status") or ""),
                    str(row.get("source_file_sha256") or "")[:12],
                    str(row.get("target_file_sha256_before") or "")[:12],
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_feed_promotion_rollback_audit(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_AUDIT_JSON,
    csv_path: str | Path | None = DEFAULT_AUDIT_CSV,
    markdown_path: str | Path | None = DEFAULT_AUDIT_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "audit_id",
        "approval_id",
        "replacement_id",
        "row_sha256",
        "source_dataset",
        "source_path",
        "target_path",
        "source_file_sha256",
        "target_file_sha256_before",
        "manifest_path",
        "manifest_sha256_before",
        "candidate_impact_snapshot",
        "promotion_approval_decision",
        "promotion_allowed",
        "rollback_dry_run_supported",
        "rollback_replay_command",
        "audit_status",
        "missing_checkpoint_fields",
        "next_action",
    ]
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
        md_file.write_text(render_feed_promotion_rollback_audit_markdown(report), encoding="utf-8")
