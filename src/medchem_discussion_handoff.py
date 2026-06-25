from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DISCUSSION_HANDOFF_JSON = Path("data/projects/demo/medchem_discussion_handoff.json")
DEFAULT_DISCUSSION_HANDOFF_CSV = Path("data/projects/demo/medchem_discussion_handoff.csv")
DEFAULT_DISCUSSION_HANDOFF_MD = Path("docs/medchem_discussion_handoff.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _by_candidate(report: dict) -> dict[str, dict]:
    rows = {}
    for row in report.get("rows") or []:
        candidate_id = str(row.get("candidate_id") or "").strip()
        if candidate_id:
            rows[candidate_id] = dict(row)
    return rows


def _limitations(row: dict) -> str:
    limitations = []
    if row.get("risk_bucket") and row.get("risk_bucket") != "clear":
        limitations.append(f"risk={row.get('risk_bucket')}")
    if row.get("baseline_movement") and row.get("baseline_movement") not in {"stable", "unchanged"}:
        limitations.append(f"baseline={row.get('baseline_movement')}")
    try:
        if float(row.get("evidence_depth_score") or 0) < 3:
            limitations.append("thin evidence depth")
    except (TypeError, ValueError):
        limitations.append("missing evidence depth")
    if row.get("local_decision") in {"watch", "needs_measurement", "reject"}:
        limitations.append(f"decision={row.get('local_decision')}")
    return "; ".join(limitations) or "No immediate limitation recorded in local evidence drawer."


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_medchem_discussion_handoff(*, root: str | Path = ".", project_name: str = "demo", max_rows: int = 80) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    drawer = _read_json(project_dir / "candidate_evidence_drawer.json")
    qa = _read_json(project_dir / "candidate_decision_qa.json")
    qa_by_id = _by_candidate(qa)
    decision_priority = {"accept": 0, "watch": 1, "needs_measurement": 2, "defer": 3, "reject": 4}
    rows = sorted(
        drawer.get("rows") or [],
        key=lambda row: (decision_priority.get(str(row.get("local_decision") or ""), 9), -_float(row.get("score"))),
    )
    handoff_rows = []
    for row in rows[: max(1, int(max_rows))]:
        candidate_id = str(row.get("candidate_id") or "")
        qa_row = qa_by_id.get(candidate_id, {})
        limitation = _limitations({**row, **qa_row})
        handoff_rows.append(
            {
                "candidate_id": candidate_id,
                "local_decision": row.get("local_decision", ""),
                "score": row.get("score", ""),
                "smiles": row.get("smiles", ""),
                "site_class": row.get("site_class", ""),
                "decision_rationale": row.get("decision_rationale", ""),
                "evidence_limitations": limitation,
                "qa_bucket": qa_row.get("qa_bucket", ""),
                "baseline_movement": row.get("baseline_movement", ""),
                "evidence_depth_score": row.get("evidence_depth_score", ""),
                "image_path": row.get("image_path", ""),
                "mmp_thumbnail_paths": row.get("mmp_thumbnail_paths", ""),
                "sar_thumbnail_paths": row.get("sar_thumbnail_paths", ""),
                "discussion_prompt": (
                    f"Discuss {candidate_id}: decision={row.get('local_decision')}; "
                    f"site={row.get('site_class')}; limitations={limitation}."
                ),
                "handoff_scope": "medchem_discussion_only",
                "procurement_allowed": False,
                "experiment_execution_allowed": False,
                "feedback_import_allowed": False,
            }
        )
    counts = Counter(str(row.get("local_decision") or "") for row in handoff_rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if handoff_rows else "missing_evidence_drawer",
        "mode": "medchem_discussion_handoff",
        "project_name": project_name,
        "row_count": len(handoff_rows),
        "decision_counts": dict(counts.most_common()),
        "rows": handoff_rows,
        "recommended_next_actions": [
            "Use this handoff for local medchem discussion only.",
            "Do not convert handoff rows into external operational workflows without a separate approved process.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_medchem_discussion_handoff_markdown(report: dict) -> str:
    lines = [
        "# MedChem Discussion Handoff",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows: `{report.get('row_count')}`",
        "",
        "This handoff is for local scientific discussion only. It is not an external workflow plan.",
        "",
        "| ID | Decision | Score | Site | QA | Limitations | Prompt |",
        "| --- | --- | ---: | --- | --- | --- | --- |",
    ]
    for row in (report.get("rows") or [])[:80]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("local_decision") or ""),
                    str(row.get("score") or ""),
                    str(row.get("site_class") or ""),
                    str(row.get("qa_bucket") or ""),
                    str(row.get("evidence_limitations") or "").replace("|", "/"),
                    str(row.get("discussion_prompt") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_medchem_discussion_handoff(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_DISCUSSION_HANDOFF_JSON,
    csv_path: str | Path | None = DEFAULT_DISCUSSION_HANDOFF_CSV,
    markdown_path: str | Path | None = DEFAULT_DISCUSSION_HANDOFF_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "candidate_id",
        "local_decision",
        "score",
        "smiles",
        "site_class",
        "decision_rationale",
        "evidence_limitations",
        "qa_bucket",
        "baseline_movement",
        "evidence_depth_score",
        "image_path",
        "mmp_thumbnail_paths",
        "sar_thumbnail_paths",
        "discussion_prompt",
        "handoff_scope",
        "procurement_allowed",
        "experiment_execution_allowed",
        "feedback_import_allowed",
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
        md_file.write_text(render_medchem_discussion_handoff_markdown(report), encoding="utf-8")
