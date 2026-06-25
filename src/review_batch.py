from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from .library import load_yaml_records
from .review import REVIEW_STATUSES, default_review_block, infer_avoid_contexts, infer_use_cases, update_substituent_review


DEFAULT_SEED_PATHS = [
    Path("data/seeds/core_substituent_seed.yaml"),
    Path("data/seeds/pubchem_expansion_seed.yaml"),
]

REVIEW_BATCH_FIELDS = [
    "apply",
    "seed_path",
    "substituent_id",
    "name",
    "current_status",
    "suggested_status",
    "default_enabled",
    "common_medchem",
    "mvp",
    "default_rank",
    "use_cases",
    "avoid_contexts",
    "review_note",
    "suggestion_reason",
]


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _risk_tags(record: dict) -> set[str]:
    return {str(tag) for tag in ((record.get("risk") or {}).get("risk_tags") or []) if tag}


def suggest_review_decision(record: dict) -> dict:
    risk_tags = _risk_tags(record)
    priority = record.get("priority") or {}
    reasons = []
    status = "approved"
    default_enabled = bool((record.get("risk") or {}).get("default_enabled", True))

    hard_block = {"reactive_alert", "toxicophore"}
    revision_flags = {"possible_strong_basicity", "chelation_risk", "advanced_only"}
    caution_flags = {"permeability_risk", "possible_lipophilicity_increase", "possible_soft_spot", "possible_metabolic_liability", "ionizable_group"}
    if risk_tags.intersection(hard_block):
        status = "blocked"
        default_enabled = False
        reasons.append("hard structural risk alert")
    elif risk_tags.intersection(revision_flags):
        status = "needs_revision"
        default_enabled = False if "advanced_only" in risk_tags else default_enabled
        reasons.append("requires project-context review before default use")
    elif risk_tags.intersection(caution_flags):
        status = "approved_with_caution"
        reasons.append("usable with risk/context guardrails")
    else:
        reasons.append("low broad-risk first-pass medchem record")

    if priority.get("common_medchem") or priority.get("mvp"):
        reasons.append("already prioritized in seed library")
    return {
        "suggested_status": status,
        "default_enabled": default_enabled,
        "common_medchem": bool(priority.get("common_medchem", False)),
        "mvp": bool(priority.get("mvp", True)),
        "default_rank": int(priority.get("default_rank") or 999),
        "use_cases": infer_use_cases(record),
        "avoid_contexts": infer_avoid_contexts(record),
        "suggestion_reason": "; ".join(dict.fromkeys(reasons)),
    }


def build_review_backlog_batch(
    seed_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
    *,
    limit: int | None = None,
) -> list[dict]:
    explicit_paths = seed_paths is not None
    paths = [Path(path) for path in (seed_paths or DEFAULT_SEED_PATHS)]
    rows = []
    audit_rows = []
    for path in paths:
        if not path.exists():
            continue
        for record in load_yaml_records(path):
            review = default_review_block(record)
            if review.get("status") != "needs_medchem_review":
                if explicit_paths:
                    suggestion = suggest_review_decision(record)
                    suggestion["suggested_status"] = review.get("status") or suggestion["suggested_status"]
                    audit_rows.append(
                        {
                            "apply": "true",
                            "seed_path": str(path),
                            "substituent_id": record.get("substituent_id"),
                            "name": record.get("name"),
                            "current_status": review.get("status"),
                            "suggested_status": suggestion["suggested_status"],
                            "default_enabled": _bool_text(suggestion["default_enabled"]),
                            "common_medchem": _bool_text(suggestion["common_medchem"]),
                            "mvp": _bool_text(suggestion["mvp"]),
                            "default_rank": suggestion["default_rank"],
                            "use_cases": "; ".join(suggestion["use_cases"]),
                            "avoid_contexts": "; ".join(suggestion["avoid_contexts"]),
                            "review_note": "Batch periodic review: status retained.",
                            "suggestion_reason": "already reviewed; included for explicit audit batch",
                        }
                    )
                continue
            suggestion = suggest_review_decision(record)
            rows.append(
                {
                    "apply": "true",
                    "seed_path": str(path),
                    "substituent_id": record.get("substituent_id"),
                    "name": record.get("name"),
                    "current_status": review.get("status"),
                    "suggested_status": suggestion["suggested_status"],
                    "default_enabled": _bool_text(suggestion["default_enabled"]),
                    "common_medchem": _bool_text(suggestion["common_medchem"]),
                    "mvp": _bool_text(suggestion["mvp"]),
                    "default_rank": suggestion["default_rank"],
                    "use_cases": "; ".join(suggestion["use_cases"]),
                    "avoid_contexts": "; ".join(suggestion["avoid_contexts"]),
                    "review_note": f"Batch first-pass review: {suggestion['suggestion_reason']}.",
                    "suggestion_reason": suggestion["suggestion_reason"],
                }
            )
            if limit is not None and len(rows) >= int(limit):
                return rows
    if not rows and explicit_paths:
        return audit_rows[: int(limit)] if limit is not None else audit_rows
    return rows


def suggest_revision_decision(record: dict) -> dict:
    suggestion = suggest_review_decision(record)
    risk_tags = _risk_tags(record)
    reasons = []
    status = "approved_with_caution"
    default_enabled = bool((record.get("risk") or {}).get("default_enabled", True))
    avoid_contexts = infer_avoid_contexts(record)

    if "chelation_risk" in risk_tags:
        status = "blocked"
        default_enabled = False
        reasons.append("blocked after second-pass review because chelation risk is a broad default-use concern")
    elif "advanced_only" in risk_tags:
        status = "approved_with_caution"
        default_enabled = False
        avoid_contexts.append("keep disabled by default; use only when an advanced scaffold or vector hypothesis is explicit")
        reasons.append("advanced-only motif retained as opt-in design idea")
    elif "possible_strong_basicity" in risk_tags:
        status = "approved_with_caution"
        avoid_contexts.append("avoid for hERG-sensitive, CNS-like, or lysosomal-trapping-sensitive profiles")
        reasons.append("basic group retained with hERG/CNS/basicity guardrails")
    else:
        reasons.append("second-pass review resolved outstanding context question")

    return {
        **suggestion,
        "suggested_status": status,
        "default_enabled": default_enabled,
        "avoid_contexts": sorted(set(avoid_contexts)),
        "suggestion_reason": "; ".join(dict.fromkeys(reasons)),
    }


def build_revision_review_batch(
    seed_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
    *,
    limit: int | None = None,
) -> list[dict]:
    paths = [Path(path) for path in (seed_paths or DEFAULT_SEED_PATHS)]
    rows = []
    for path in paths:
        if not path.exists():
            continue
        for record in load_yaml_records(path):
            review = default_review_block(record)
            if review.get("status") != "needs_revision":
                continue
            suggestion = suggest_revision_decision(record)
            rows.append(
                {
                    "apply": "true",
                    "seed_path": str(path),
                    "substituent_id": record.get("substituent_id"),
                    "name": record.get("name"),
                    "current_status": review.get("status"),
                    "suggested_status": suggestion["suggested_status"],
                    "default_enabled": _bool_text(suggestion["default_enabled"]),
                    "common_medchem": _bool_text(suggestion["common_medchem"]),
                    "mvp": _bool_text(suggestion["mvp"]),
                    "default_rank": suggestion["default_rank"],
                    "use_cases": "; ".join(suggestion["use_cases"]),
                    "avoid_contexts": "; ".join(suggestion["avoid_contexts"]),
                    "review_note": f"Batch second-pass revision review: {suggestion['suggestion_reason']}.",
                    "suggestion_reason": suggestion["suggestion_reason"],
                }
            )
            if limit is not None and len(rows) >= int(limit):
                return rows
    return rows


def write_review_backlog_batch(rows: list[dict], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_BATCH_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in REVIEW_BATCH_FIELDS})


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "apply"}


def _read_batch(path: str | Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def apply_review_backlog_batch(
    batch_path: str | Path,
    *,
    reviewed_by: str = "batch_review",
    dry_run: bool = False,
    change_summary_prefix: str = "Batch first-pass review",
) -> dict:
    rows = _read_batch(batch_path)
    applied = 0
    skipped = 0
    status_counts: Counter[str] = Counter()
    updated_ids = []
    for row in rows:
        if not _truthy(row.get("apply")):
            skipped += 1
            continue
        status = str(row.get("suggested_status") or "").strip()
        if status not in REVIEW_STATUSES:
            skipped += 1
            continue
        if dry_run:
            applied += 1
            status_counts[status] += 1
            updated_ids.append(row.get("substituent_id"))
            continue
        update_substituent_review(
            row["seed_path"],
            row["substituent_id"],
            status=status,
            reviewed_by=reviewed_by,
            review_note=row.get("review_note") or None,
            use_cases=row.get("use_cases") or None,
            avoid_contexts=row.get("avoid_contexts") or None,
            default_enabled=_truthy(row.get("default_enabled")),
            common_medchem=_truthy(row.get("common_medchem")),
            mvp=_truthy(row.get("mvp")),
            default_rank=int(float(row.get("default_rank") or 999)),
            change_summary=f"{change_summary_prefix} set status to {status}.",
        )
        applied += 1
        status_counts[status] += 1
        updated_ids.append(row.get("substituent_id"))
    return {
        "batch_path": str(Path(batch_path).resolve()),
        "dry_run": dry_run,
        "applied_count": applied,
        "skipped_count": skipped,
        "status_counts": dict(status_counts.most_common()),
        "updated_substituent_ids": updated_ids[:100],
    }
