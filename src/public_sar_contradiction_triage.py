from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_PUBLIC_SAR_CONTRADICTION_TRIAGE_PATH = Path("data/projects/demo/public_sar_contradiction_triage.json")
DEFAULT_PUBLIC_SAR_CONTRADICTION_TRIAGE_CSV_PATH = Path("data/projects/demo/public_sar_contradiction_triage.csv")
DEFAULT_PUBLIC_SAR_CONTRADICTION_RESOLUTION_BATCH_PATH = Path("data/projects/demo/public_sar_contradiction_resolution_batch.json")
DEFAULT_PUBLIC_SAR_CONTRADICTION_RESOLUTION_BATCH_CSV_PATH = Path("data/projects/demo/public_sar_contradiction_resolution_batch.csv")
DEFAULT_PUBLIC_SAR_CONTRADICTION_WATCHLIST_PATH = Path("data/projects/demo/public_sar_contradiction_watchlist.json")
DEFAULT_PUBLIC_SAR_CONTRADICTION_WATCHLIST_CSV_PATH = Path("data/projects/demo/public_sar_contradiction_watchlist.csv")

SAR_TRIAGE_REVIEW_STATUSES = {"open", "in_review", "resolved", "deferred"}
SAR_TRIAGE_RESOLUTIONS = {
    "downgrade_public_prior",
    "retain_public_prior",
    "reference_only_watch",
    "block_public_prior",
    "needs_measurement",
}
_REVIEW_FIELDS = [
    "review_status",
    "resolution_status",
    "resolution_effect",
    "resolved_by",
    "resolved_at",
    "resolution_note",
    "resolution_history",
]


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _row_id(*parts: object) -> str:
    digest = hashlib.sha1("|".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()[:12].upper()
    return f"SARTRI-{digest}"


def _split_examples(value: object) -> set[str]:
    return {part.strip() for part in str(value or "").split(";") if part.strip()}


def _signal_key(signal: dict) -> str:
    return str(signal.get("signal_id") or signal.get("source_signal_id") or signal.get("signal_key") or "")


def _candidate_links_by_signal(validation: dict) -> dict[str, list[dict]]:
    links: dict[str, list[dict]] = defaultdict(list)
    for row in validation.get("rows") or []:
        keys = {
            str(row.get("source_signal_id") or ""),
            str(row.get("signal_key") or ""),
        } - {""}
        for key in keys:
            for link in row.get("candidate_links") or []:
                links[key].append({**dict(link), "task_id": row.get("task_id"), "link_source": "public_sar_validation"})
    return links


def _analog_links_by_signal(validation: dict) -> dict[str, list[dict]]:
    links: dict[str, list[dict]] = defaultdict(list)
    for row in validation.get("rows") or []:
        keys = {
            str(row.get("source_signal_id") or ""),
            str(row.get("signal_key") or ""),
        } - {""}
        for key in keys:
            for link in row.get("analog_series_links") or []:
                links[key].append({**dict(link), "task_id": row.get("task_id"), "link_source": "public_sar_validation"})
    return links


def _priority_links_by_signal(candidate_priority: dict) -> dict[str, list[dict]]:
    links: dict[str, list[dict]] = defaultdict(list)
    for row in candidate_priority.get("rows") or []:
        for key in _split_examples(row.get("public_sar_signal_examples")):
            links[key].append(
                {
                    "queue_id": row.get("queue_id"),
                    "candidate_id": row.get("candidate_id"),
                    "smiles": row.get("smiles") or row.get("candidate_key"),
                    "endpoint_group": row.get("endpoint_group"),
                    "enumeration_type": row.get("enumeration_type"),
                    "replacement_label": row.get("replacement_label"),
                    "queue_rank": row.get("queue_rank"),
                    "queue_priority_score": row.get("queue_priority_score"),
                    "candidate_evidence_priority_score": row.get("candidate_evidence_priority_score"),
                    "candidate_evidence_priority_tier": row.get("candidate_evidence_priority_tier"),
                    "link_source": "candidate_evidence_priority",
                }
            )
    return links


def _dedupe_rows(rows: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for row in rows:
        key = (
            str(row.get("queue_id") or ""),
            str(row.get("candidate_id") or ""),
            str(row.get("smiles") or ""),
            str(row.get("series_key") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _existing_resolution_lookup(path: str | Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    existing = _read_json(path)
    lookup = {}
    for row in existing.get("rows") or []:
        triage_id = str(row.get("triage_id") or "")
        if triage_id:
            lookup[triage_id] = {field: row.get(field, "") for field in _REVIEW_FIELDS}
    return lookup


def _resolution_effect(resolution_status: str) -> str:
    mapping = {
        "downgrade_public_prior": "downgrade_candidate_prior",
        "retain_public_prior": "retain_public_prior",
        "reference_only_watch": "exclude_from_candidate_scoring",
        "block_public_prior": "block_public_prior_from_scoring",
        "needs_measurement": "require_measured_feedback_before_scoring_change",
    }
    return mapping.get(resolution_status, "")


def _review_defaults(existing: dict | None = None) -> dict:
    existing = existing or {}
    return {
        "review_status": existing.get("review_status") or "open",
        "resolution_status": existing.get("resolution_status") or "",
        "resolution_effect": existing.get("resolution_effect") or _resolution_effect(str(existing.get("resolution_status") or "")),
        "resolved_by": existing.get("resolved_by") or "",
        "resolved_at": existing.get("resolved_at") or "",
        "resolution_note": existing.get("resolution_note") or "",
        "resolution_history": existing.get("resolution_history") or [],
    }


def _triage_priority(score: float, *, net_contradicted: bool, candidate_count: int) -> str:
    if net_contradicted and candidate_count:
        return "high"
    if score >= 26:
        return "high"
    if candidate_count or score >= 14:
        return "medium"
    return "low"


def _triage_action(*, net_contradicted: bool, candidate_count: int, analog_count: int) -> str:
    if candidate_count and net_contradicted:
        return "downgrade_candidate_public_prior_and_manual_review"
    if candidate_count:
        return "review_candidate_public_prior_balance"
    if analog_count:
        return "review_analog_series_public_prior"
    return "keep_reference_only_contradiction_watch"


def build_public_sar_contradiction_triage(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    public_strategy_signal_path: str | Path = "data/substituents/public_strategy_signal_report.json",
    public_sar_validation_path: str | Path = "data/projects/demo/public_sar_validation_report.json",
    candidate_priority_path: str | Path = "data/projects/demo/candidate_evidence_priority_report.json",
    existing_triage_path: str | Path | None = DEFAULT_PUBLIC_SAR_CONTRADICTION_TRIAGE_PATH,
    max_rows: int = 80,
) -> dict:
    root_path = Path(root)
    signal_file = Path(public_strategy_signal_path)
    validation_file = Path(public_sar_validation_path)
    priority_file = Path(candidate_priority_path)
    public_report = _read_json(signal_file if signal_file.is_absolute() else root_path / signal_file)
    validation = _read_json(validation_file if validation_file.is_absolute() else root_path / validation_file)
    candidate_priority = _read_json(priority_file if priority_file.is_absolute() else root_path / priority_file)
    validation_candidate_links = _candidate_links_by_signal(validation)
    validation_analog_links = _analog_links_by_signal(validation)
    priority_candidate_links = _priority_links_by_signal(candidate_priority)
    existing_review = _existing_resolution_lookup(
        Path(existing_triage_path) if existing_triage_path and Path(existing_triage_path).is_absolute() else root_path / Path(existing_triage_path)
        if existing_triage_path
        else None
    )

    rows = []
    for signal in public_report.get("signals") or []:
        contradiction_count = _int(signal.get("contradiction_count"))
        if contradiction_count <= 0:
            continue
        signal_id = _signal_key(signal)
        signal_key = str(signal.get("signal_key") or "")
        signal_keys = {signal_id, signal_key} - {""}
        candidate_links = []
        analog_links = []
        for key in signal_keys:
            candidate_links.extend(validation_candidate_links.get(key) or [])
            candidate_links.extend(priority_candidate_links.get(key) or [])
            analog_links.extend(validation_analog_links.get(key) or [])
        candidate_links = _dedupe_rows(candidate_links)
        analog_links = _dedupe_rows(analog_links)
        support_count = _int(signal.get("support_count"))
        evidence_count = _int(signal.get("public_evidence_count"), 1)
        score = _float(signal.get("public_evidence_score"), 55.0)
        net_contradicted = contradiction_count > support_count
        triage_score = round(
            min(
                100.0,
                contradiction_count * 7.5
                + max(0.0, 70.0 - score) * 0.35
                + min(14.0, evidence_count ** 0.5)
                + min(18.0, len(candidate_links) * 3.0)
                + min(8.0, len(analog_links) * 2.0),
            ),
            2,
        )
        action = _triage_action(net_contradicted=net_contradicted, candidate_count=len(candidate_links), analog_count=len(analog_links))
        priority = _triage_priority(triage_score, net_contradicted=net_contradicted, candidate_count=len(candidate_links))
        triage_id = _row_id(signal_id, signal_key, signal.get("endpoint_group"), signal.get("target_family"))
        review_fields = _review_defaults(existing_review.get(triage_id))
        rows.append(
            {
                "triage_id": triage_id,
                "task_type": "public_sar_contradiction_triage",
                "project_name": project_name,
                "priority": priority,
                "triage_score": triage_score,
                "triage_action": action,
                "source_signal_id": signal_id,
                "signal_key": signal_key,
                "signal_scope": signal.get("signal_scope"),
                "operator": signal.get("operator"),
                "endpoint_group": signal.get("endpoint_group"),
                "target_family": signal.get("target_family"),
                "public_evidence_score": score,
                "public_evidence_count": evidence_count,
                "support_count": support_count,
                "contradiction_count": contradiction_count,
                "net_contradicted": net_contradicted,
                "source_names": signal.get("source_names"),
                "basis": signal.get("basis"),
                "candidate_link_count": len(candidate_links),
                "analog_series_link_count": len(analog_links),
                "candidate_ids": ";".join(dict.fromkeys(str(row.get("candidate_id") or "") for row in candidate_links if row.get("candidate_id"))),
                "queue_ids": ";".join(dict.fromkeys(str(row.get("queue_id") or "") for row in candidate_links if row.get("queue_id"))),
                "analog_series_keys": ";".join(dict.fromkeys(str(row.get("series_key") or "") for row in analog_links if row.get("series_key"))),
                "candidate_links": candidate_links[:12],
                "analog_series_links": analog_links[:12],
                "next_step": (
                    "Review candidate public-prior balance before using this signal in scoring."
                    if action != "keep_reference_only_contradiction_watch"
                    else "Keep as reference-only contradiction watch until project candidate overlap exists."
                ),
                **review_fields,
            }
        )
    rows.sort(
        key=lambda row: (
            {"high": 0, "medium": 1, "low": 2}.get(str(row.get("priority")), 9),
            -_float(row.get("triage_score")),
            -_int(row.get("contradiction_count")),
            str(row.get("source_signal_id") or ""),
        )
    )
    rows = rows[: int(max_rows)]
    priority_counts = Counter(str(row.get("priority") or "unknown") for row in rows)
    action_counts = Counter(str(row.get("triage_action") or "unknown") for row in rows)
    review_counts = Counter(str(row.get("review_status") or "open") for row in rows)
    resolution_counts = Counter(str(row.get("resolution_status") or "unresolved") or "unresolved" for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "project_name": project_name,
        "row_count": len(rows),
        "high_priority_count": priority_counts.get("high", 0),
        "candidate_linked_count": sum(1 for row in rows if row.get("candidate_link_count")),
        "analog_series_linked_count": sum(1 for row in rows if row.get("analog_series_link_count")),
        "net_contradicted_count": sum(1 for row in rows if row.get("net_contradicted")),
        "priority_counts": dict(priority_counts.most_common()),
        "triage_action_counts": dict(action_counts.most_common()),
        "review_status_counts": dict(review_counts.most_common()),
        "resolution_status_counts": dict(resolution_counts.most_common()),
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "rows": rows,
        "recommended_next_actions": [
            "Use high-priority contradiction rows to downgrade or manually review candidate public priors.",
            "Keep unlinked contradictions as reference-only watch items until project overlap exists.",
            "Do not use procurement/vendor availability as a substitute for SAR contradiction review.",
        ],
    }


def update_public_sar_contradiction_resolution(
    triage_id: str,
    *,
    resolution_status: str,
    review_status: str = "resolved",
    reviewer: str | None = None,
    note: str | None = None,
    triage_path: str | Path = DEFAULT_PUBLIC_SAR_CONTRADICTION_TRIAGE_PATH,
    csv_path: str | Path | None = DEFAULT_PUBLIC_SAR_CONTRADICTION_TRIAGE_CSV_PATH,
    write_back: bool = True,
) -> dict:
    if review_status not in SAR_TRIAGE_REVIEW_STATUSES:
        raise ValueError(f"review_status must be one of {sorted(SAR_TRIAGE_REVIEW_STATUSES)}")
    if resolution_status and resolution_status not in SAR_TRIAGE_RESOLUTIONS:
        raise ValueError(f"resolution_status must be one of {sorted(SAR_TRIAGE_RESOLUTIONS)}")
    report_path = Path(triage_path)
    report = _read_json(report_path)
    rows = [dict(row) for row in report.get("rows") or []]
    now = datetime.now(timezone.utc).isoformat()
    target = None
    for row in rows:
        if str(row.get("triage_id") or "") == str(triage_id):
            target = row
            break
    if target is None:
        raise KeyError(f"Unknown SAR triage id: {triage_id}")
    history = list(target.get("resolution_history") or [])
    event = {
        "changed_at": now,
        "reviewer": reviewer or "",
        "review_status": review_status,
        "resolution_status": resolution_status,
        "resolution_effect": _resolution_effect(resolution_status),
        "note": note or "",
    }
    history.append(event)
    target.update(
        {
            "review_status": review_status,
            "resolution_status": resolution_status,
            "resolution_effect": event["resolution_effect"],
            "resolved_by": reviewer or target.get("resolved_by") or "",
            "resolved_at": now if review_status == "resolved" else target.get("resolved_at") or "",
            "resolution_note": note or "",
            "resolution_history": history,
        }
    )
    for index, row in enumerate(rows):
        if str(row.get("triage_id") or "") == str(triage_id):
            rows[index] = target
            break
    review_counts = Counter(str(row.get("review_status") or "open") for row in rows)
    resolution_counts = Counter(str(row.get("resolution_status") or "unresolved") or "unresolved" for row in rows)
    updated = {
        **report,
        "updated_at": now,
        "rows": rows,
        "review_status_counts": dict(review_counts.most_common()),
        "resolution_status_counts": dict(resolution_counts.most_common()),
    }
    if write_back:
        write_public_sar_contradiction_triage(updated, report_path, csv_path=csv_path)
    return {"status": "updated", "triage_id": triage_id, "event": event, "report": updated}


def _policy_resolution(row: dict) -> tuple[str, str]:
    if _int(row.get("candidate_link_count")):
        return "needs_measurement", "candidate-linked contradiction requires measured project feedback before changing score weights"
    return "reference_only_watch", "no active candidate overlap; keep contradiction out of candidate scoring until overlap exists"


def apply_public_sar_contradiction_resolution_batch(
    *,
    triage_path: str | Path = DEFAULT_PUBLIC_SAR_CONTRADICTION_TRIAGE_PATH,
    csv_path: str | Path | None = DEFAULT_PUBLIC_SAR_CONTRADICTION_TRIAGE_CSV_PATH,
    priority: str = "high",
    reviewer: str = "sar_resolution_policy_v1",
    overwrite_existing: bool = False,
) -> dict:
    report_path = Path(triage_path)
    report = _read_json(report_path)
    rows = [dict(row) for row in report.get("rows") or []]
    now = datetime.now(timezone.utc).isoformat()
    newly_processed_count = 0
    for row in rows:
        if str(row.get("priority") or "") != priority:
            continue
        if row.get("resolution_status") and not overwrite_existing:
            continue
        resolution_status, basis = _policy_resolution(row)
        history = list(row.get("resolution_history") or [])
        event = {
            "changed_at": now,
            "reviewer": reviewer,
            "review_status": "resolved",
            "resolution_status": resolution_status,
            "resolution_effect": _resolution_effect(resolution_status),
            "note": basis,
        }
        history.append(event)
        row.update(
            {
                "review_status": "resolved",
                "resolution_status": resolution_status,
                "resolution_effect": event["resolution_effect"],
                "resolved_by": reviewer,
                "resolved_at": now,
                "resolution_note": basis,
                "resolution_history": history,
            }
        )
        newly_processed_count += 1
    review_counts = Counter(str(row.get("review_status") or "open") for row in rows)
    resolution_counts = Counter(str(row.get("resolution_status") or "unresolved") or "unresolved" for row in rows)
    updated_report = {
        **report,
        "updated_at": now,
        "rows": rows,
        "review_status_counts": dict(review_counts.most_common()),
        "resolution_status_counts": dict(resolution_counts.most_common()),
    }
    write_public_sar_contradiction_triage(updated_report, report_path, csv_path=csv_path)
    priority_rows = [row for row in rows if str(row.get("priority") or "") == priority]
    batch_rows = []
    for row in priority_rows:
        if not row.get("resolution_status"):
            continue
        batch_rows.append(
            {
                "triage_id": row.get("triage_id"),
                "priority": row.get("priority"),
                "triage_action": row.get("triage_action"),
                "source_signal_id": row.get("source_signal_id"),
                "endpoint_group": row.get("endpoint_group"),
                "target_family": row.get("target_family"),
                "candidate_link_count": row.get("candidate_link_count"),
                "net_contradicted": row.get("net_contradicted"),
                "resolution_status": row.get("resolution_status"),
                "resolution_effect": row.get("resolution_effect"),
                "resolution_basis": row.get("resolution_note"),
                "resolved_by": row.get("resolved_by"),
                "resolved_at": row.get("resolved_at"),
            }
        )
    batch_counts = Counter(str(row.get("resolution_status") or "unknown") for row in batch_rows)
    unresolved_priority_count = len(priority_rows) - len(batch_rows)
    batch_status = "resolved" if priority_rows and unresolved_priority_count == 0 else "partial" if batch_rows else "empty"
    batch_report = {
        "created_at": now,
        "status": batch_status,
        "reviewer": reviewer,
        "priority": priority,
        "processed_count": len(batch_rows),
        "newly_processed_count": newly_processed_count,
        "unresolved_priority_count": unresolved_priority_count,
        "candidate_measurement_gated_count": batch_counts.get("needs_measurement", 0),
        "reference_only_watch_count": batch_counts.get("reference_only_watch", 0),
        "resolution_status_counts": dict(batch_counts.most_common()),
        "rows": batch_rows,
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "recommended_next_actions": [
            "Run measurement feedback rows for candidate-linked needs_measurement contradictions.",
            "Keep reference-only contradictions out of candidate scoring until an active candidate or analog-series overlap appears.",
            "Review any future manually changed rows through the SAR resolution UI before profile or scoring activation.",
        ],
    }
    return {"status": batch_report["status"], "report": updated_report, "batch_report": batch_report}


def write_public_sar_contradiction_resolution_batch(
    report: dict,
    output_path: str | Path = DEFAULT_PUBLIC_SAR_CONTRADICTION_RESOLUTION_BATCH_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_PUBLIC_SAR_CONTRADICTION_RESOLUTION_BATCH_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    fieldnames = [
        "triage_id",
        "priority",
        "triage_action",
        "source_signal_id",
        "endpoint_group",
        "target_family",
        "candidate_link_count",
        "net_contradicted",
        "resolution_status",
        "resolution_effect",
        "resolution_basis",
        "resolved_by",
        "resolved_at",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.get("rows") or []:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def build_public_sar_contradiction_watchlist(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    triage_path: str | Path = DEFAULT_PUBLIC_SAR_CONTRADICTION_TRIAGE_PATH,
) -> dict:
    root_path = Path(root)
    report_path = Path(triage_path)
    if not report_path.is_absolute():
        report_path = root_path / report_path
    triage = _read_json(report_path)
    open_rows = [
        dict(row)
        for row in triage.get("rows") or []
        if str(row.get("review_status") or "open") != "resolved" and not str(row.get("resolution_status") or "").strip()
    ]
    actionable = []
    deferred_reference = 0
    for row in open_rows:
        candidate_count = _int(row.get("candidate_link_count"))
        analog_count = _int(row.get("analog_series_link_count"))
        if candidate_count <= 0 and analog_count <= 0:
            deferred_reference += 1
            continue
        review_lane = "candidate_linked" if candidate_count else "analog_series_linked"
        review_action = (
            "resolve_candidate_public_prior_or_measure_endpoint"
            if candidate_count
            else "review_analog_series_overlap_before_candidate_scoring"
        )
        actionable.append(
            {
                "triage_id": row.get("triage_id"),
                "project_name": project_name,
                "priority": row.get("priority"),
                "triage_score": row.get("triage_score"),
                "review_lane": review_lane,
                "review_action": review_action,
                "source_signal_id": row.get("source_signal_id"),
                "endpoint_group": row.get("endpoint_group"),
                "target_family": row.get("target_family"),
                "candidate_link_count": candidate_count,
                "candidate_ids": row.get("candidate_ids"),
                "queue_ids": row.get("queue_ids"),
                "analog_series_link_count": analog_count,
                "analog_series_keys": row.get("analog_series_keys"),
                "contradiction_count": row.get("contradiction_count"),
                "support_count": row.get("support_count"),
                "net_contradicted": row.get("net_contradicted"),
                "review_status": row.get("review_status") or "open",
                "resolution_status": row.get("resolution_status") or "",
                "next_step": (
                    "Move to measurement-gated resolution before any scoring change."
                    if candidate_count
                    else "Keep out of candidate scoring until analog-series overlap is manually confirmed."
                ),
            }
        )
    actionable.sort(
        key=lambda row: (
            {"high": 0, "medium": 1, "low": 2}.get(str(row.get("priority")), 9),
            -_float(row.get("triage_score")),
            str(row.get("triage_id") or ""),
        )
    )
    lane_counts = Counter(str(row.get("review_lane") or "unknown") for row in actionable)
    status = "ready" if actionable else "no_linked_open_rows" if open_rows else "empty"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "project_name": project_name,
        "open_unresolved_count": len(open_rows),
        "actionable_count": len(actionable),
        "candidate_linked_open_count": lane_counts.get("candidate_linked", 0),
        "analog_series_linked_open_count": lane_counts.get("analog_series_linked", 0),
        "deferred_reference_only_count": deferred_reference,
        "review_lane_counts": dict(lane_counts.most_common()),
        "rows": actionable,
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "recommended_next_actions": [
            "Only advance open SAR contradictions with candidate or analog-series overlap.",
            "Leave unlinked reference contradictions out of scoring until overlap appears.",
            "Use measurement-gated resolution for candidate-linked rows before changing priors.",
        ],
    }


def write_public_sar_contradiction_watchlist(
    report: dict,
    output_path: str | Path = DEFAULT_PUBLIC_SAR_CONTRADICTION_WATCHLIST_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_PUBLIC_SAR_CONTRADICTION_WATCHLIST_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    fieldnames = [
        "triage_id",
        "project_name",
        "priority",
        "triage_score",
        "review_lane",
        "review_action",
        "source_signal_id",
        "endpoint_group",
        "target_family",
        "candidate_link_count",
        "candidate_ids",
        "queue_ids",
        "analog_series_link_count",
        "analog_series_keys",
        "contradiction_count",
        "support_count",
        "net_contradicted",
        "review_status",
        "resolution_status",
        "next_step",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.get("rows") or []:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_public_sar_contradiction_triage(
    report: dict,
    output_path: str | Path = DEFAULT_PUBLIC_SAR_CONTRADICTION_TRIAGE_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_PUBLIC_SAR_CONTRADICTION_TRIAGE_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    rows = [dict(row) for row in report.get("rows") or []]
    fieldnames = [
        "triage_id",
        "task_type",
        "project_name",
        "priority",
        "triage_score",
        "triage_action",
        "source_signal_id",
        "signal_key",
        "signal_scope",
        "operator",
        "endpoint_group",
        "target_family",
        "public_evidence_score",
        "public_evidence_count",
        "support_count",
        "contradiction_count",
        "net_contradicted",
        "review_status",
        "resolution_status",
        "resolution_effect",
        "resolved_by",
        "resolved_at",
        "resolution_note",
        "candidate_link_count",
        "analog_series_link_count",
        "candidate_ids",
        "queue_ids",
        "analog_series_keys",
        "source_names",
        "basis",
        "next_step",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
