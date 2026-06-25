from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .promotion_freeze_approval import (
    DEFAULT_PROMOTION_FREEZE_APPROVAL_PATH,
    DEFAULT_PROMOTION_FREEZE_LATEST_PATH,
    load_promotion_freeze_approvals,
    rollback_profile_promotion_freeze,
)


DEFAULT_PROMOTION_FREEZE_ROLLBACK_DRILL_PATH = Path("data/projects/demo/profile_promotion_freeze_rollback_drill.json")


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check(check_id: str, label: str, status: str, details: str = "") -> dict:
    return {"check_id": check_id, "label": label, "status": status, "details": details}


def _resolve_path(root_path: Path, value: object) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    return path if path.is_absolute() else root_path / path


def build_profile_promotion_freeze_rollback_drill(
    *,
    root: str | Path = ".",
    target_freeze_id: str | None = None,
    reviewer: str = "codex",
    registry_path: str | Path = DEFAULT_PROMOTION_FREEZE_APPROVAL_PATH,
    freeze_manifest_path: str | Path = DEFAULT_PROMOTION_FREEZE_LATEST_PATH,
    promotion_gate_path: str | Path = "data/projects/demo/closed_loop_promotion_gate.json",
    execute: bool = False,
) -> dict:
    root_path = Path(root)
    registry_file = _resolve_path(root_path, registry_path) or Path(registry_path)
    manifest_file = _resolve_path(root_path, freeze_manifest_path) or Path(freeze_manifest_path)
    gate_file = _resolve_path(root_path, promotion_gate_path) or Path(promotion_gate_path)

    approvals = load_promotion_freeze_approvals(registry_file)
    latest_manifest = _read_json(manifest_file)
    gate = _read_json(gate_file)
    active_freeze_id = str(approvals.get("active_freeze_id") or "")
    selected_freeze_id = str(target_freeze_id or active_freeze_id or latest_manifest.get("freeze_id") or "")
    freeze_events = [
        row
        for row in approvals.get("events") or []
        if str(row.get("freeze_id") or "") == selected_freeze_id
    ]
    approved_events = [row for row in freeze_events if str(row.get("approval_status") or "") == "approved"]
    latest_event = approved_events[0] if approved_events else (freeze_events[0] if freeze_events else {})
    package_dir = _resolve_path(root_path, latest_event.get("package_dir") or latest_manifest.get("package_dir"))
    package_manifest = package_dir / "profile_promotion_freeze_manifest.json" if package_dir else None
    package_manifest_payload = _read_json(package_manifest) if package_manifest else {}
    gate_artifacts = {
        str(row.get("artifact_id") or ""): row
        for row in ((gate.get("evidence_snapshot") or {}).get("artifacts") or [])
        if isinstance(row, dict)
    }

    checks = [
        _check(
            "approval_registry_present",
            "Freeze approval registry is available",
            "pass" if approvals.get("event_count") is not None else "block",
            f"registry_path={registry_file}; events={approvals.get('event_count')}",
        ),
        _check(
            "target_freeze_has_history",
            "Target freeze has approval history",
            "pass" if freeze_events else "block",
            f"target_freeze={selected_freeze_id or 'missing'}; event_count={len(freeze_events)}",
        ),
        _check(
            "target_freeze_is_active",
            "Rollback drill targets the active freeze",
            "pass" if selected_freeze_id and selected_freeze_id == active_freeze_id else "review",
            f"target_freeze={selected_freeze_id or 'missing'}; active_freeze={active_freeze_id or 'missing'}",
        ),
        _check(
            "release_tag_present",
            "Current release tag is traceable before rollback",
            "pass" if approvals.get("latest_release_tag") else "block",
            f"latest_release_tag={approvals.get('latest_release_tag') or 'missing'}",
        ),
        _check(
            "freeze_package_manifest_present",
            "Freeze package manifest is present",
            "pass" if package_manifest and package_manifest.exists() else "review",
            f"package_manifest={package_manifest or 'missing'}; sha256={_sha256(package_manifest) if package_manifest else None}",
        ),
        _check(
            "freeze_package_assets_complete",
            "Freeze package has no missing assets",
            "pass" if int((package_manifest_payload or latest_manifest).get("missing_asset_count") or 0) == 0 else "block",
            f"missing_asset_count={(package_manifest_payload or latest_manifest).get('missing_asset_count')}",
        ),
        _check(
            "promotion_gate_snapshot_traceable",
            "Promotion gate snapshot references rollback-relevant governance artifacts",
            "pass"
            if (gate_artifacts.get("profile_promotion_freeze_approvals") or {}).get("exists")
            and (gate_artifacts.get("profile_promotion_freeze_rollback_drill") or {}).get("exists")
            else "review",
            (
                f"gate_status={gate.get('promotion_status') or 'missing'}; "
                f"has_approvals_artifact={bool((gate_artifacts.get('profile_promotion_freeze_approvals') or {}).get('exists'))}; "
                f"has_drill_artifact={bool((gate_artifacts.get('profile_promotion_freeze_rollback_drill') or {}).get('exists'))}"
            ),
        ),
        _check(
            "rollback_action_planned",
            "Rollback action is deterministic and auditable",
            "pass" if selected_freeze_id else "block",
            f"would_set_active_freeze_id={selected_freeze_id or 'missing'}; would_release_tag=ROLLBACK-{selected_freeze_id or 'missing'}",
        ),
    ]
    block_count = sum(1 for row in checks if row["status"] == "block")
    review_count = sum(1 for row in checks if row["status"] == "review")
    status = "blocked" if block_count else "review_required" if review_count else "pass"
    execution_result = {}
    if execute and selected_freeze_id and not block_count:
        execution_result = rollback_profile_promotion_freeze(
            selected_freeze_id,
            reviewer=reviewer,
            note="Executed from rollback drill.",
            registry_path=registry_file,
        )
    now = datetime.now(timezone.utc)
    return {
        "created_at": now.isoformat(),
        "status": status,
        "execution_mode": "execute" if execute else "dry_run",
        "state_mutated": bool(execution_result),
        "reviewer": reviewer,
        "target_freeze_id": selected_freeze_id,
        "active_freeze_id_before": active_freeze_id,
        "latest_release_tag_before": approvals.get("latest_release_tag"),
        "would_set_active_freeze_id": selected_freeze_id,
        "would_release_tag": f"ROLLBACK-{selected_freeze_id}" if selected_freeze_id else "",
        "registry_path": str(registry_file),
        "freeze_manifest_path": str(manifest_file),
        "promotion_gate_path": str(gate_file),
        "package_manifest_path": str(package_manifest) if package_manifest else None,
        "package_manifest_sha256": _sha256(package_manifest) if package_manifest else None,
        "block_count": block_count,
        "review_count": review_count,
        "execution_result": execution_result,
        "checks": checks,
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "recommended_next_actions": [
            "Run an executed rollback only in a controlled release rehearsal or real rollback event.",
            "After any executed rollback, rebuild the promotion gate and freeze package to preserve the trace.",
            "Keep rollback evidence tied to profile freeze/release tags only; procurement/vendor workflows are out of scope.",
        ],
    }


def write_profile_promotion_freeze_rollback_drill(
    report: dict,
    output_path: str | Path = DEFAULT_PROMOTION_FREEZE_ROLLBACK_DRILL_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
