from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


DEFAULT_PROFILE_PROMOTION_REGISTRY_PATH = Path("data/profiles/profile_promotion_registry.json")
PROFILE_PROMOTION_STATUSES = {"draft", "review_requested", "approved", "active", "rejected", "deferred"}
PENDING_PROFILE_PROMOTION_STATUSES = {"draft", "review_requested", "approved"}


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


def _load_artifact(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        if path.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        else:
            data = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _profile_artifact_id(artifact: dict, path: Path, artifact_type: str) -> str:
    return str(
        artifact.get("profile_id")
        or artifact.get("policy_id")
        or artifact.get("version")
        or artifact.get("id")
        or f"{artifact_type}:{path.stem}"
    )


def load_profile_promotion_registry(path: str | Path = DEFAULT_PROFILE_PROMOTION_REGISTRY_PATH) -> dict:
    registry = _read_json(path)
    records = [dict(row) for row in registry.get("records") or [] if isinstance(row, dict)]
    return {
        "version": registry.get("version") or "profile-promotion-registry-0.1",
        "created_at": registry.get("created_at"),
        "updated_at": registry.get("updated_at"),
        "record_count": len(records),
        "status_counts": dict(Counter(str(row.get("promotion_status") or "unknown") for row in records).most_common()),
        "records": records,
    }


def write_profile_promotion_registry(registry: dict, path: str | Path = DEFAULT_PROFILE_PROMOTION_REGISTRY_PATH) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    records = [dict(row) for row in registry.get("records") or [] if isinstance(row, dict)]
    registry = {
        **registry,
        "version": registry.get("version") or "profile-promotion-registry-0.1",
        "record_count": len(records),
        "status_counts": dict(Counter(str(row.get("promotion_status") or "unknown") for row in records).most_common()),
        "records": records,
    }
    out.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")


def build_profile_promotion_record(
    *,
    artifact_path: str | Path,
    root: str | Path = ".",
    artifact_type: str = "scoring_profile",
    project_name: str | None = "demo_learning",
    promotion_status: str = "review_requested",
    reviewer: str | None = None,
    note: str | None = None,
) -> dict:
    status = str(promotion_status or "review_requested").strip().lower()
    if status not in PROFILE_PROMOTION_STATUSES:
        raise ValueError(f"Unsupported profile promotion status: {promotion_status}")
    root_path = Path(root)
    path = Path(artifact_path)
    artifact = _load_artifact(path)
    artifact_id = _profile_artifact_id(artifact, path, artifact_type)
    gate = _read_json(root_path / "data/projects/demo/closed_loop_promotion_gate.json")
    evidence_pack = _read_json(root_path / "data/projects/demo/project_evidence_pack.json")
    iteration_comparison = _read_json(root_path / "data/projects/demo/iteration_comparison_report.json")
    release_smoke = _read_json(root_path / "data/releases/release_smoke_checklist.json")
    profile_ab_replay = _read_json(root_path / "data/projects/demo/profile_ab_replay_report.json")
    profile_ab_matrix = _read_json(root_path / "data/projects/demo/profile_ab_replay_matrix.json")
    promotion_freeze = _read_json(root_path / "data/projects/demo/profile_promotion_freeze_manifest.json")
    freeze_approvals = _read_json(root_path / "data/projects/demo/profile_promotion_freeze_approvals.json")
    now = datetime.now(timezone.utc).isoformat()
    basis = "|".join([artifact_type, artifact_id, str(project_name or ""), now])
    return {
        "promotion_id": f"PPROM-{hashlib.sha1(basis.encode('utf-8')).hexdigest()[:12].upper()}",
        "created_at": now,
        "updated_at": now,
        "project_name": project_name,
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "artifact_path": str(path.resolve()),
        "artifact_sha256": _sha256(path),
        "promotion_status": status,
        "reviewer": reviewer or "",
        "note": note or "",
        "gate_status": gate.get("promotion_status"),
        "gate_block_count": gate.get("block_count"),
        "gate_review_count": gate.get("review_count"),
        "evidence_pack_status": evidence_pack.get("status"),
        "evidence_pack_outcome_count": evidence_pack.get("outcome_count"),
        "evidence_gap_count": len(evidence_pack.get("evidence_gaps") or []),
        "iteration_base": iteration_comparison.get("base_iteration_id"),
        "iteration_head": iteration_comparison.get("head_iteration_id"),
        "iteration_changed_asset_count": iteration_comparison.get("changed_asset_count"),
        "release_smoke_status": release_smoke.get("status"),
        "profile_ab_replay_status": profile_ab_replay.get("status"),
        "profile_ab_replay_review_status": profile_ab_replay.get("review_status"),
        "profile_ab_replay_changed_top_n_count": profile_ab_replay.get("changed_top_n_count"),
        "profile_ab_replay_max_score_delta": profile_ab_replay.get("max_score_delta"),
        "profile_ab_matrix_status": profile_ab_matrix.get("status"),
        "profile_ab_matrix_scenario_count": profile_ab_matrix.get("scenario_count"),
        "profile_ab_matrix_review_required_count": profile_ab_matrix.get("review_required_count"),
        "promotion_freeze_id": promotion_freeze.get("freeze_id"),
        "promotion_freeze_present_asset_count": promotion_freeze.get("present_asset_count"),
        "promotion_freeze_active_id": freeze_approvals.get("active_freeze_id"),
        "promotion_freeze_release_tag": freeze_approvals.get("latest_release_tag"),
        "artifact_summary": {
            "name": artifact.get("name"),
            "parent_profile_id": artifact.get("parent_profile_id"),
            "score_weights": artifact.get("score_weights") or {},
            "endpoint_family_residual_adjustments": {
                key: value
                for key, value in (artifact.get("endpoint_family_residual_adjustments") or {}).items()
                if key in {"enabled", "version", "applied_count", "review_required", "source_model_created_at"}
            },
        },
        "status_history": [
            {
                "status": status,
                "created_at": now,
                "reviewer": reviewer or "",
                "note": note or "",
            }
        ],
    }


def register_profile_promotion(
    record: dict,
    *,
    registry_path: str | Path = DEFAULT_PROFILE_PROMOTION_REGISTRY_PATH,
) -> dict:
    registry = load_profile_promotion_registry(registry_path)
    now = datetime.now(timezone.utc).isoformat()
    records = [row for row in registry.get("records") or [] if row.get("promotion_id") != record.get("promotion_id")]
    records.append(record)
    records.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    registry = {
        **registry,
        "created_at": registry.get("created_at") or now,
        "updated_at": now,
        "records": records,
    }
    registry["record_count"] = len(records)
    registry["status_counts"] = dict(Counter(str(row.get("promotion_status") or "unknown") for row in records).most_common())
    write_profile_promotion_registry(registry, registry_path)
    return registry


def update_profile_promotion_status(
    promotion_id: str,
    *,
    status: str,
    registry_path: str | Path = DEFAULT_PROFILE_PROMOTION_REGISTRY_PATH,
    reviewer: str | None = None,
    note: str | None = None,
) -> dict:
    normalized = str(status or "").strip().lower()
    if normalized not in PROFILE_PROMOTION_STATUSES:
        raise ValueError(f"Unsupported profile promotion status: {status}")
    registry = load_profile_promotion_registry(registry_path)
    now = datetime.now(timezone.utc).isoformat()
    updated = False
    records = []
    for row in registry.get("records") or []:
        if str(row.get("promotion_id") or "") != str(promotion_id):
            records.append(row)
            continue
        history = list(row.get("status_history") or [])
        history.append({"status": normalized, "created_at": now, "reviewer": reviewer or "", "note": note or ""})
        records.append(
            {
                **row,
                "promotion_status": normalized,
                "updated_at": now,
                "reviewer": reviewer or row.get("reviewer") or "",
                "note": note or row.get("note") or "",
                "status_history": history[-20:],
            }
        )
        updated = True
    if not updated:
        raise ValueError(f"Profile promotion record not found: {promotion_id}")
    registry = {**registry, "updated_at": now, "records": records}
    registry["record_count"] = len(records)
    registry["status_counts"] = dict(Counter(str(row.get("promotion_status") or "unknown") for row in records).most_common())
    write_profile_promotion_registry(registry, registry_path)
    return registry


def profile_promotion_readiness(registry: dict) -> dict:
    records = [dict(row) for row in registry.get("records") or []]
    pending = [row for row in records if str(row.get("promotion_status") or "") in PENDING_PROFILE_PROMOTION_STATUSES]
    active = [row for row in records if str(row.get("promotion_status") or "") == "active"]
    return {
        "record_count": len(records),
        "pending_count": len(pending),
        "active_count": len(active),
        "status_counts": dict(Counter(str(row.get("promotion_status") or "unknown") for row in records).most_common()),
        "latest_pending": pending[0] if pending else {},
        "latest_active": active[0] if active else {},
    }
