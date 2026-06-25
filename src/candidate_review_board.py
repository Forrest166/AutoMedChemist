from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REVIEW_BOARD_JSON = Path("data/projects/demo/candidate_review_board.json")
DEFAULT_REVIEW_BOARD_CSV = Path("data/projects/demo/candidate_review_board.csv")
DEFAULT_REVIEW_BOARD_FOCUSED_CSV = Path("data/projects/demo/candidate_review_board_focused.csv")
DEFAULT_REVIEW_BOARD_MD = Path("docs/candidate_review_board.md")
DEFAULT_REVIEW_STATUS_LEDGER_JSON = Path("data/projects/demo/candidate_review_status_ledger.json")
DEFAULT_REVIEW_STATUS_LEDGER_CSV = Path("data/projects/demo/candidate_review_status_ledger.csv")


def _resolve(root: Path, path: str | Path) -> Path:
    item = Path(path)
    return item if item.is_absolute() else root / item


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ledger_paths(root: Path, project_name: str, ledger_json: str | Path | None = None, ledger_csv: str | Path | None = None) -> tuple[Path, Path]:
    project_dir = root / "data" / "projects" / project_name
    return (
        _resolve(root, ledger_json or project_dir / "candidate_review_status_ledger.json"),
        _resolve(root, ledger_csv or project_dir / "candidate_review_status_ledger.csv"),
    )


def _load_decisions(path: Path) -> dict[str, dict[str, Any]]:
    payload = _read_json(path)
    decisions = payload.get("decisions") or {}
    return {str(key): dict(value) for key, value in decisions.items() if isinstance(value, dict)}


def _write_decisions(path: Path, csv_path: Path, project_name: str, decisions: dict[str, dict[str, Any]]) -> dict:
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready",
        "mode": "local_candidate_review_status_ledger",
        "project_name": project_name,
        "decision_count": len(decisions),
        "status_counts": dict(Counter(str(row.get("local_review_status") or "") for row in decisions.values()).most_common()),
        "decisions": decisions,
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }
    _write_json(path, payload)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["candidate_id", "local_review_status", "reviewer", "reviewed_at", "review_note", "history_count"]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for candidate_id, row in sorted(decisions.items()):
            writer.writerow(
                {
                    "candidate_id": candidate_id,
                    "local_review_status": row.get("local_review_status", ""),
                    "reviewer": row.get("reviewer", ""),
                    "reviewed_at": row.get("reviewed_at", ""),
                    "review_note": row.get("review_note", ""),
                    "history_count": len(row.get("history") or []),
                }
            )
    return payload


def _risk_bucket(row: dict[str, Any]) -> str:
    if str(row.get("mmp_contradiction_flags") or "").strip():
        return "contradiction"
    if _float(row.get("risk_score"), 100.0) < 70:
        return "low_risk_score"
    if row.get("blocked_contexts"):
        return "blocked_context"
    if row.get("review_status") == "pending_review":
        return "pending_review"
    return "clear"


def _needs_focused_review(row: dict[str, Any]) -> bool:
    local_status = str(row.get("local_review_status") or "")
    packet_status = str(row.get("review_status") or "")
    risk = str(row.get("risk_bucket") or "")
    return (
        local_status in {"pending_review", "unreviewed", "needs_follow_up", "blocked"}
        or packet_status == "pending_review"
        or risk != "clear"
    )


def _pending_reason(row: dict[str, Any]) -> tuple[str, str]:
    local_status = str(row.get("local_review_status") or "").strip()
    packet_status = str(row.get("review_status") or "").strip()
    risk = str(row.get("risk_bucket") or "").strip()
    blocked_contexts = str(row.get("blocked_contexts") or "").strip()
    mmp_flags = str(row.get("mmp_contradiction_flags") or "").strip()
    review_bucket = str(row.get("review_bucket") or "").strip()
    site_action = str(row.get("site_class_governance_action") or "").strip()
    evidence = str(row.get("evidence_strength") or "").strip().lower()
    reviewer = str(row.get("reviewer") or "").strip()
    if risk == "contradiction" or mmp_flags:
        return "risk_contradiction", f"risk={risk or '-'}; mmp_flags={mmp_flags or '-'}"
    if site_action or review_bucket == "site_class_governance_review":
        return "site_class_governance_review", site_action or "site-class policy requires local review"
    if risk == "blocked_context" or blocked_contexts:
        return "blocked_context", blocked_contexts or "blocked context flagged by review packet"
    if risk == "low_risk_score":
        return "low_risk_score", f"risk_score={row.get('risk_score') or '-'}"
    if "mmp=none" in evidence or "confidence=" in evidence and any(token in evidence for token in ["confidence=0", "confidence=1", "confidence=2", "confidence=3", "confidence=4"]):
        return "thin_evidence", row.get("evidence_strength") or "thin evidence"
    if local_status in {"blocked", "needs_follow_up"}:
        return f"local_{local_status}", f"local_status={local_status}"
    if local_status in {"pending_review", "unreviewed"}:
        return "local_pending_review", f"local_status={local_status}"
    if packet_status == "pending_review":
        return "packet_pending_review", "packet review status is pending"
    if not reviewer and local_status not in {"", "pending_review", "unreviewed"}:
        return "unassigned_reviewer", "local decision exists without reviewer attribution"
    return "manual_review", "manual review attention"


def _visual_rows(root: Path, project_name: str) -> dict[str, dict]:
    visual = _read_json(root / "data" / "projects" / project_name / "candidate_visual_compare.json")
    return {str(row.get("candidate_id") or ""): dict(row) for row in visual.get("rows") or []}


def _match_filter(value: object, expected: str) -> bool:
    expected = expected.strip()
    return not expected or expected == "all" or str(value or "") == expected


def build_candidate_review_board(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    packet_json: str | Path | None = None,
    ledger_json: str | Path | None = None,
    site_class: str = "",
    review_bucket: str = "",
    review_status: str = "",
    local_review_status: str = "",
    risk_bucket: str = "",
    focused_max_rows: int = 80,
) -> dict[str, Any]:
    root_path = Path(root)
    packet_path = _resolve(root_path, packet_json or root_path / "data" / "projects" / project_name / "candidate_review_packet.json")
    ledger_path, _ledger_csv = _ledger_paths(root_path, project_name, ledger_json=ledger_json)
    packet = _read_json(packet_path)
    packet_rows = list(packet.get("rows") or [])
    if not packet_rows:
        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "missing_review_packet",
            "project_name": project_name,
            "row_count": 0,
            "filtered_row_count": 0,
            "rows": [],
            "recommended_next_actions": ["Build the candidate review packet before using the review board."],
            "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
        }
    decisions = _load_decisions(ledger_path)
    visual_by_id = _visual_rows(root_path, project_name)
    rows: list[dict[str, Any]] = []
    for row in packet_rows:
        candidate_id = str(row.get("candidate_id") or "")
        decision = decisions.get(candidate_id) or {}
        visual = visual_by_id.get(candidate_id) or {}
        local_status = str(decision.get("local_review_status") or row.get("review_status") or "unreviewed")
        risk = _risk_bucket(row)
        merged = {
            **row,
            "risk_bucket": risk,
            "local_review_status": local_status,
            "board_status": local_status,
            "reviewer_decision": decision.get("reviewer_decision") or local_status,
            "reviewer": decision.get("reviewer", ""),
            "reviewed_at": decision.get("reviewed_at", ""),
            "review_note": decision.get("review_note", ""),
            "history_count": len(decision.get("history") or []),
            "image_path": visual.get("image_path", ""),
            "highlight_atom_count": visual.get("highlight_atom_count", ""),
            "highlight_legend": visual.get("highlight_legend", ""),
            "highlight_color_legend": visual.get("highlight_color_legend", ""),
            "site_highlight_label": visual.get("site_highlight_label", ""),
            "substitution_change_summary": visual.get("substitution_change_summary", ""),
            "structure_highlight_detail": visual.get("structure_highlight_detail", ""),
            "site_change_token": visual.get("site_change_token", ""),
        }
        pending_reason, pending_detail = _pending_reason(merged)
        merged["pending_reason_cluster"] = pending_reason
        merged["pending_reason_detail"] = pending_detail
        if (
            _match_filter(merged.get("site_class"), site_class)
            and _match_filter(merged.get("review_bucket"), review_bucket)
            and _match_filter(merged.get("review_status"), review_status)
            and _match_filter(merged.get("local_review_status"), local_review_status)
            and _match_filter(merged.get("risk_bucket"), risk_bucket)
        ):
            rows.append(merged)
    focused_rows = [row for row in rows if _needs_focused_review(row)][: max(1, int(focused_max_rows))]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready",
        "mode": "local_candidate_review_board",
        "project_name": project_name,
        "source_packet_status": packet.get("status"),
        "row_count": len(packet_rows),
        "filtered_row_count": len(rows),
        "focused_row_count": len(focused_rows),
        "pending_local_review_count": sum(1 for row in rows if row.get("local_review_status") in {"pending_review", "unreviewed"}),
        "site_class_counts": dict(Counter(str(row.get("site_class") or "unknown") for row in rows).most_common()),
        "review_bucket_counts": dict(Counter(str(row.get("review_bucket") or "unknown") for row in rows).most_common()),
        "local_status_counts": dict(Counter(str(row.get("local_review_status") or "unknown") for row in rows).most_common()),
        "risk_bucket_counts": dict(Counter(str(row.get("risk_bucket") or "unknown") for row in rows).most_common()),
        "pending_reason_counts": dict(Counter(str(row.get("pending_reason_cluster") or "manual_review") for row in focused_rows).most_common()),
        "pending_reason_cluster_count": len({str(row.get("pending_reason_cluster") or "manual_review") for row in focused_rows}),
        "filters": {
            "site_class": site_class,
            "review_bucket": review_bucket,
            "review_status": review_status,
            "local_review_status": local_review_status,
            "risk_bucket": risk_bucket,
        },
        "rows": rows,
        "focused_rows": focused_rows,
        "recommended_next_actions": [
            "Filter by site class, review bucket, and risk bucket before batch-marking local review status.",
            "Open the candidate image and evidence packet for rows with contradictions or blocked contexts.",
            "Treat board status as local governance only; external operational workflows remain blocked.",
        ],
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }


def batch_update_candidate_review_status(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    candidate_ids: list[str],
    local_review_status: str,
    reviewer_decision: str = "",
    reviewer: str = "local_reviewer",
    review_note: str = "",
    ledger_json: str | Path | None = None,
    ledger_csv: str | Path | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    ledger_path, csv_path = _ledger_paths(root_path, project_name, ledger_json=ledger_json, ledger_csv=ledger_csv)
    decisions = _load_decisions(ledger_path)
    stamp = datetime.now(timezone.utc).isoformat()
    ids = [str(item).strip() for item in candidate_ids if str(item).strip()]
    for candidate_id in ids:
        current = decisions.get(candidate_id) or {"candidate_id": candidate_id, "history": []}
        history = list(current.get("history") or [])
        history.append(
            {
                "local_review_status": local_review_status,
                "reviewer_decision": reviewer_decision or local_review_status,
                "reviewer": reviewer,
                "reviewed_at": stamp,
                "review_note": review_note,
            }
        )
        current.update(
            {
                "candidate_id": candidate_id,
                "local_review_status": local_review_status,
                "reviewer_decision": reviewer_decision or local_review_status,
                "reviewer": reviewer,
                "reviewed_at": stamp,
                "review_note": review_note,
                "history": history,
            }
        )
        decisions[candidate_id] = current
    ledger = _write_decisions(ledger_path, csv_path, project_name, decisions)
    return {
        "created_at": stamp,
        "status": "updated",
        "project_name": project_name,
        "updated_count": len(ids),
        "candidate_ids": ids,
        "local_review_status": local_review_status,
        "reviewer_decision": reviewer_decision or local_review_status,
        "ledger_path": str(ledger_path),
        "ledger_csv_path": str(csv_path),
        "ledger_decision_count": ledger.get("decision_count"),
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }


def render_candidate_review_board_markdown(report: dict) -> str:
    lines = [
        "# Candidate Review Board",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Project: `{report.get('project_name')}`",
        f"- Rows: `{report.get('filtered_row_count')}` / `{report.get('row_count')}`",
        f"- Focused rows: `{report.get('focused_row_count')}`",
        f"- Pending local review: `{report.get('pending_local_review_count')}`",
        f"- Pending reason clusters: `{report.get('pending_reason_cluster_count')}`",
        "",
        "| ID | Site | Bucket | Packet Status | Local Status | Risk | Reason | Score | Action |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in (report.get("rows") or [])[:80]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("site_class") or ""),
                    str(row.get("review_bucket") or ""),
                    str(row.get("review_status") or ""),
                    str(row.get("local_review_status") or ""),
                    str(row.get("risk_bucket") or ""),
                    str(row.get("pending_reason_cluster") or ""),
                    str(row.get("score") or ""),
                    str(row.get("proposed_review_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_candidate_review_board(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_REVIEW_BOARD_JSON,
    csv_path: str | Path | None = DEFAULT_REVIEW_BOARD_CSV,
    focused_csv_path: str | Path | None = DEFAULT_REVIEW_BOARD_FOCUSED_CSV,
    markdown_path: str | Path | None = DEFAULT_REVIEW_BOARD_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "candidate_id",
        "rank",
        "score",
        "smiles",
        "site_class",
        "review_bucket",
        "review_status",
        "local_review_status",
        "board_status",
        "reviewer_decision",
        "risk_bucket",
        "risk_score",
        "reviewer",
        "reviewed_at",
        "review_note",
        "blocked_contexts",
        "evidence_strength",
        "proposed_review_action",
        "image_path",
        "highlight_atom_count",
        "highlight_legend",
        "highlight_color_legend",
        "site_highlight_label",
        "substitution_change_summary",
        "structure_highlight_detail",
        "site_change_token",
        "pending_reason_cluster",
        "pending_reason_detail",
    ]
    if csv_path:
        csv_file = Path(csv_path)
        csv_file.parent.mkdir(parents=True, exist_ok=True)
        with csv_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in report.get("rows") or []:
                writer.writerow({field: row.get(field, "") for field in fields})
    if focused_csv_path:
        focused_file = Path(focused_csv_path)
        if not focused_file.is_absolute() and Path(json_path).is_absolute():
            focused_file = Path(json_path).parent / focused_file.name
        focused_file.parent.mkdir(parents=True, exist_ok=True)
        with focused_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in report.get("focused_rows") or []:
                writer.writerow({field: row.get(field, "") for field in fields})
    if markdown_path:
        md_file = Path(markdown_path)
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(render_candidate_review_board_markdown(report), encoding="utf-8")
