from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


PRECEDENTED_BUCKETS = {"approved_drug_precedented", "clinical_trial_precedented", "ertl_common"}
EXPANDED_BUCKETS = {"ertl_precedented", "ertl_expansion"}
DEFAULT_TIER_TARGETS = {
    "precedented": 0.4,
    "expanded": 0.35,
    "exploratory": 0.25,
}


def _float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def novelty_tier(row: dict) -> str:
    novelty = str(row.get("ring_novelty_bucket") or "")
    enumeration = str(row.get("enumeration_type") or "")
    if novelty in PRECEDENTED_BUCKETS:
        return "precedented"
    if novelty in EXPANDED_BUCKETS:
        return "expanded"
    if novelty:
        return "exploratory"
    if enumeration in {"ring_network_replacement", "scaffold_replacement"}:
        return "exploratory"
    if enumeration == "rgroup_network_replacement":
        return "expanded"
    return "precedented"


def novelty_diversity_bucket(row: dict) -> str:
    tier = novelty_tier(row)
    diversity = (
        row.get("ring_diversity_bucket")
        or row.get("diversity_bucket")
        or row.get("replacement_class")
        or row.get("enumeration_type")
        or "unknown"
    )
    site = row.get("site_type") or "site"
    return f"{tier}:{site}:{diversity}"


def _selection_key(row: dict) -> tuple[float, float, float]:
    return (
        _float(row.get("score"), 0.0),
        _float(row.get("ring_sampling_score"), 0.0),
        _float(row.get("public_strategy_signal_score"), 0.0),
    )


def select_novelty_diversity_batch(
    rows: list[dict],
    *,
    max_rows: int = 24,
    per_bucket_limit: int = 3,
    tier_targets: dict[str, float] | None = None,
) -> list[dict]:
    if max_rows <= 0 or not rows:
        return []
    targets = {**DEFAULT_TIER_TARGETS, **(tier_targets or {})}
    tier_limits = {
        tier: max(1, int(round(max_rows * fraction)))
        for tier, fraction in targets.items()
        if fraction > 0
    }
    sorted_rows = sorted(rows, key=_selection_key, reverse=True)
    selected: list[dict] = []
    selected_ids: set[str] = set()
    tier_counts: Counter = Counter()
    bucket_counts: Counter = Counter()

    def can_take(row: dict, *, strict_tier: bool) -> bool:
        candidate_id = str(row.get("candidate_id") or "")
        if candidate_id in selected_ids:
            return False
        bucket = row.get("novelty_batch_bucket") or novelty_diversity_bucket(row)
        tier = row.get("novelty_batch_tier") or novelty_tier(row)
        if bucket_counts[bucket] >= per_bucket_limit:
            return False
        if strict_tier and tier_counts[tier] >= tier_limits.get(tier, max_rows):
            return False
        return True

    def take(row: dict) -> None:
        item = dict(row)
        item["novelty_batch_tier"] = item.get("novelty_batch_tier") or novelty_tier(item)
        item["novelty_batch_bucket"] = item.get("novelty_batch_bucket") or novelty_diversity_bucket(item)
        item["novelty_batch_reason"] = (
            f"{item['novelty_batch_tier']} | {item['novelty_batch_bucket']} | score {item.get('score')}"
        )
        selected.append(item)
        selected_ids.add(str(item.get("candidate_id") or ""))
        tier_counts[item["novelty_batch_tier"]] += 1
        bucket_counts[item["novelty_batch_bucket"]] += 1

    for row in sorted_rows:
        if can_take(row, strict_tier=True):
            take(row)
            if len(selected) >= max_rows:
                break
    if len(selected) < max_rows:
        for row in sorted_rows:
            if can_take(row, strict_tier=False):
                take(row)
                if len(selected) >= max_rows:
                    break
    for rank, row in enumerate(selected, start=1):
        row["novelty_batch_rank"] = rank
        row["novelty_batch_pick"] = True
    return selected


def annotate_novelty_diversity_batch(
    rows: list[dict],
    *,
    max_rows: int = 24,
    per_bucket_limit: int = 3,
    tier_targets: dict[str, float] | None = None,
) -> list[dict]:
    enriched = []
    for row in rows:
        item = dict(row)
        item["novelty_batch_tier"] = novelty_tier(item)
        item["novelty_batch_bucket"] = novelty_diversity_bucket(item)
        enriched.append(item)
    selected = select_novelty_diversity_batch(
        enriched,
        max_rows=max_rows,
        per_bucket_limit=per_bucket_limit,
        tier_targets=tier_targets,
    )
    selected_by_id = {row.get("candidate_id"): row for row in selected}
    annotated = []
    for row in enriched:
        selected_row = selected_by_id.get(row.get("candidate_id"))
        if selected_row:
            item = {**row, **selected_row}
        else:
            item = {
                **row,
                "novelty_batch_pick": False,
                "novelty_batch_rank": None,
                "novelty_batch_reason": None,
            }
        annotated.append(item)
    return annotated


def novelty_batch_summary(rows: list[dict]) -> dict:
    picks = [row for row in rows if row.get("novelty_batch_pick")]
    return {
        "candidate_count": len(rows),
        "batch_count": len(picks),
        "tier_counts": dict(Counter(str(row.get("novelty_batch_tier") or "unknown") for row in picks)),
        "bucket_counts": dict(Counter(str(row.get("novelty_batch_bucket") or "unknown") for row in picks)),
        "top_score": max((_float(row.get("score")) for row in picks), default=None),
    }


def write_novelty_diversity_batch(rows: list[dict], output_prefix: str | Path) -> dict:
    prefix = Path(output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    csv_path = prefix.with_suffix(".csv")
    json_path = prefix.with_suffix(".json")
    fieldnames = sorted({key for row in rows for key in row})
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})
    json_path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    return {"csv": str(csv_path.resolve()), "json": str(json_path.resolve())}
