from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CANDIDATE_EXPLANATION_MATRIX_JSON = Path("data/projects/demo/candidate_explanation_matrix.json")
DEFAULT_CANDIDATE_EXPLANATION_MATRIX_CSV = Path("data/projects/demo/candidate_explanation_matrix.csv")
DEFAULT_CANDIDATE_EXPLANATION_MATRIX_MD = Path("docs/candidate_explanation_matrix.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]


COMPONENTS = [
    "score_component",
    "evidence_component",
    "qa_component",
    "baseline_component",
    "remediation_component",
]


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: object) -> int:
    return int(_number(value))


def _rank_key(row: dict[str, Any]) -> tuple[float, str]:
    rank = _number(row.get("rank"))
    if rank <= 0:
        rank = 999999
    return (rank, str(row.get("candidate_id") or ""))


def _bucket(row: dict[str, Any]) -> tuple[str, int]:
    open_tasks = _int(row.get("open_remediation_count"))
    qa = str(row.get("qa_bucket") or "").lower()
    evidence = _number(row.get("evidence_component"))
    if open_tasks or qa not in {"clear", "evidence_supported", "ready", "missing"}:
        return "stoplist", 3 + open_tasks
    if evidence < 50:
        return "thin_evidence", 2
    return "review_ready", 0


def build_candidate_explanation_matrix(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    candidate_ids: list[str] | None = None,
    max_candidates: int = 12,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    panel = _read_json(project_dir / "candidate_explanation_panel.json")
    panel_rows = [dict(row) for row in panel.get("rows") or []]
    id_filter = {str(item).strip() for item in (candidate_ids or []) if str(item).strip()}
    if id_filter:
        selected_rows = [row for row in panel_rows if str(row.get("candidate_id") or "") in id_filter]
    else:
        selected_rows = sorted(panel_rows, key=_rank_key)[: max(1, int(max_candidates))]

    rows: list[dict[str, Any]] = []
    for index, source in enumerate(selected_rows, start=1):
        bucket, stoplist_score = _bucket(source)
        component_values = [_number(source.get(component)) for component in COMPONENTS]
        component_mean = round(sum(component_values) / max(1, len(component_values)), 2)
        row = {
            "matrix_rank": index,
            "candidate_id": source.get("candidate_id", ""),
            "rank": source.get("rank", ""),
            "score": source.get("score", ""),
            "site_class": source.get("site_class", ""),
            "local_decision": source.get("local_decision", ""),
            "decision_confidence": source.get("decision_confidence", ""),
            "qa_bucket": source.get("qa_bucket", ""),
            "baseline_lineage_status": source.get("baseline_lineage_status", ""),
            "open_remediation_count": source.get("open_remediation_count", 0),
            "evidence_summary": source.get("evidence_summary", ""),
            "component_mean": component_mean,
            "matrix_bucket": bucket,
            "stoplist_score": stoplist_score,
            "score_component": source.get("score_component", ""),
            "evidence_component": source.get("evidence_component", ""),
            "qa_component": source.get("qa_component", ""),
            "baseline_component": source.get("baseline_component", ""),
            "remediation_component": source.get("remediation_component", ""),
            "next_action": source.get("next_action", ""),
        }
        rows.append(row)

    pairwise_delta_rows: list[dict[str, Any]] = []
    if rows:
        base = rows[0]
        for row in rows[1:]:
            pairwise_delta_rows.append(
                {
                    "base_candidate_id": base.get("candidate_id", ""),
                    "head_candidate_id": row.get("candidate_id", ""),
                    "score_delta": round(_number(row.get("score")) - _number(base.get("score")), 4),
                    "component_mean_delta": round(_number(row.get("component_mean")) - _number(base.get("component_mean")), 4),
                    "stoplist_delta": _int(row.get("stoplist_score")) - _int(base.get("stoplist_score")),
                    "qa_changed": str(row.get("qa_bucket") or "") != str(base.get("qa_bucket") or ""),
                    "baseline_changed": str(row.get("baseline_lineage_status") or "") != str(base.get("baseline_lineage_status") or ""),
                }
            )

    bucket_counts = Counter(str(row.get("matrix_bucket") or "") for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "mode": "candidate_explanation_matrix",
        "project_name": project_name,
        "row_count": len(rows),
        "candidate_count": len(rows),
        "component_count": len(COMPONENTS),
        "pairwise_delta_count": len(pairwise_delta_rows),
        "stoplist_candidate_count": bucket_counts.get("stoplist", 0),
        "matrix_bucket_counts": dict(bucket_counts.most_common()),
        "rows": rows,
        "pairwise_delta_rows": pairwise_delta_rows,
        "recommended_next_actions": [
            "Use the N-way matrix to compare local evidence, QA, baseline movement, and open remediation across a selected candidate set.",
            "Treat stoplist rows as local review blockers before discussion handoff.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_candidate_explanation_matrix_markdown(report: dict) -> str:
    lines = [
        "# Candidate Explanation Matrix",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Candidates: `{report.get('candidate_count')}`",
        f"- Stop-list candidates: `{report.get('stoplist_candidate_count')}`",
        "",
        "| Candidate | Rank | Score | Bucket | Mean | QA | Baseline | Open Tasks | Next Action |",
        "| --- | ---: | ---: | --- | ---: | --- | --- | ---: | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("rank") or ""),
                    str(row.get("score") or ""),
                    str(row.get("matrix_bucket") or ""),
                    str(row.get("component_mean") or ""),
                    str(row.get("qa_bucket") or ""),
                    str(row.get("baseline_lineage_status") or ""),
                    str(row.get("open_remediation_count") or 0),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_candidate_explanation_matrix(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_CANDIDATE_EXPLANATION_MATRIX_JSON,
    csv_path: str | Path | None = DEFAULT_CANDIDATE_EXPLANATION_MATRIX_CSV,
    markdown_path: str | Path | None = DEFAULT_CANDIDATE_EXPLANATION_MATRIX_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "matrix_rank",
        "candidate_id",
        "rank",
        "score",
        "site_class",
        "local_decision",
        "decision_confidence",
        "qa_bucket",
        "baseline_lineage_status",
        "open_remediation_count",
        "evidence_summary",
        "component_mean",
        "matrix_bucket",
        "stoplist_score",
        "score_component",
        "evidence_component",
        "qa_component",
        "baseline_component",
        "remediation_component",
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
        md_file.write_text(render_candidate_explanation_matrix_markdown(report), encoding="utf-8")
