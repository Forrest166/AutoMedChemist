from __future__ import annotations

import csv
import json
from pathlib import Path

from .ring_outcome_overlay import (
    DEFAULT_RING_OUTCOME_OVERLAY_PATH,
    RING_ENUMERATION_TYPES,
    _candidate_context,
    _float,
    ring_context_id,
)


DEFAULT_RING_OUTCOME_OVERLAY_REPLAY_PATH = Path("data/projects/demo/ring_outcome_overlay_replay.json")
DEFAULT_RING_OUTCOME_OVERLAY_REPLAY_CSV_PATH = Path("data/projects/demo/ring_outcome_overlay_replay.csv")


def _load_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_csv_rows(path: str | Path) -> list[dict]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _candidate_files(root: Path, patterns: list[str] | tuple[str, ...] | None) -> list[Path]:
    patterns = list(patterns or ["data/projects/**/candidates.csv"])
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(root.glob(pattern))
    return sorted(dict.fromkeys(path for path in paths if path.exists()))


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def _base_score(row: dict) -> float:
    score = _float(row.get("score"))
    current_delta = _float(row.get("ring_outcome_learning_score_delta"))
    return _clamp_score(score - current_delta)


def _candidate_id(row: dict, index: int) -> str:
    return str(row.get("candidate_id") or row.get("id") or f"row-{index}")


def _rank(rows: list[dict], score_field: str, rank_field: str) -> None:
    for rank, row in enumerate(
        sorted(rows, key=lambda item: (-_float(item.get(score_field)), str(item.get("candidate_id") or ""))),
        start=1,
    ):
        row[rank_field] = rank


def _materialize_replay_rows(
    candidate_rows: list[dict],
    *,
    source_path: str,
    contexts: dict[str, dict],
    target_context: dict | None = None,
) -> list[dict]:
    rows = []
    for index, row in enumerate(candidate_rows, start=1):
        if row.get("enumeration_type") not in RING_ENUMERATION_TYPES:
            continue
        context_id = str(row.get("ring_outcome_learning_context_id") or "").strip()
        if not context_id:
            context_id = ring_context_id(_candidate_context(row, target_context))
        context = contexts.get(context_id, {})
        base_score = _base_score(row)
        current_adjustment = _float(row.get("ring_outcome_learning_score_delta"))
        active_adjustment = _float(context.get("active_score_adjustment"))
        proposed_adjustment = _float(context.get("proposed_score_adjustment"))
        replay_score = _clamp_score(base_score + active_adjustment)
        proposed_score = _clamp_score(base_score + proposed_adjustment)
        rows.append(
            {
                "source_path": source_path,
                "candidate_id": _candidate_id(row, index),
                "smiles": row.get("smiles") or row.get("canonical_smiles") or "",
                "enumeration_type": row.get("enumeration_type"),
                "replacement_label": row.get("replacement_label"),
                "replacement_class": row.get("replacement_class") or "unspecified",
                "ring_outcome_context_id": context_id,
                "overlay_gate_status": context.get("gate_status") or "no_context",
                "overlay_gate_reasons": context.get("gate_reasons") or "",
                "learning_action": context.get("learning_action") or "",
                "observed_count": context.get("observed_count") or "",
                "hit_rate": context.get("hit_rate") or "",
                "current_ring_adjustment": round(current_adjustment, 4),
                "active_ring_adjustment": round(active_adjustment, 4),
                "proposed_ring_adjustment": round(proposed_adjustment, 4),
                "base_score": round(base_score, 4),
                "current_score": round(_float(row.get("score")), 4),
                "replay_score": round(replay_score, 4),
                "proposed_replay_score": round(proposed_score, 4),
                "score_delta_vs_current": round(replay_score - _float(row.get("score")), 4),
                "proposed_score_delta_vs_current": round(proposed_score - _float(row.get("score")), 4),
            }
        )
    _rank(rows, "base_score", "base_rank")
    _rank(rows, "current_score", "current_rank")
    _rank(rows, "replay_score", "replay_rank")
    _rank(rows, "proposed_replay_score", "proposed_replay_rank")
    for row in rows:
        row["replay_rank_delta_vs_current"] = int(row.get("current_rank") or 0) - int(row.get("replay_rank") or 0)
        row["proposed_rank_delta_vs_current"] = int(row.get("current_rank") or 0) - int(row.get("proposed_replay_rank") or 0)
    rows.sort(
        key=lambda item: (
            -abs(_float(item.get("score_delta_vs_current"))),
            -abs(int(item.get("replay_rank_delta_vs_current") or 0)),
            str(item.get("source_path") or ""),
            int(item.get("replay_rank") or 999999),
        )
    )
    return rows


def build_ring_outcome_overlay_replay(
    *,
    root: str | Path = Path("."),
    overlay_path: str | Path = DEFAULT_RING_OUTCOME_OVERLAY_PATH,
    candidate_globs: list[str] | tuple[str, ...] | None = None,
    target_context: dict | None = None,
    candidate_rows: list[dict] | None = None,
) -> dict:
    root_path = Path(root)
    overlay = _load_json(overlay_path)
    contexts = {str(row.get("context_id") or ""): dict(row) for row in overlay.get("contexts") or [] if row.get("context_id")}
    source_reports = []
    all_rows: list[dict] = []
    if candidate_rows is not None:
        rows = _materialize_replay_rows(
            [dict(row) for row in candidate_rows],
            source_path="provided_rows",
            contexts=contexts,
            target_context=target_context,
        )
        source_reports.append({"source_path": "provided_rows", "candidate_count": len(candidate_rows), "ring_candidate_count": len(rows)})
        all_rows.extend(rows)
    else:
        for path in _candidate_files(root_path, candidate_globs):
            raw_rows = _read_csv_rows(path)
            rows = _materialize_replay_rows(
                raw_rows,
                source_path=str(path),
                contexts=contexts,
                target_context=target_context,
            )
            source_reports.append({"source_path": str(path), "candidate_count": len(raw_rows), "ring_candidate_count": len(rows)})
            all_rows.extend(rows)

    active_context_count = sum(1 for row in contexts.values() if row.get("gate_status") == "active")
    matched_count = sum(1 for row in all_rows if row.get("overlay_gate_status") != "no_context")
    affected_count = sum(1 for row in all_rows if abs(_float(row.get("score_delta_vs_current"))) > 0)
    proposed_affected_count = sum(1 for row in all_rows if abs(_float(row.get("proposed_score_delta_vs_current"))) > 0)
    max_abs_score_delta = max([abs(_float(row.get("score_delta_vs_current"))) for row in all_rows] or [0.0])
    max_abs_rank_delta = max([abs(int(row.get("replay_rank_delta_vs_current") or 0)) for row in all_rows] or [0])
    max_abs_proposed_score_delta = max([abs(_float(row.get("proposed_score_delta_vs_current"))) for row in all_rows] or [0.0])
    max_abs_proposed_rank_delta = max([abs(int(row.get("proposed_rank_delta_vs_current") or 0)) for row in all_rows] or [0])
    if not source_reports:
        status = "no_candidate_files"
    elif not all_rows:
        status = "no_ring_candidates"
    elif not contexts:
        status = "no_overlay_contexts"
    elif active_context_count <= 0:
        status = "no_active_overlay"
    else:
        status = "ready"
    return {
        "status": status,
        "overlay_path": str(Path(overlay_path)),
        "overlay_context_count": len(contexts),
        "active_context_count": active_context_count,
        "candidate_source_count": len(source_reports),
        "candidate_count": sum(int(row.get("candidate_count") or 0) for row in source_reports),
        "ring_candidate_count": len(all_rows),
        "matched_context_count": matched_count,
        "affected_candidate_count": affected_count,
        "proposed_affected_candidate_count": proposed_affected_count,
        "max_abs_score_delta": round(max_abs_score_delta, 4),
        "max_abs_rank_delta": max_abs_rank_delta,
        "max_abs_proposed_score_delta": round(max_abs_proposed_score_delta, 4),
        "max_abs_proposed_rank_delta": max_abs_proposed_rank_delta,
        "source_reports": source_reports,
        "top_score_movers": all_rows[:25],
        "rows": all_rows,
        "recommended_next_actions": [
            "Review proposed_replay_score and proposed_rank_delta_vs_current before approving any blocked overlay context.",
            "Only activate overlay contexts after observed outcomes meet the minimum count and review approval gates.",
            "Rebuild candidate queues after approval so score_after_ring_outcome_learning is persisted in new exports.",
        ],
    }


def write_ring_outcome_overlay_replay(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_RING_OUTCOME_OVERLAY_REPLAY_PATH,
    csv_path: str | Path | None = DEFAULT_RING_OUTCOME_OVERLAY_REPLAY_CSV_PATH,
) -> None:
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    rows = [dict(row) for row in report.get("rows") or []]
    fields = [
        "source_path",
        "candidate_id",
        "smiles",
        "enumeration_type",
        "replacement_label",
        "replacement_class",
        "ring_outcome_context_id",
        "overlay_gate_status",
        "overlay_gate_reasons",
        "learning_action",
        "observed_count",
        "hit_rate",
        "current_ring_adjustment",
        "active_ring_adjustment",
        "proposed_ring_adjustment",
        "base_rank",
        "current_rank",
        "replay_rank",
        "proposed_replay_rank",
        "replay_rank_delta_vs_current",
        "proposed_rank_delta_vs_current",
        "base_score",
        "current_score",
        "replay_score",
        "proposed_replay_score",
        "score_delta_vs_current",
        "proposed_score_delta_vs_current",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
