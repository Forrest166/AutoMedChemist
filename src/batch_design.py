from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from .export import export_csv


BATCH_EXPORT_COLUMNS = [
    "route_batch_id",
    "batch_type",
    "rank",
    "candidate_id",
    "replacement_label",
    "substituent_name",
    "score",
    "procurement_bucket",
    "availability_tier",
    "lead_time_days",
    "route_confidence",
    "route_steps",
    "reaction_family",
    "suggested_building_block",
    "route_template_id",
    "route_routine_level",
    "route_risk_flags",
    "catalog_url",
    "quote_status",
    "quote_request_id",
    "chemist_approval_status",
    "reagent_overlap_key",
    "reagent_overlap_score",
    "protecting_group_risk",
    "regioselectivity_risk",
    "purification_risk",
    "route_execution_risk_score",
    "smiles",
]


def _float(value, default: float = 0.0) -> float:
    try:
        if value in {None, ""}:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value, default: int = 0) -> int:
    try:
        if value in {None, ""}:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def route_risk_flags(row: dict) -> list[str]:
    flags = []
    bucket = str(row.get("procurement_bucket") or "unknown")
    routine = str(row.get("route_routine_level") or "").lower()
    lead_time = _int(row.get("lead_time_days"))
    route_confidence = _float(row.get("route_confidence"))
    route_steps = _int(row.get("route_steps"))
    if bucket in {"blocked", "unknown", "review"}:
        flags.append(f"bucket_{bucket}")
    if bucket == "custom_synthesis" or routine in {"specialty", "custom"}:
        flags.append("custom_route_review")
    if lead_time >= 21:
        flags.append("long_lead_time")
    if route_confidence and route_confidence < 0.5:
        flags.append("low_route_confidence")
    if route_steps >= 4:
        flags.append("multi_step_route")
    if not row.get("suggested_building_block") and bucket not in {"quick_purchase", "blocked"}:
        flags.append("missing_building_block")
    return flags


def batch_type_for_bucket(bucket: str | None) -> str:
    value = str(bucket or "unknown")
    if value == "quick_purchase":
        return "quick_purchase"
    if value == "standard_route":
        return "standard_route"
    if value == "custom_synthesis":
        return "custom_synthesis"
    return "review"


def _batch_key(row: dict) -> tuple[str, str, str, str, str]:
    bucket = str(row.get("procurement_bucket") or "unknown")
    return (
        batch_type_for_bucket(bucket),
        bucket,
        str(row.get("reaction_family") or row.get("route_template_id") or "unspecified_reaction"),
        str(row.get("suggested_building_block") or "unspecified_building_block"),
        str(row.get("route_template_id") or row.get("route_routine_level") or "unspecified_route"),
    )


def _candidate_sort_key(row: dict) -> tuple[float, int]:
    return (_float(row.get("score")), -_int(row.get("rank"), 999999))


def _execution_for_batch(batch: dict, candidates: list[dict]) -> dict:
    batch_type = batch["batch_type"]
    candidate_ids = [str(row.get("candidate_id")) for row in candidates if row.get("candidate_id")]
    lead_times = [_int(row.get("lead_time_days")) for row in candidates if row.get("lead_time_days") not in {None, ""}]
    catalog_urls = [str(row.get("availability_source_url")) for row in candidates if row.get("availability_source_url")]
    overlap_key = "|".join(
        [
            str(batch.get("reaction_family") or "unspecified_reaction"),
            str(batch.get("suggested_building_block") or "unspecified_building_block"),
            str(batch.get("route_template_id") or "unspecified_route"),
        ]
    )
    action = {
        "quick_purchase": "request_catalog_purchase",
        "standard_route": "route_feasibility_review",
        "custom_synthesis": "request_custom_synthesis_quote",
        "review": "chemist_triage",
    }.get(batch_type, "chemist_triage")
    quote_status = "quote_not_required" if batch_type == "quick_purchase" else "needs_quote"
    risk_profile = route_execution_risk_profile(batch, candidates)
    return {
        "recommended_action": action,
        "chemist_approval_status": "needs_chemist_review",
        "quote_status": quote_status,
        "quote_request_id": f"QUOTE-{batch.get('route_batch_id', 'BATCH')}",
        "reagent_overlap_key": overlap_key,
        **risk_profile,
        "catalog_urls": catalog_urls[:10],
        "candidate_ids": candidate_ids,
        "estimated_total_lead_time_days": max(lead_times) if lead_times else None,
        "purchase_bucket": batch_type,
    }


def _risk_bucket(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def route_execution_risk_profile(batch: dict, candidates: list[dict]) -> dict:
    candidate_count = max(len(candidates), 1)
    overlap_counts = Counter(
        "|".join(
            [
                str(row.get("reaction_family") or batch.get("reaction_family") or "unspecified_reaction"),
                str(row.get("suggested_building_block") or batch.get("suggested_building_block") or "unspecified_building_block"),
            ]
        )
        for row in candidates
    )
    most_common_overlap = overlap_counts.most_common(1)[0][1] if overlap_counts else 1
    reagent_overlap_score = round(100.0 * most_common_overlap / candidate_count, 2)
    flags = Counter(flag for row in candidates for flag in route_risk_flags(row))
    route_steps = max((_int(row.get("route_steps")) for row in candidates), default=0)
    unknown_fraction = sum(1 for row in candidates if str(row.get("procurement_bucket") or "unknown") == "unknown") / candidate_count
    specialty_fraction = sum(
        1
        for row in candidates
        if str(row.get("route_routine_level") or "").lower() in {"specialty", "advanced", "custom"}
        or str(row.get("batch_type") or batch.get("batch_type")) in {"custom_synthesis", "review"}
    ) / candidate_count
    protecting_score = min(100.0, 18.0 * route_steps + 25.0 * specialty_fraction)
    regio_score = min(100.0, 35.0 * unknown_fraction + 18.0 * bool(flags.get("missing_building_block")) + 15.0 * bool(flags.get("low_route_confidence")))
    purification_score = min(100.0, 22.0 * route_steps + 18.0 * specialty_fraction + 18.0 * bool(flags.get("custom_route_review")))
    total_score = round(0.25 * (100.0 - reagent_overlap_score) + 0.25 * protecting_score + 0.25 * regio_score + 0.25 * purification_score, 2)
    return {
        "reagent_overlap_score": reagent_overlap_score,
        "protecting_group_risk": _risk_bucket(protecting_score),
        "regioselectivity_risk": _risk_bucket(regio_score),
        "purification_risk": _risk_bucket(purification_score),
        "route_execution_risk_score": total_score,
    }


def build_route_batches(rows: list[dict], *, top_n_per_batch: int | None = None) -> list[dict]:
    grouped: dict[tuple[str, str, str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[_batch_key(row)].append(row)

    summaries = []
    for key, items in grouped.items():
        batch_type, bucket, reaction_family, building_block, route_template_id = key
        ranked = sorted(items, key=_candidate_sort_key, reverse=True)
        if top_n_per_batch is not None:
            ranked = ranked[:top_n_per_batch]
        lead_times = [_int(row.get("lead_time_days")) for row in ranked if row.get("lead_time_days") not in {None, ""}]
        confidences = [_float(row.get("route_confidence")) for row in ranked if row.get("route_confidence") not in {None, ""}]
        flags = Counter(flag for row in ranked for flag in route_risk_flags(row))
        summaries.append(
            {
                "batch_type": batch_type,
                "procurement_bucket": bucket,
                "reaction_family": reaction_family,
                "suggested_building_block": building_block,
                "route_template_id": route_template_id,
                "candidate_count": len(ranked),
                "top_score": round(max(_float(row.get("score")) for row in ranked), 4) if ranked else None,
                "mean_score": round(mean(_float(row.get("score")) for row in ranked), 4) if ranked else None,
                "mean_lead_time_days": round(mean(lead_times), 2) if lead_times else None,
                "mean_route_confidence": round(mean(confidences), 4) if confidences else None,
                "route_risk_flags": ";".join(flag for flag, _count in flags.most_common()),
                "candidate_ids": ";".join(str(row.get("candidate_id")) for row in ranked if row.get("candidate_id")),
                "candidates": ranked,
            }
        )

    priority = {"quick_purchase": 0, "standard_route": 1, "custom_synthesis": 2, "review": 3}
    summaries.sort(key=lambda item: (priority.get(item["batch_type"], 9), -(item.get("top_score") or 0), item["reaction_family"]))
    for idx, batch in enumerate(summaries, start=1):
        batch["route_batch_id"] = f"BATCH-{idx:03d}"
        batch["execution"] = _execution_for_batch(batch, batch["candidates"])
        batch["chemist_approval_status"] = batch["execution"]["chemist_approval_status"]
        batch["quote_status"] = batch["execution"]["quote_status"]
        batch["quote_request_id"] = batch["execution"]["quote_request_id"]
        batch["reagent_overlap_key"] = batch["execution"]["reagent_overlap_key"]
        batch["reagent_overlap_score"] = batch["execution"]["reagent_overlap_score"]
        batch["protecting_group_risk"] = batch["execution"]["protecting_group_risk"]
        batch["regioselectivity_risk"] = batch["execution"]["regioselectivity_risk"]
        batch["purification_risk"] = batch["execution"]["purification_risk"]
        batch["route_execution_risk_score"] = batch["execution"]["route_execution_risk_score"]
        for candidate in batch["candidates"]:
            candidate["route_batch_id"] = batch["route_batch_id"]
            candidate["batch_type"] = batch["batch_type"]
            candidate["route_risk_flags"] = ";".join(route_risk_flags(candidate))
            candidate["catalog_url"] = candidate.get("availability_source_url")
            candidate["chemist_approval_status"] = batch["chemist_approval_status"]
            candidate["quote_status"] = batch["quote_status"]
            candidate["quote_request_id"] = batch["quote_request_id"]
            candidate["reagent_overlap_key"] = batch["reagent_overlap_key"]
            candidate["reagent_overlap_score"] = batch["reagent_overlap_score"]
            candidate["protecting_group_risk"] = batch["protecting_group_risk"]
            candidate["regioselectivity_risk"] = batch["regioselectivity_risk"]
            candidate["purification_risk"] = batch["purification_risk"]
            candidate["route_execution_risk_score"] = batch["route_execution_risk_score"]
    return summaries


def route_batch_summary(rows: list[dict]) -> dict:
    batches = build_route_batches(rows)
    counts = Counter(batch["batch_type"] for batch in batches)
    return {
        "batch_count": len(batches),
        "candidate_count": sum(batch["candidate_count"] for batch in batches),
        "batch_type_counts": dict(counts.most_common()),
        "batches": [
            {key: value for key, value in batch.items() if key != "candidates"}
            for batch in batches
        ],
    }


def load_candidate_csv(path: str | Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _project_columns(rows: list[dict]) -> list[dict]:
    projected = []
    for row in rows:
        projected.append({column: row.get(column) for column in BATCH_EXPORT_COLUMNS if column in row})
    return projected


def write_route_batch_exports(rows: list[dict], output_dir: str | Path) -> dict:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    batches = build_route_batches(rows)
    summary = {
        "batch_count": len(batches),
        "candidate_count": sum(batch["candidate_count"] for batch in batches),
        "batches": batches,
    }

    json_path = out_dir / "route_batches.json"
    csv_path = out_dir / "route_batches.csv"
    execution_json_path = out_dir / "route_execution_plan.json"
    execution_csv_path = out_dir / "route_execution_plan.csv"
    approval_csv_path = out_dir / "batch_approval_queue.csv"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    export_csv(
        [{key: value for key, value in batch.items() if key != "candidates"} for batch in batches],
        csv_path,
    )
    execution_rows = [
        {
            "route_batch_id": batch["route_batch_id"],
            "batch_type": batch["batch_type"],
            "recommended_action": batch["execution"]["recommended_action"],
            "quote_status": batch["quote_status"],
            "quote_request_id": batch["quote_request_id"],
            "chemist_approval_status": batch["chemist_approval_status"],
            "reagent_overlap_key": batch["reagent_overlap_key"],
            "estimated_total_lead_time_days": batch["execution"].get("estimated_total_lead_time_days"),
            "reagent_overlap_score": batch["reagent_overlap_score"],
            "protecting_group_risk": batch["protecting_group_risk"],
            "regioselectivity_risk": batch["regioselectivity_risk"],
            "purification_risk": batch["purification_risk"],
            "route_execution_risk_score": batch["route_execution_risk_score"],
            "candidate_count": batch["candidate_count"],
            "candidate_ids": batch["candidate_ids"],
            "catalog_urls": ";".join(batch["execution"].get("catalog_urls") or []),
            "route_risk_flags": batch.get("route_risk_flags"),
        }
        for batch in batches
    ]
    execution_json_path.write_text(json.dumps({"execution_batches": execution_rows}, indent=2, sort_keys=True), encoding="utf-8")
    export_csv(execution_rows, execution_csv_path)
    export_csv(
        [
            {
                "route_batch_id": row["route_batch_id"],
                "chemist_approval_status": row["chemist_approval_status"],
                "approval_note": "",
                "recommended_action": row["recommended_action"],
                "candidate_count": row["candidate_count"],
                "route_risk_flags": row["route_risk_flags"],
                "route_execution_risk_score": row["route_execution_risk_score"],
            }
            for row in execution_rows
        ],
        approval_csv_path,
    )

    exported = {
        "route_batches_json": str(json_path.resolve()),
        "route_batches_csv": str(csv_path.resolve()),
        "route_execution_plan_json": str(execution_json_path.resolve()),
        "route_execution_plan_csv": str(execution_csv_path.resolve()),
        "batch_approval_queue_csv": str(approval_csv_path.resolve()),
    }
    for batch_type in ["quick_purchase", "standard_route", "custom_synthesis", "review"]:
        candidates = []
        for batch in batches:
            if batch["batch_type"] == batch_type:
                candidates.extend(batch["candidates"])
        path = out_dir / f"{batch_type}_candidates.csv"
        export_csv(_project_columns(candidates), path)
        exported[f"{batch_type}_csv"] = str(path.resolve())
    return {"summary": summary, "outputs": exported}
