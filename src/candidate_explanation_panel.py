from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - optional chart rendering
    Image = None
    ImageDraw = None
    ImageFont = None


DEFAULT_CANDIDATE_EXPLANATION_PANEL_JSON = Path("data/projects/demo/candidate_explanation_panel.json")
DEFAULT_CANDIDATE_EXPLANATION_PANEL_CSV = Path("data/projects/demo/candidate_explanation_panel.csv")
DEFAULT_CANDIDATE_EXPLANATION_PANEL_MD = Path("docs/candidate_explanation_panel.md")
DEFAULT_CANDIDATE_EXPLANATION_CHART_DIR = Path("data/projects/demo/candidate_explanation_charts")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]


def _resolve(root: Path, path: str | Path) -> Path:
    item = Path(path)
    return item if item.is_absolute() else root / item


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _by_candidate(report: dict, *, keys: tuple[str, ...] = ("candidate_id", "candidate_key", "source_id")) -> dict[str, dict]:
    rows = {}
    for row in report.get("rows") or []:
        for key in keys:
            candidate_id = str(row.get(key) or "").strip()
            if candidate_id:
                rows[candidate_id] = dict(row)
                break
    return rows


def _group_remediation(report: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in report.get("rows") or []:
        candidate_id = str(row.get("source_id") or "").strip()
        if not candidate_id:
            target = str(row.get("target_filter") or "")
            for part in target.split(";"):
                key, _, value = part.partition("=")
                if key.strip() == "candidate_id":
                    candidate_id = value.strip()
                    break
        if candidate_id:
            grouped[candidate_id].append(dict(row))
    return grouped


def _join(values: list[object], limit: int = 7) -> str:
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return " | ".join(out[:limit])


def _safe_id(value: object) -> str:
    text = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in str(value or "candidate"))
    return text.strip("._-") or "candidate"


def _score(value: object, default: float = 0.0) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    if 0 < score <= 1:
        score *= 100
    elif 1 < score <= 10:
        score *= 10
    return round(max(0.0, min(100.0, score)), 2)


def _qa_score(qa_bucket: object) -> float:
    value = str(qa_bucket or "").lower()
    if not value or value == "missing":
        return 55.0
    if value in {"clear", "evidence_supported", "ready"}:
        return 100.0
    if any(token in value for token in ["blocked", "stop", "fail"]):
        return 25.0
    if any(token in value for token in ["stale", "attention", "follow", "review", "pending"]):
        return 45.0
    return 70.0


def _baseline_score(lineage_status: object) -> float:
    value = str(lineage_status or "").lower()
    if not value or value in {"missing", "unknown"}:
        return 65.0
    if value in {"unchanged", "current", "clear", "stable"}:
        return 100.0
    if "changed" in value:
        return 60.0
    if any(token in value for token in ["entered", "exited", "removed", "added"]):
        return 45.0
    return 75.0


def _remediation_score(open_count: int) -> float:
    return round(max(0.0, 100.0 - 25.0 * max(0, open_count)), 2)


def _component_scores(source: dict, drawer_row: dict, qa_bucket: object, lineage_status: object, open_remediation_count: int) -> dict[str, float]:
    return {
        "score_component": _score(source.get("score") or drawer_row.get("score")),
        "evidence_component": _score(drawer_row.get("evidence_depth_score"), 60.0 if drawer_row.get("evidence_context_summary") or drawer_row.get("drawer_summary") else 35.0),
        "qa_component": _qa_score(qa_bucket),
        "baseline_component": _baseline_score(lineage_status),
        "remediation_component": _remediation_score(open_remediation_count),
    }


def _font(size: int, *, bold: bool = False):
    if ImageFont is None:
        return None
    names = ("seguisb.ttf", "segoeuib.ttf") if bold else ("segoeui.ttf", "arial.ttf")
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _write_breakdown_png(path: Path, candidate_id: str, components: dict[str, float], *, title: str = "Candidate Score Breakdown") -> bool:
    if Image is None or ImageDraw is None:
        return False
    labels = [
        ("Score", "score_component", "#2563EB"),
        ("Evidence", "evidence_component", "#0F766E"),
        ("QA", "qa_component", "#B45309"),
        ("Baseline", "baseline_component", "#7C3AED"),
        ("Remediation", "remediation_component", "#BE123C"),
    ]
    width = 980
    height = 330
    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    title_font = _font(30, bold=True)
    text_font = _font(20)
    small_font = _font(18)
    draw.text((32, 26), f"{title}: {candidate_id}", fill="#17202A", font=title_font)
    draw.text((32, 66), "Local-only explanation components; not a procurement or experiment trigger.", fill="#52616F", font=small_font)
    y = 112
    for label, key, color in labels:
        value = float(components.get(key) or 0)
        draw.text((32, y - 4), label, fill="#17202A", font=text_font)
        draw.rectangle((180, y, 860, y + 22), fill="#E9EEF2")
        draw.rounded_rectangle((180, y, 180 + int(680 * value / 100), y + 22), radius=5, fill=color)
        draw.text((880, y - 4), f"{value:.0f}", fill="#17202A", font=text_font)
        y += 38
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    return True


def _write_summary_png(path: Path, rows: list[dict[str, Any]]) -> bool:
    if Image is None or ImageDraw is None:
        return False
    rows = rows[:12]
    width = 1180
    height = max(360, 128 + 52 * max(1, len(rows)))
    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    title_font = _font(32, bold=True)
    text_font = _font(18)
    draw.text((34, 28), "Candidate Explanation Components", fill="#17202A", font=title_font)
    draw.text((34, 70), "Score / evidence / QA / baseline / remediation component overview", fill="#52616F", font=text_font)
    colors = [
        ("score_component", "#2563EB"),
        ("evidence_component", "#0F766E"),
        ("qa_component", "#B45309"),
        ("baseline_component", "#7C3AED"),
        ("remediation_component", "#BE123C"),
    ]
    y = 122
    for row in rows:
        draw.text((34, y - 2), _safe_id(row.get("candidate_id"))[:24], fill="#17202A", font=text_font)
        x = 280
        for key, color in colors:
            value = float(row.get(key) or 0)
            width_px = int(126 * value / 100)
            draw.rectangle((x, y, x + 126, y + 18), fill="#E9EEF2")
            draw.rounded_rectangle((x, y, x + max(3, width_px), y + 18), radius=4, fill=color)
            x += 156
        y += 52
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    return True


def build_candidate_explanation_panel(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    candidates_csv: str | Path | None = None,
    max_rows: int = 160,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = Path("data/projects") / project_name
    project_abs = root_path / project_dir
    chart_dir = project_abs / "candidate_explanation_charts"
    candidates = _read_csv_rows(_resolve(root_path, candidates_csv or project_dir / "candidates.csv"))
    drawer = _read_json(project_abs / "candidate_evidence_drawer.json")
    decision_qa = _read_json(project_abs / "candidate_decision_qa.json")
    baseline_lineage = _read_json(project_abs / "baseline_lineage_compare.json")
    remediation = _read_json(project_abs / "review_remediation_queue.json") or _read_json(project_abs / "candidate_remediation_queue.json")
    command_center = _read_json(project_abs / "review_command_center.json")

    drawer_by_id = _by_candidate(drawer)
    qa_by_id = _by_candidate(decision_qa)
    lineage_by_id = _by_candidate(baseline_lineage)
    remediation_by_id = _group_remediation(remediation)
    command_by_candidate: dict[str, list[dict]] = defaultdict(list)
    for row in command_center.get("rows") or []:
        candidate_id = str(row.get("candidate_id") or "").strip()
        if candidate_id:
            command_by_candidate[candidate_id].append(dict(row))

    rows: list[dict[str, Any]] = []
    for source in candidates[: max(1, int(max_rows))]:
        candidate_id = str(source.get("candidate_id") or "").strip()
        drawer_row = drawer_by_id.get(candidate_id, {})
        qa_row = qa_by_id.get(candidate_id, {})
        lineage_row = lineage_by_id.get(candidate_id, {})
        remediation_rows = remediation_by_id.get(candidate_id, [])
        command_rows = command_by_candidate.get(candidate_id, [])
        open_remediation = [
            row
            for row in remediation_rows
            if str(row.get("closure_status") or row.get("status") or "open")
            in {"open", "reopened", "needs_follow_up", "blocked"}
        ]
        task_ids = [row.get("task_id") for row in remediation_rows]
        command_ids = [row.get("command_id") for row in command_rows]
        qa_bucket = qa_row.get("qa_bucket") or ""
        lineage_status = lineage_row.get("lineage_status") or lineage_row.get("status") or drawer_row.get("baseline_status") or ""
        components = _component_scores(source, drawer_row, qa_bucket or "clear", lineage_status, len(open_remediation))
        breakdown_path = chart_dir / f"{_safe_id(candidate_id)}.png"
        preview_path = str(breakdown_path.resolve()) if _write_breakdown_png(breakdown_path, candidate_id, components) else ""
        explanation_trace = _join(
            [
                f"score={source.get('score') or drawer_row.get('score')}",
                f"decision={drawer_row.get('local_decision')}",
                f"evidence={drawer_row.get('evidence_context_summary') or drawer_row.get('drawer_summary')}",
                f"baseline={lineage_status or drawer_row.get('baseline_movement')}",
                f"qa={qa_bucket or 'clear'}",
                f"remediation_open={len(open_remediation)}",
            ]
        )
        next_action = (
            qa_row.get("next_action")
            or (open_remediation[0].get("next_action") if open_remediation else "")
            or drawer_row.get("next_action")
            or "No panel action required."
        )
        rows.append(
            {
                "candidate_id": candidate_id,
                "rank": source.get("rank", ""),
                "score": source.get("score") or drawer_row.get("score", ""),
                "smiles": source.get("smiles", ""),
                "site_class": source.get("site_class") or drawer_row.get("site_class", ""),
                "local_decision": drawer_row.get("local_decision", ""),
                "decision_confidence": drawer_row.get("decision_confidence", ""),
                "evidence_summary": drawer_row.get("evidence_context_summary") or drawer_row.get("drawer_summary", ""),
                "evidence_depth_score": drawer_row.get("evidence_depth_score", ""),
                "baseline_lineage_status": lineage_status,
                "baseline_changed_fields": lineage_row.get("changed_fields") or drawer_row.get("changed_fields", ""),
                "qa_bucket": qa_bucket or "missing",
                "qa_reason": qa_row.get("qa_reason", ""),
                "open_remediation_count": len(open_remediation),
                "remediation_task_ids": ";".join(str(item or "") for item in task_ids if item),
                "command_ids": ";".join(str(item or "") for item in command_ids if item),
                **components,
                "explanation_score_vector": ";".join(f"{key}={value}" for key, value in components.items()),
                "breakdown_chart_path": preview_path,
                "breakdown_preview_path": preview_path,
                "explanation_trace": explanation_trace,
                "panel_sections": "score;evidence;baseline;decision_qa;remediation",
                "next_action": next_action,
                "export_scope": "local_candidate_explanation",
                "procurement_allowed": False,
                "feedback_import_allowed": False,
            }
        )

    qa_counts = Counter(str(row.get("qa_bucket") or "") for row in rows)
    remediation_linked_count = sum(1 for row in rows if int(row.get("open_remediation_count") or 0) > 0)
    summary_chart = chart_dir / "candidate_explanation_score_breakdown.png"
    summary_path = str(summary_chart.resolve()) if _write_summary_png(summary_chart, rows) else ""
    chart_rows = [
        {
            "chart_id": "candidate_explanation_score_breakdown",
            "label": "Candidate explanation score breakdown",
            "status": "ready" if summary_path else "preview_unavailable",
            "candidate_count": len(rows),
            "chart_path": summary_path,
            "image_path": summary_path,
            "preview_path": summary_path,
            "next_action": "Use component bars to decide whether score, evidence, QA, baseline movement, or open remediation is driving local review.",
        }
    ]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "missing_candidates",
        "mode": "candidate_explanation_panel",
        "project_name": project_name,
        "row_count": len(rows),
        "linked_drawer_rows": len(drawer_by_id),
        "linked_qa_rows": len(qa_by_id),
        "linked_lineage_rows": len(lineage_by_id),
        "linked_remediation_candidates": len(remediation_by_id),
        "remediation_linked_count": remediation_linked_count,
        "chart_count": len([row for row in rows if row.get("breakdown_preview_path")]) + (1 if summary_path else 0),
        "qa_counts": dict(qa_counts.most_common()),
        "rows": rows,
        "chart_rows": chart_rows,
        "recommended_next_actions": [
            "Use one panel row to inspect score, evidence, baseline movement, QA, and remediation before changing local review status.",
            "Use open_remediation_count and qa_bucket as the local explanation stop list before discussion handoff.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_candidate_explanation_panel_markdown(report: dict) -> str:
    lines = [
        "# Candidate Explanation Panel",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows: `{report.get('row_count')}`",
        f"- Remediation-linked candidates: `{report.get('remediation_linked_count')}`",
        "",
        "| ID | Score | Evidence | QA | Baseline | Remediation | Open Tasks | Trace | Next Action |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in (report.get("rows") or [])[:120]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("score_component") or row.get("score") or ""),
                    str(row.get("evidence_component") or ""),
                    str(row.get("qa_component") or ""),
                    str(row.get("baseline_component") or ""),
                    str(row.get("remediation_component") or ""),
                    str(row.get("open_remediation_count") or 0),
                    str(row.get("explanation_trace") or "").replace("|", "/"),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    for chart in report.get("chart_rows") or []:
        image = chart.get("preview_path") or chart.get("image_path") or chart.get("chart_path")
        if image:
            lines.extend(["", f"## {chart.get('label')}", "", f"![{chart.get('label')}]({image})"])
    lines.append("")
    return "\n".join(lines)


def write_candidate_explanation_panel(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_CANDIDATE_EXPLANATION_PANEL_JSON,
    csv_path: str | Path | None = DEFAULT_CANDIDATE_EXPLANATION_PANEL_CSV,
    markdown_path: str | Path | None = DEFAULT_CANDIDATE_EXPLANATION_PANEL_MD,
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
        "local_decision",
        "decision_confidence",
        "evidence_summary",
        "evidence_depth_score",
        "baseline_lineage_status",
        "baseline_changed_fields",
        "qa_bucket",
        "qa_reason",
        "open_remediation_count",
        "remediation_task_ids",
        "command_ids",
        "score_component",
        "evidence_component",
        "qa_component",
        "baseline_component",
        "remediation_component",
        "explanation_score_vector",
        "breakdown_chart_path",
        "breakdown_preview_path",
        "explanation_trace",
        "panel_sections",
        "next_action",
        "export_scope",
        "procurement_allowed",
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
        md_file.write_text(render_candidate_explanation_panel_markdown(report), encoding="utf-8")
