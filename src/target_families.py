from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml


DEFAULT_TARGET_FAMILY_RULES_PATH = Path(__file__).resolve().parents[2] / "data" / "rules" / "target_family_normalization.yaml"


@lru_cache(maxsize=8)
def load_target_family_rules(path: str | Path | None = None) -> dict:
    rules_path = Path(path) if path is not None else DEFAULT_TARGET_FAMILY_RULES_PATH
    if not rules_path.exists():
        return {}
    with rules_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _text(*values: object) -> str:
    return " ".join(str(value or "").lower() for value in values if value not in {None, ""})


def normalize_target_family(
    value: str | None = None,
    *,
    target_pref_name: str | None = None,
    target_type: str | None = None,
    rules: dict | None = None,
) -> dict:
    rules = rules or load_target_family_rules()
    haystack = _text(value, target_pref_name, target_type)
    for family in rules.get("families") or []:
        tokens = [str(token).lower() for token in ((family.get("match") or {}).get("any_contains") or [])]
        if any(token and token in haystack for token in tokens):
            return {
                "target_family_normalized": family.get("family_id"),
                "target_family_label": family.get("label") or family.get("family_id"),
                "target_family_weight": float(family.get("weight") or 1.0),
            }
    default = rules.get("default") or {"family_id": "other", "label": "Other / target-specific", "weight": 1.0}
    return {
        "target_family_normalized": default.get("family_id"),
        "target_family_label": default.get("label") or default.get("family_id"),
        "target_family_weight": float(default.get("weight") or 1.0),
    }


def normalize_target_context(context: dict | None) -> dict:
    context = context or {}
    normalized = normalize_target_family(
        context.get("target_family"),
        target_pref_name=context.get("target_pref_name"),
        target_type=context.get("target_type"),
    )
    return {
        **context,
        **normalized,
        "target_family": context.get("target_family"),
        "assay_type": context.get("assay_type") or context.get("standard_type"),
        "endpoint_group": context.get("endpoint_group"),
    }
