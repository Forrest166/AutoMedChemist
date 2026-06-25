from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_PROMOTION_FREEZE_LATEST_PATH = Path("data/projects/demo/profile_promotion_freeze_manifest.json")
DEFAULT_PROMOTION_FREEZE_APPROVAL_PATH = Path("data/projects/demo/profile_promotion_freeze_approvals.json")
DEFAULT_PROFILE_PROMOTION_RELEASE_TAGS_PATH = Path("data/projects/demo/profile_promotion_release_tags.json")

FREEZE_APPROVAL_STATUSES = {"draft", "approved", "rejected", "deferred", "rolled_back"}


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: str | Path, data: dict) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _event_id(*parts: object) -> str:
    basis = "|".join(str(part or "") for part in parts)
    return f"PFAPP-{hashlib.sha1(basis.encode('utf-8')).hexdigest()[:12].upper()}"


def load_promotion_freeze_approvals(path: str | Path = DEFAULT_PROMOTION_FREEZE_APPROVAL_PATH) -> dict:
    registry = _read_json(path)
    events = [dict(row) for row in registry.get("events") or [] if isinstance(row, dict)]
    return {
        "version": registry.get("version") or "profile-promotion-freeze-approvals-0.1",
        "created_at": registry.get("created_at"),
        "updated_at": registry.get("updated_at"),
        "active_freeze_id": registry.get("active_freeze_id"),
        "latest_release_tag": registry.get("latest_release_tag"),
        "event_count": len(events),
        "status_counts": dict(Counter(str(row.get("approval_status") or "unknown") for row in events).most_common()),
        "events": events,
    }


def _load_release_tags(path: str | Path = DEFAULT_PROFILE_PROMOTION_RELEASE_TAGS_PATH) -> dict:
    payload = _read_json(path)
    tags = [dict(row) for row in payload.get("tags") or [] if isinstance(row, dict)]
    return {
        "version": payload.get("version") or "profile-promotion-release-tags-0.1",
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
        "tag_count": len(tags),
        "tags": tags,
    }


def _release_tag(project_name: str | None, freeze_id: str, now: datetime) -> str:
    safe_project = str(project_name or "project").replace(" ", "_")
    short = hashlib.sha1(str(freeze_id).encode("utf-8")).hexdigest()[:8].upper()
    return f"PROFILE-{safe_project}-{now.strftime('%Y%m%dT%H%M%SZ')}-{short}"


def review_profile_promotion_freeze(
    *,
    freeze_manifest_path: str | Path = DEFAULT_PROMOTION_FREEZE_LATEST_PATH,
    approval_status: str = "approved",
    reviewer: str = "codex",
    note: str | None = None,
    release_tag: str | None = None,
    registry_path: str | Path = DEFAULT_PROMOTION_FREEZE_APPROVAL_PATH,
    release_tags_path: str | Path = DEFAULT_PROFILE_PROMOTION_RELEASE_TAGS_PATH,
) -> dict:
    normalized = str(approval_status or "").strip().lower()
    if normalized not in FREEZE_APPROVAL_STATUSES - {"rolled_back"}:
        raise ValueError(f"Unsupported freeze approval status: {approval_status}")
    manifest = _read_json(freeze_manifest_path)
    if not manifest:
        raise ValueError(f"Freeze manifest not found or invalid: {freeze_manifest_path}")
    if normalized == "approved" and int(manifest.get("missing_asset_count") or 0):
        raise ValueError("Cannot approve a freeze with missing assets.")
    now = datetime.now(timezone.utc)
    tag = release_tag or (_release_tag(manifest.get("project_name"), manifest.get("freeze_id"), now) if normalized == "approved" else "")
    registry = load_promotion_freeze_approvals(registry_path)
    event = {
        "approval_id": _event_id(manifest.get("freeze_id"), normalized, reviewer, now.isoformat()),
        "approval_status": normalized,
        "created_at": now.isoformat(),
        "reviewer": reviewer,
        "note": note or "",
        "freeze_id": manifest.get("freeze_id"),
        "freeze_manifest_path": str(freeze_manifest_path),
        "package_dir": manifest.get("package_dir"),
        "project_name": manifest.get("project_name"),
        "present_asset_count": manifest.get("present_asset_count"),
        "missing_asset_count": manifest.get("missing_asset_count"),
        "release_tag": tag,
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
    }
    events = [event, *registry.get("events", [])]
    updated = {
        **registry,
        "created_at": registry.get("created_at") or now.isoformat(),
        "updated_at": now.isoformat(),
        "active_freeze_id": manifest.get("freeze_id") if normalized == "approved" else registry.get("active_freeze_id"),
        "latest_release_tag": tag or registry.get("latest_release_tag"),
        "events": events[:100],
    }
    updated["event_count"] = len(updated["events"])
    updated["status_counts"] = dict(Counter(str(row.get("approval_status") or "unknown") for row in updated["events"]).most_common())
    _write_json(registry_path, updated)
    tags = _load_release_tags(release_tags_path)
    if normalized == "approved":
        tag_row = {
            "release_tag": tag,
            "freeze_id": manifest.get("freeze_id"),
            "created_at": now.isoformat(),
            "reviewer": reviewer,
            "note": note or "",
            "manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode("utf-8")).hexdigest(),
            "asset_count": manifest.get("asset_count"),
            "present_asset_count": manifest.get("present_asset_count"),
        }
        tags = {
            **tags,
            "created_at": tags.get("created_at") or now.isoformat(),
            "updated_at": now.isoformat(),
            "tags": [tag_row, *tags.get("tags", [])][:100],
        }
        tags["tag_count"] = len(tags["tags"])
    else:
        tags = {
            **tags,
            "created_at": tags.get("created_at") or now.isoformat(),
            "updated_at": now.isoformat(),
            "tags": tags.get("tags", []),
        }
        tags["tag_count"] = len(tags["tags"])
    _write_json(release_tags_path, tags)
    return {"created_at": now.isoformat(), "status": normalized, "event": event, "registry": updated}


def rollback_profile_promotion_freeze(
    freeze_id: str,
    *,
    reviewer: str = "codex",
    note: str | None = None,
    registry_path: str | Path = DEFAULT_PROMOTION_FREEZE_APPROVAL_PATH,
) -> dict:
    registry = load_promotion_freeze_approvals(registry_path)
    known = [row for row in registry.get("events") or [] if str(row.get("freeze_id") or "") == str(freeze_id)]
    if not known:
        raise ValueError(f"Freeze id has no approval history: {freeze_id}")
    now = datetime.now(timezone.utc)
    event = {
        "approval_id": _event_id(freeze_id, "rolled_back", reviewer, now.isoformat()),
        "approval_status": "rolled_back",
        "created_at": now.isoformat(),
        "reviewer": reviewer,
        "note": note or "",
        "freeze_id": freeze_id,
        "release_tag": f"ROLLBACK-{freeze_id}",
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
    }
    events = [event, *registry.get("events", [])]
    updated = {
        **registry,
        "updated_at": now.isoformat(),
        "active_freeze_id": freeze_id,
        "latest_release_tag": event["release_tag"],
        "events": events[:100],
    }
    updated["event_count"] = len(updated["events"])
    updated["status_counts"] = dict(Counter(str(row.get("approval_status") or "unknown") for row in updated["events"]).most_common())
    _write_json(registry_path, updated)
    return {"created_at": now.isoformat(), "status": "rolled_back", "event": event, "registry": updated}
