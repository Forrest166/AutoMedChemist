from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_JSON = Path("data/substituents/rgroup_staging_admission_scorecard.json")
DEFAULT_CSV = Path("data/substituents/rgroup_staging_admission_scorecard.csv")
DEFAULT_MD = Path("docs/rgroup_staging_admission_scorecard.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import", "production_scoring_write"]


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _int(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _source_metrics(metrics: dict) -> dict[str, dict]:
    return {
        str(row.get("group_key") or ""): dict(row)
        for row in metrics.get("rows") or []
        if str(row.get("metric_type") or "") == "source" and row.get("group_key")
    }


def _signoff_counts(signoff: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in signoff.get("rows") or []:
        source = str(row.get("source_dataset") or "").strip()
        if source and str(row.get("curator_decision") or "") in {"ready_for_sandbox_review", "accepted_for_sandbox", "reviewed"}:
            counts[source] = counts.get(source, 0) + 1
    return counts


def _source_confidence(ledger: dict, source: str) -> float:
    values = [
        _float(row.get("source_confidence_score"))
        for row in ledger.get("rows") or []
        if str(row.get("source_dataset") or "") == source and str(row.get("source_confidence_score") or "").strip()
    ]
    values = [value for value in values if value > 0]
    return round(sum(values) / len(values), 4) if values else 0.0


def _candidate_impact_from_ledger(ledger: dict, source: str) -> tuple[int, str]:
    impacted = 0
    candidates: list[str] = []
    for row in ledger.get("rows") or []:
        if str(row.get("source_dataset") or "") != source:
            continue
        matched = str(row.get("matched_candidate_ids") or "").strip()
        if matched:
            impacted += 1
            for candidate_id in matched.replace(";", ",").split(","):
                candidate_id = candidate_id.strip()
                if candidate_id and candidate_id not in candidates:
                    candidates.append(candidate_id)
    return impacted, ";".join(candidates[:8])


def _bucket(score: float, blockers: int, signoff_count: int) -> str:
    if blockers:
        return "blocked_pending_curation"
    if signoff_count <= 0:
        return "needs_curator_signoff"
    if score >= 75:
        return "ready_for_sandbox_review"
    if score >= 55:
        return "curator_review"
    return "hold_for_data_cleanup"


def build_rgroup_staging_admission_scorecard(
    *,
    root: str | Path = ".",
) -> dict[str, Any]:
    root_path = Path(root)
    budget = _read_json(root_path / "data/substituents/rgroup_staging_quality_budget.json")
    signoff = _read_json(root_path / "data/substituents/rgroup_staging_curator_signoff.json")
    ledger = _read_json(root_path / "data/substituents/rgroup_feed_digestion_ledger.json")
    quality_metrics = _read_json(root_path / "data/substituents/rgroup_digestion_quality_metrics.json")
    metrics_by_source = _source_metrics(quality_metrics)
    signoff_by_source = _signoff_counts(signoff)
    rows: list[dict[str, Any]] = []
    for index, budget_row in enumerate(budget.get("rows") or budget.get("manual_review_queue_rows") or [], start=1):
        source = str(budget_row.get("source_dataset") or "").strip()
        metric = metrics_by_source.get(source, {})
        row_count = _int(budget_row.get("row_count"))
        blockers = _int(budget_row.get("blocker_count"))
        duplicate_pressure = _int(metric.get("duplicate_pressure_count")) + _int(budget_row.get("duplicate_row_sha256_count")) + _int(budget_row.get("duplicate_replacement_id_count"))
        missing_metadata = _int(budget_row.get("missing_metadata_count"))
        low_confidence = _int(metric.get("low_confidence_count")) + _int(budget_row.get("low_confidence_count"))
        unreviewed = _int(budget_row.get("unreviewed_count"))
        confidence_avg = _float(metric.get("confidence_avg")) or _source_confidence(ledger, source)
        signoff_count = signoff_by_source.get(source, 0)
        impacted_rows, impacted_candidates = _candidate_impact_from_ledger(ledger, source)
        source_credibility = _score((50 + confidence_avg * 50) - blockers * 18 - missing_metadata * 4 - low_confidence * 7 - unreviewed * 6)
        duplicate_score = _score(100 - duplicate_pressure * 2.5)
        disabled_contexts = str(budget_row.get("disabled_contexts") or "")
        applicable_contexts = str(budget_row.get("applicable_contexts") or "")
        has_scope_guard = all(scope in disabled_contexts for scope in BLOCKED_SCOPES)
        context_fit = _score(70 + (15 if "local" in applicable_contexts.lower() else 0) + (15 if has_scope_guard else -25) - blockers * 10)
        candidate_impact = _score(45 + min(35, impacted_rows * 12) + min(15, _int(metric.get("candidate_impacted_row_count")) * 3) - _int(metric.get("deferred_count")) * 3)
        admission_score = _score(source_credibility * 0.35 + duplicate_score * 0.2 + context_fit * 0.25 + candidate_impact * 0.2)
        rows.append(
            {
                "rank": index,
                "source_dataset": source,
                "admission_score": admission_score,
                "admission_bucket": _bucket(admission_score, blockers, signoff_count),
                "source_credibility_score": source_credibility,
                "duplicate_pressure_score": duplicate_score,
                "context_fit_score": context_fit,
                "candidate_impact_score": candidate_impact,
                "row_count": row_count,
                "blocker_count": blockers,
                "warning_count": _int(budget_row.get("warning_count")),
                "duplicate_pressure_count": duplicate_pressure,
                "low_confidence_count": low_confidence,
                "curator_signoff_count": signoff_count,
                "candidate_impacted_row_count": impacted_rows or _int(metric.get("candidate_impacted_row_count")),
                "impacted_candidate_ids": impacted_candidates,
                "applicable_contexts": applicable_contexts,
                "disabled_contexts": disabled_contexts,
                "production_scoring_write_allowed": False,
                "promotion_allowed": False,
                "next_action": (
                    "Resolve blockers before sandbox review."
                    if blockers
                    else "Record curator signoff before sandbox scoring."
                    if signoff_count <= 0
                    else "Review this source in sandbox score-delta and digestion quality views."
                ),
            }
        )
    rows.sort(key=lambda row: (-_float(row.get("admission_score")), str(row.get("source_dataset") or "")))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    bucket_counts: dict[str, int] = {}
    for row in rows:
        bucket = str(row.get("admission_bucket") or "unknown")
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "mode": "rgroup_staging_admission_scorecard",
        "row_count": len(rows),
        "bucket_counts": bucket_counts,
        "top_source": rows[0].get("source_dataset") if rows else "",
        "promotion_allowed": False,
        "production_scoring_write_allowed": False,
        "rows": rows,
        "recommended_next_actions": [
            "Use admission_score to choose the next local sandbox-review source.",
            "Keep production scoring writes and feed promotion disabled until separate governed ledgers approve them.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_rgroup_staging_admission_scorecard_markdown(report: dict) -> str:
    lines = [
        "# R-group Staging Admission Scorecard",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows: `{report.get('row_count')}`",
        f"- Promotion allowed: `{report.get('promotion_allowed')}`",
        "",
        "| Rank | Source | Bucket | Score | Credibility | Duplicate | Context | Impact | Rows | Signoff | Next Action |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("rank") or ""),
                    str(row.get("source_dataset") or ""),
                    str(row.get("admission_bucket") or ""),
                    str(row.get("admission_score") or 0),
                    str(row.get("source_credibility_score") or 0),
                    str(row.get("duplicate_pressure_score") or 0),
                    str(row.get("context_fit_score") or 0),
                    str(row.get("candidate_impact_score") or 0),
                    str(row.get("row_count") or 0),
                    str(row.get("curator_signoff_count") or 0),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_rgroup_staging_admission_scorecard(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_JSON,
    csv_path: str | Path | None = DEFAULT_CSV,
    markdown_path: str | Path | None = DEFAULT_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "rank",
        "source_dataset",
        "admission_score",
        "admission_bucket",
        "source_credibility_score",
        "duplicate_pressure_score",
        "context_fit_score",
        "candidate_impact_score",
        "row_count",
        "blocker_count",
        "warning_count",
        "duplicate_pressure_count",
        "low_confidence_count",
        "curator_signoff_count",
        "candidate_impacted_row_count",
        "impacted_candidate_ids",
        "applicable_contexts",
        "disabled_contexts",
        "production_scoring_write_allowed",
        "promotion_allowed",
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
        md_file.write_text(render_rgroup_staging_admission_scorecard_markdown(report), encoding="utf-8")
