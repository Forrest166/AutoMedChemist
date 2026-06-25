from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import yaml

DEFAULT_REVIEW_STATUS = "needs_medchem_review"
REVIEW_STATUSES = [
    "needs_medchem_review",
    "approved",
    "approved_with_caution",
    "needs_revision",
    "blocked",
    "rejected",
    "deprecated",
]


def ensure_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        if ";" in value:
            return [part.strip() for part in value.split(";") if part.strip()]
        return [value] if value else []
    return [value]


def infer_use_cases(record: dict) -> list[str]:
    tags = set(ensure_list(record.get("direction_tags")))
    classes = set(ensure_list(record.get("class")))
    use_cases: list[str] = []

    if "small_scan" in tags:
        use_cases.append("first-pass small substituent scan")
    if "increase_polarity" in tags:
        use_cases.append("increase polarity or hydrogen-bonding capacity")
    if "reduce_lipophilicity" in tags:
        use_cases.append("reduce lipophilicity while preserving local SAR")
    if "metabolism_blocking" in tags:
        use_cases.append("block or probe local metabolic soft spots")
    if "electronics_scan" in tags:
        use_cases.append("probe local electronic effects")
    if "heteroaryl_scan" in tags or "heteroaryl" in classes:
        use_cases.append("heteroaryl replacement or vector scan")
    if "improve_solubility" in tags or "solubilizing_group" in classes:
        use_cases.append("improve solubility or tune ionization")
    if "increase_size" in tags:
        use_cases.append("fill local hydrophobic or steric space")
    if not use_cases:
        use_cases.append("context-dependent local substituent exploration")
    return sorted(set(use_cases))


def infer_avoid_contexts(record: dict) -> list[str]:
    risk_tags = set(ensure_list(record.get("risk", {}).get("risk_tags")))
    classes = set(ensure_list(record.get("class")))
    avoid: list[str] = []

    if "possible_lipophilicity_increase" in risk_tags:
        avoid.append("avoid when logP or clearance risk is already high")
    if "permeability_risk" in risk_tags:
        avoid.append("avoid when passive permeability is the primary constraint")
    if "possible_strong_basicity" in risk_tags:
        avoid.append("avoid when basicity, hERG, or lysosomal trapping risk is a concern")
    if "reactive_alert" in risk_tags:
        avoid.append("avoid default use without explicit medicinal chemistry review")
    if "possible_soft_spot" in risk_tags:
        avoid.append("avoid when adding an obvious metabolic soft spot is undesirable")
    if "acid" in classes:
        avoid.append("avoid for CNS-like profiles unless acidic exposure is intentional")
    if not avoid:
        avoid.append("no broad exclusion; review in project context")
    return sorted(set(avoid))


def default_review_block(record: dict) -> dict:
    existing = dict(record.get("review") or {})
    existing.setdefault("status", DEFAULT_REVIEW_STATUS)
    existing.setdefault("reviewed_by", None)
    existing.setdefault("reviewed_at", None)
    existing.setdefault("review_notes", [])
    existing.setdefault("use_cases", infer_use_cases(record))
    existing.setdefault("avoid_contexts", infer_avoid_contexts(record))
    return existing


def default_version_history(record: dict, build_date: str | None = None) -> list[dict]:
    existing = record.get("version_history")
    if isinstance(existing, list) and existing:
        return existing
    source = record.get("source", {})
    return [
        {
            "version": source.get("version", "0.1"),
            "date": build_date or date.today().isoformat(),
            "change_type": "initial_curation",
            "summary": "Initial curated MVP substituent entry with RDKit descriptor enrichment.",
        }
    ]


def review_queue_row(record: dict) -> dict:
    review = record.get("review", {})
    return {
        "substituent_id": record.get("substituent_id"),
        "name": record.get("name"),
        "short_name": record.get("short_name"),
        "smiles": record.get("smiles"),
        "review_status": review.get("status"),
        "use_cases": ";".join(ensure_list(review.get("use_cases"))),
        "avoid_contexts": ";".join(ensure_list(review.get("avoid_contexts"))),
        "risk_tags": ";".join(ensure_list(record.get("risk", {}).get("risk_tags"))),
        "default_rank": record.get("priority", {}).get("default_rank"),
        "reviewed_by": review.get("reviewed_by") or "",
        "reviewed_at": review.get("reviewed_at") or "",
        "review_notes": ";".join(ensure_list(review.get("review_notes"))),
    }


def _load_library_document(path: str | Path) -> tuple[dict, list[dict]]:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(data, dict):
        records = list(data.get("substituents", []))
        return data, records
    if isinstance(data, list):
        return {"substituents": data}, data
    raise ValueError(f"Unsupported library shape: {path}")


def _dump_library_document(path: str | Path, data: dict) -> None:
    path = Path(path)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=False), encoding="utf-8")


def parse_semicolon_text(text: str | list | tuple | None) -> list[str]:
    if isinstance(text, (list, tuple)):
        return [str(item).strip() for item in text if str(item).strip()]
    if not text:
        return []
    return [part.strip() for part in str(text).split(";") if part.strip()]


def update_substituent_review(
    library_path: str | Path,
    substituent_id: str,
    *,
    status: str,
    reviewed_by: str | None = None,
    review_note: str | None = None,
    use_cases: list[str] | str | None = None,
    avoid_contexts: list[str] | str | None = None,
    default_enabled: bool | None = None,
    common_medchem: bool | None = None,
    mvp: bool | None = None,
    default_rank: int | None = None,
    change_summary: str | None = None,
) -> dict:
    if status not in REVIEW_STATUSES:
        raise ValueError(f"Unsupported review status: {status}")

    data, records = _load_library_document(library_path)
    record = next((item for item in records if item.get("substituent_id") == substituent_id), None)
    if record is None:
        raise KeyError(f"Substituent not found: {substituent_id}")

    now = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()

    review = default_review_block(record)
    review["status"] = status
    review["reviewed_by"] = reviewed_by or review.get("reviewed_by")
    review["reviewed_at"] = now
    if use_cases is not None:
        review["use_cases"] = parse_semicolon_text(use_cases)
    if avoid_contexts is not None:
        review["avoid_contexts"] = parse_semicolon_text(avoid_contexts)
    notes = ensure_list(review.get("review_notes"))
    if review_note:
        notes.append(f"{today}: {review_note}")
    review["review_notes"] = notes
    record["review"] = review

    record.setdefault("risk", {})
    if default_enabled is not None:
        record["risk"]["default_enabled"] = bool(default_enabled)

    record.setdefault("priority", {})
    if common_medchem is not None:
        record["priority"]["common_medchem"] = bool(common_medchem)
    if mvp is not None:
        record["priority"]["mvp"] = bool(mvp)
    if default_rank is not None:
        record["priority"]["default_rank"] = int(default_rank)

    version_history = default_version_history(record)
    version_history.append(
        {
            "version": record.get("source", {}).get("version", "0.1"),
            "date": today,
            "change_type": "review_update",
            "summary": change_summary or f"Review updated to {status}.",
        }
    )
    record["version_history"] = version_history

    _dump_library_document(library_path, data)
    return record
