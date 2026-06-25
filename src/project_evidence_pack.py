from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from .multi_objective import _candidate_outcome_rows


DEFAULT_PROJECT_EVIDENCE_PACK_PATH = Path("data/projects/demo/project_evidence_pack.json")
DEFAULT_PROJECT_EVIDENCE_PACK_CSV_PATH = Path("data/projects/demo/project_evidence_pack_summary.csv")


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _mean(values: list[float]) -> float | None:
    return round(mean(values), 4) if values else None


def _project_context_summary(outcome_rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in outcome_rows:
        context = row.get("target_context") or {}
        grouped[
            (
                str(context.get("endpoint_group") or row.get("endpoint_group") or "unspecified"),
                str(context.get("target_family") or "unspecified"),
                str(context.get("assay_type") or "unspecified"),
            )
        ].append(row)
    summaries = []
    for (endpoint, family, assay), rows in sorted(grouped.items()):
        outcomes = [float(row.get("outcome_value") or 0.0) for row in rows]
        positives = [value for value in outcomes if value >= 0.7]
        negatives = [value for value in outcomes if value <= 0.35]
        summaries.append(
            {
                "endpoint_group": endpoint,
                "target_family": family,
                "assay_type": assay,
                "outcome_count": len(rows),
                "mean_outcome": _mean(outcomes),
                "positive_count": len(positives),
                "negative_count": len(negatives),
                "positive_rate": round(len(positives) / len(rows), 4) if rows else None,
                "candidate_count": len({str(row.get("candidate_id") or "") for row in rows if row.get("candidate_id")}),
            }
        )
    summaries.sort(key=lambda row: (-int(row.get("outcome_count") or 0), str(row.get("endpoint_group") or "")))
    return summaries


def _active_context_sets(context_summary: list[dict]) -> tuple[set[str], set[str]]:
    endpoints = {str(row.get("endpoint_group") or "").lower() for row in context_summary if row.get("endpoint_group")}
    families = {str(row.get("target_family") or "").lower() for row in context_summary if row.get("target_family")}
    return endpoints - {"all", "unspecified"}, families - {"all", "unspecified"}


def _top_public_signals(public_report: dict, *, endpoints: set[str], families: set[str], limit: int) -> list[dict]:
    rows = []
    for signal in public_report.get("signals") or []:
        endpoint = str(signal.get("endpoint_group") or "").lower()
        family = str(signal.get("target_family") or "").lower()
        if endpoints and endpoint not in endpoints:
            continue
        if families and family not in families and family not in {"", "all", "unspecified", "other"}:
            continue
        rows.append(
            {
                "signal_id": signal.get("signal_id"),
                "signal_scope": signal.get("signal_scope"),
                "signal_key": signal.get("signal_key"),
                "endpoint_group": signal.get("endpoint_group"),
                "target_family": signal.get("target_family"),
                "operator": signal.get("operator"),
                "public_evidence_score": signal.get("public_evidence_score"),
                "public_evidence_count": signal.get("public_evidence_count"),
                "support_count": signal.get("support_count"),
                "contradiction_count": signal.get("contradiction_count"),
                "inconclusive_count": signal.get("inconclusive_count"),
                "basis": signal.get("basis"),
                "source_names": signal.get("source_names"),
            }
        )
    rows.sort(key=lambda row: (-(float(row.get("public_evidence_score") or 0.0)), -(int(row.get("public_evidence_count") or 0))))
    return rows[: int(limit)]


def _residual_model_rows(model_report: dict, *, endpoints: set[str], families: set[str], limit: int) -> list[dict]:
    rows = []
    for row in model_report.get("rows") or []:
        endpoint = str(row.get("endpoint_group") or "").lower()
        family = str(row.get("target_family") or "").lower()
        if endpoints and endpoint not in endpoints:
            continue
        if families and family not in families and family not in {"", "all", "unspecified"}:
            continue
        rows.append(row)
    rows.sort(key=lambda row: (-(float(row.get("max_abs_residual") or 0.0)), -(int(row.get("observed_count") or 0))))
    return rows[: int(limit)]


def _residual_task_rows(registry: dict, *, limit: int) -> list[dict]:
    rows = [dict(row) for row in registry.get("tasks") or []]
    rows.sort(key=lambda row: (str(row.get("status") or ""), -(float(row.get("expected_information_gain") or 0.0))))
    return rows[: int(limit)]


def _analog_series_rows(report: dict, *, limit: int) -> list[dict]:
    rows = []
    for row in report.get("series") or []:
        rows.append(
            {
                "series_key": row.get("series_key"),
                "endpoint_group": row.get("endpoint_group") or row.get("primary_endpoint_group"),
                "target_family": row.get("target_family"),
                "candidate_count": row.get("candidate_count"),
                "observed_event_count": row.get("observed_event_count") or row.get("observed_candidate_count"),
                "series_delta_action": row.get("series_delta_action"),
                "recommendation": row.get("recommendation") or row.get("series_recommendation"),
                "mean_observed_feedback": row.get("mean_observed_feedback") or row.get("mean_observed_score"),
                "max_evidence_confidence_abs_residual": row.get("max_evidence_confidence_abs_residual"),
                "evidence_sufficiency_score": row.get("evidence_sufficiency_score"),
                "evidence_sufficiency_status": row.get("evidence_sufficiency_status"),
                "next_evidence_action": row.get("next_evidence_action"),
            }
        )
    rows.sort(key=lambda row: (-(float(row.get("max_evidence_confidence_abs_residual") or 0.0)), -(int(row.get("observed_event_count") or 0))))
    return rows[: int(limit)]


def _scaffold_draft_summary(path: Path) -> dict:
    if not path.exists():
        return {"draft_count": 0, "status_counts": {}}
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    return {
        "draft_count": len(rows),
        "status_counts": dict(Counter(str(row.get("draft_status") or "unknown") for row in rows).most_common()),
        "pending_count": sum(1 for row in rows if str(row.get("draft_status") or "") not in {"applied", "rejected", "retired"}),
    }


def build_project_evidence_pack(
    *,
    root: str | Path = ".",
    db_path: str | Path = Path("data/localmedchem.sqlite"),
    project_name: str | None = "demo_learning",
    max_public_signals: int = 40,
    max_residual_rows: int = 20,
) -> dict:
    root_path = Path(root)
    outcome_rows = _candidate_outcome_rows(db_path=db_path, project_name=project_name)
    context_summary = _project_context_summary(outcome_rows)
    endpoints, families = _active_context_sets(context_summary)
    public_report = _read_json(root_path / "data/substituents/public_strategy_signal_report.json")
    residual_model = _read_json(root_path / "data/substituents/endpoint_family_residual_model.json")
    residual_registry = _read_json(root_path / "data/substituents/evidence_residual_task_registry.json")
    analog_series = _read_json(root_path / "data/projects/demo/analog_series_report.json")
    top_public = _top_public_signals(public_report, endpoints=endpoints, families=families, limit=max_public_signals)
    residual_rows = _residual_model_rows(residual_model, endpoints=endpoints, families=families, limit=max_residual_rows)
    residual_tasks = _residual_task_rows(residual_registry, limit=max_residual_rows)
    analog_rows = _analog_series_rows(analog_series, limit=max_residual_rows)
    evidence_gaps = []
    for row in residual_rows:
        action = str(row.get("recommended_weight_action") or "")
        if action and action != "keep_current_weight":
            evidence_gaps.append(
                {
                    "gap_type": "endpoint_family_residual",
                    "endpoint_group": row.get("endpoint_group"),
                    "target_family": row.get("target_family"),
                    "evidence_source": row.get("evidence_source"),
                    "recommended_action": action,
                    "max_abs_residual": row.get("max_abs_residual"),
                    "confidence": row.get("adjustment_confidence"),
                }
            )
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name,
        "status": "ready" if outcome_rows or top_public or residual_rows else "empty",
        "outcome_count": len(outcome_rows),
        "context_summary": context_summary,
        "active_endpoint_count": len(endpoints),
        "active_target_family_count": len(families),
        "top_public_signal_count": len(top_public),
        "top_public_signals": top_public,
        "endpoint_family_residual_rows": residual_rows,
        "residual_task_status_counts": residual_registry.get("status_counts") or {},
        "top_residual_tasks": residual_tasks,
        "analog_series_rows": analog_rows,
        "scaffold_review_drafts": _scaffold_draft_summary(root_path / "data/substituents/scaffold_rule_review_drafts.csv"),
        "evidence_gaps": evidence_gaps[: int(max_residual_rows)],
        "recommended_next_actions": [
            "Use top_public_signals only as priors when they overlap active endpoint/family contexts.",
            "Route endpoint_family_residual gaps into residual result imports before changing score weights.",
            "Keep scaffold review drafts as manual sign-off items before promotion gate readiness.",
        ],
    }


def write_project_evidence_pack(
    report: dict,
    output_path: str | Path = DEFAULT_PROJECT_EVIDENCE_PACK_PATH,
    *,
    summary_csv_path: str | Path | None = DEFAULT_PROJECT_EVIDENCE_PACK_CSV_PATH,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if summary_csv_path is not None:
        csv_path = Path(summary_csv_path)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        rows: list[dict[str, Any]] = []
        for row in report.get("context_summary") or []:
            rows.append({"section": "context_summary", **row})
        for row in report.get("evidence_gaps") or []:
            rows.append({"section": "evidence_gap", **row})
        fieldnames = sorted({key for row in rows for key in row}) or ["section"]
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fieldnames})
