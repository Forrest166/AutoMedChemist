from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CANDIDATE_EXPLANATION_COMPARE_JSON = Path("data/projects/demo/candidate_explanation_compare.json")
DEFAULT_CANDIDATE_EXPLANATION_COMPARE_CSV = Path("data/projects/demo/candidate_explanation_compare.csv")
DEFAULT_CANDIDATE_EXPLANATION_COMPARE_MD = Path("docs/candidate_explanation_compare.md")
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


def _number(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _short(value: object, limit: int = 220) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _pick_rows(panel_rows: list[dict[str, Any]], base_candidate_id: str | None, head_candidate_id: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    by_id = {str(row.get("candidate_id") or ""): dict(row) for row in panel_rows}
    base = by_id.get(str(base_candidate_id or "").strip(), {}) if base_candidate_id else {}
    head = by_id.get(str(head_candidate_id or "").strip(), {}) if head_candidate_id else {}
    if not base and panel_rows:
        base = dict(panel_rows[0])
    if not head:
        for row in panel_rows:
            if str(row.get("candidate_id") or "") != str(base.get("candidate_id") or ""):
                head = dict(row)
                break
    return base, head


def _component(component: str, base: object, head: object, *, next_action: str = "") -> dict[str, Any]:
    base_num = _number(base)
    head_num = _number(head)
    delta = "" if base_num is None or head_num is None else round(head_num - base_num, 6)
    if delta == "":
        direction = "same" if str(base or "") == str(head or "") else "changed"
    elif float(delta) > 0:
        direction = "higher"
    elif float(delta) < 0:
        direction = "lower"
    else:
        direction = "same"
    return {
        "component": component,
        "base_value": _short(base),
        "head_value": _short(head),
        "delta": delta,
        "direction": direction,
        "next_action": next_action,
    }


def build_candidate_explanation_compare(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    base_candidate_id: str | None = None,
    head_candidate_id: str | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    panel = _read_json(project_dir / "candidate_explanation_panel.json")
    rows = [dict(row) for row in panel.get("rows") or []]
    base, head = _pick_rows(rows, base_candidate_id, head_candidate_id)
    base_id = str(base.get("candidate_id") or "")
    head_id = str(head.get("candidate_id") or "")
    compare_rows = [
        _component("score", base.get("score"), head.get("score"), next_action="Review score delta together with evidence and QA differences."),
        _component("rank", base.get("rank"), head.get("rank"), next_action="Lower rank number is better; inspect movement before selecting a lead discussion row."),
        _component("site_class", base.get("site_class"), head.get("site_class"), next_action="Different site classes may require different local review rules."),
        _component("local_decision", base.get("local_decision"), head.get("local_decision"), next_action="Decision mismatch should be reviewed before handoff."),
        _component("decision_confidence", base.get("decision_confidence"), head.get("decision_confidence"), next_action="Prefer explicit evidence over confidence alone."),
        _component("evidence_depth_score", base.get("evidence_depth_score"), head.get("evidence_depth_score"), next_action="Thin evidence should remain a review stop list item."),
        _component("evidence_summary", base.get("evidence_summary"), head.get("evidence_summary"), next_action="Compare evidence limitations and contradiction flags."),
        _component("baseline_lineage_status", base.get("baseline_lineage_status"), head.get("baseline_lineage_status"), next_action="Changed or entered rows need baseline context before promotion discussion."),
        _component("baseline_changed_fields", base.get("baseline_changed_fields"), head.get("baseline_changed_fields"), next_action="Use changed fields to explain why recommendation context moved."),
        _component("qa_bucket", base.get("qa_bucket"), head.get("qa_bucket"), next_action="Non-clear QA buckets block unqualified recommendation language."),
        _component("open_remediation_count", base.get("open_remediation_count"), head.get("open_remediation_count"), next_action="Open remediation count is a local stop-list signal."),
        _component("next_action", base.get("next_action"), head.get("next_action"), next_action="Use the stricter next action when candidates are otherwise similar."),
    ]
    stoplist_components = [
        row["component"]
        for row in compare_rows
        if row["component"] in {"qa_bucket", "open_remediation_count", "evidence_summary", "baseline_lineage_status"}
        and row["direction"] != "same"
    ]
    status = "ready" if base_id and head_id else "needs_two_candidates"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "candidate_explanation_compare",
        "project_name": project_name,
        "base_candidate_id": base_id,
        "head_candidate_id": head_id,
        "row_count": len(compare_rows) if status == "ready" else 0,
        "different_component_count": sum(1 for row in compare_rows if row["direction"] != "same") if status == "ready" else 0,
        "stoplist_component_count": len(stoplist_components),
        "stoplist_components": stoplist_components,
        "rows": compare_rows if status == "ready" else [],
        "recommended_next_actions": [
            "Use explanation comparison to choose which candidate needs deeper local review, not to automate procurement or experiment feedback.",
            "Treat non-clear QA, thinner evidence, and open remediation as stronger stop-list signals than raw score deltas.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_candidate_explanation_compare_markdown(report: dict) -> str:
    lines = [
        "# Candidate Explanation Compare",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Base -> head: `{report.get('base_candidate_id')}` -> `{report.get('head_candidate_id')}`",
        f"- Different components: `{report.get('different_component_count')}`",
        "",
        "| Component | Base | Head | Delta | Direction | Next Action |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("component") or ""),
                    str(row.get("base_value") or "").replace("|", "/"),
                    str(row.get("head_value") or "").replace("|", "/"),
                    str(row.get("delta") or ""),
                    str(row.get("direction") or ""),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_candidate_explanation_compare(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_CANDIDATE_EXPLANATION_COMPARE_JSON,
    csv_path: str | Path | None = DEFAULT_CANDIDATE_EXPLANATION_COMPARE_CSV,
    markdown_path: str | Path | None = DEFAULT_CANDIDATE_EXPLANATION_COMPARE_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = ["component", "base_value", "head_value", "delta", "direction", "next_action"]
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
        md_file.write_text(render_candidate_explanation_compare_markdown(report), encoding="utf-8")
