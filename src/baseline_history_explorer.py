from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .baseline_lineage_compare import BLOCKED_SCOPES, CURRENT_ID, build_baseline_lineage_compare

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - optional native preview dependency
    Image = None
    ImageDraw = None
    ImageFont = None


DEFAULT_BASELINE_HISTORY_JSON = Path("data/projects/demo/baseline_history_explorer.json")
DEFAULT_BASELINE_HISTORY_CSV = Path("data/projects/demo/baseline_history_explorer.csv")
DEFAULT_BASELINE_HISTORY_MD = Path("docs/baseline_history_explorer.md")
DEFAULT_BASELINE_HISTORY_CHART_DIR = Path("data/projects/demo/baseline_history_explorer_charts")
DEFAULT_BASELINE_HISTORY_MATRIX_CSV = Path("data/projects/demo/baseline_history_explorer_matrix.csv")
DEFAULT_BASELINE_ACTIVE_PREVIEW_JSON = Path("data/projects/demo/baseline_active_preview.json")
DEFAULT_BASELINE_ROLLBACK_MD = Path("docs/baseline_rollback_explanation.md")


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_csv_count(path: str | Path) -> int:
    source = Path(path)
    if not source.exists():
        return 0
    with source.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return sum(1 for _ in reader)


def _safe_id(value: object) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in str(value or "")).strip("._-")


def _int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _short(value: object, limit: int = 56) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 3] + "..."


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


def _write_svg_chart(path: Path, comparison_rows: list[dict[str, Any]]) -> None:
    width = 920
    height = max(220, 110 + 46 * max(1, len(comparison_rows)))
    movement_values = [
        _int(row.get("changed_candidate_count")) + _int(row.get("entered_candidate_count")) + _int(row.get("exited_candidate_count"))
        for row in comparison_rows
    ]
    max_value = max([1, *movement_values])
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect x="0" y="0" width="920" height="' + str(height) + '" fill="#ffffff"/>',
        '<text x="24" y="34" font-family="Segoe UI, Arial" font-size="22" font-weight="700" fill="#17202A">Baseline History Movement</text>',
        '<text x="24" y="60" font-family="Segoe UI, Arial" font-size="12" fill="#52616F">changed / entered / exited candidate counts across saved baseline comparisons</text>',
    ]
    y = 94
    colors = [("#2563EB", "changed_candidate_count"), ("#0F766E", "entered_candidate_count"), ("#B45309", "exited_candidate_count")]
    for row in comparison_rows or [{"baseline_id": "no_comparison", "head_baseline_id": "", "changed_candidate_count": 0}]:
        label = _short(f"{row.get('baseline_id')} -> {row.get('head_baseline_id')}", 72)
        parts.append(f'<text x="24" y="{y}" font-family="Segoe UI, Arial" font-size="12" fill="#17202A">{label}</text>')
        x = 260
        for color, field in colors:
            value = _int(row.get(field))
            bar_width = int(520 * value / max_value) if value else 4
            parts.append(f'<rect x="{x}" y="{y - 14}" width="{bar_width}" height="12" fill="{color}"/>')
            parts.append(f'<text x="{x + bar_width + 8}" y="{y - 4}" font-family="Segoe UI, Arial" font-size="11" fill="#52616F">{value}</text>')
            x += 185
        y += 46
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")


def _write_png_chart(path: Path, comparison_rows: list[dict[str, Any]]) -> bool:
    if Image is None or ImageDraw is None:
        return False
    rows = comparison_rows or [{"baseline_id": "no_comparison", "head_baseline_id": "", "changed_candidate_count": 0}]
    width = 1440
    height = max(360, 170 + 78 * len(rows))
    movement_values = [
        _int(row.get("changed_candidate_count")) + _int(row.get("entered_candidate_count")) + _int(row.get("exited_candidate_count"))
        for row in rows
    ]
    max_value = max([1, *movement_values])
    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    title_font = _font(36, bold=True)
    text_font = _font(22)
    small_font = _font(20)
    draw.text((40, 30), "Baseline History Movement", fill="#17202A", font=title_font)
    draw.text((40, 82), "changed / entered / exited candidate counts across saved baseline comparisons", fill="#52616F", font=text_font)
    y = 150
    colors = [("#2563EB", "changed_candidate_count"), ("#0F766E", "entered_candidate_count"), ("#B45309", "exited_candidate_count")]
    for row in rows:
        draw.text((40, y - 8), _short(f"{row.get('baseline_id')} -> {row.get('head_baseline_id')}", 68), fill="#17202A", font=small_font)
        x = 420
        for color, field in colors:
            value = _int(row.get(field))
            bar_width = int(520 * value / max_value) if value else 8
            draw.rounded_rectangle((x, y - 18, x + bar_width, y + 6), radius=5, fill=color)
            draw.text((x + bar_width + 12, y - 20), str(value), fill="#52616F", font=small_font)
            x += 280
        y += 78
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    return True


def _build_chart_rows(root_path: Path, project_name: str, comparison_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chart_dir = root_path / "data" / "projects" / project_name / "baseline_history_explorer_charts"
    svg_path = chart_dir / "baseline_history_movement.svg"
    png_path = chart_dir / "baseline_history_movement.png"
    _write_svg_chart(svg_path, comparison_rows)
    preview_available = _write_png_chart(png_path, comparison_rows)
    return [
        {
            "chart_id": "baseline_history_movement",
            "label": "Baseline history movement",
            "status": "ready" if comparison_rows else "no_comparisons",
            "comparison_count": len(comparison_rows),
            "chart_path": str(svg_path.resolve()),
            "image_path": str(png_path.resolve()) if preview_available else "",
            "preview_path": str(png_path.resolve()) if preview_available else "",
            "next_action": "Use this compact chart to spot entered, exited, and changed candidate movement before pinning another baseline.",
            "project_name": project_name,
        }
    ]


def _baseline_path(root_path: Path, project_name: str, baseline_id: str, registry_row: dict | None = None) -> Path:
    if baseline_id == CURRENT_ID:
        return root_path / "data" / "projects" / project_name / "candidates.csv"
    if registry_row and registry_row.get("baseline_path"):
        path = Path(str(registry_row.get("baseline_path")))
        return path if path.is_absolute() else root_path / path
    return root_path / "data" / "projects" / project_name / "candidate_baselines" / _safe_id(baseline_id) / "candidates.csv"


def _active_baseline_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if str(row.get("status") or "active") not in {"archived", "inactive"}]


def _latest_active_baseline_id(rows: list[dict[str, Any]]) -> str:
    active = _active_baseline_rows(rows)
    if not active:
        return CURRENT_ID
    return str(active[-1].get("baseline_id") or CURRENT_ID)


def _preview_row(compare: dict, *, label: str, base_id: str, head_id: str) -> dict[str, Any]:
    return {
        "label": label,
        "base_baseline_id": base_id,
        "head_baseline_id": head_id,
        "status": compare.get("status"),
        "row_count": compare.get("row_count", 0),
        "changed_candidate_count": compare.get("changed_candidate_count", 0),
        "entered_candidate_count": compare.get("entered_candidate_count", 0),
        "exited_candidate_count": compare.get("exited_candidate_count", 0),
        "max_abs_score_delta": compare.get("max_abs_score_delta", 0),
        "next_action": "Review changed/entered/exited rows before switching active baseline or explaining rollback.",
    }


def _build_active_preview(root_path: Path, project_name: str, active_id: str) -> dict[str, Any]:
    compare = build_baseline_lineage_compare(root=root_path, project_name=project_name, base_baseline_id=active_id, head_baseline_id=CURRENT_ID)
    preview = _preview_row(compare, label="active_to_current", base_id=active_id, head_id=CURRENT_ID)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if active_id else "missing_active_baseline",
        "mode": "baseline_active_preview",
        "project_name": project_name,
        "active_baseline_id": active_id,
        "preview": preview,
        "rows": [preview],
        "recommended_next_actions": [
            "Use active_to_current movement before accepting a new active baseline.",
            "Use rollback options only as local explanatory snapshots, not experiment or procurement triggers.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def _build_rollback_rows(root_path: Path, project_name: str, baseline_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _active_baseline_rows(baseline_rows):
        baseline_id = str(row.get("baseline_id") or "")
        if not baseline_id:
            continue
        compare = build_baseline_lineage_compare(root=root_path, project_name=project_name, base_baseline_id=CURRENT_ID, head_baseline_id=baseline_id)
        rows.append(
            {
                **_preview_row(compare, label=f"rollback_to_{baseline_id}", base_id=CURRENT_ID, head_id=baseline_id),
                "rollback_candidate_baseline_id": baseline_id,
                "explanation": (
                    f"Rollback to {baseline_id} would re-open local review for changed={compare.get('changed_candidate_count', 0)}, "
                    f"entered={compare.get('entered_candidate_count', 0)}, exited={compare.get('exited_candidate_count', 0)} candidate movements."
                ),
            }
        )
    return rows


def build_baseline_history_explorer(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    max_pairwise: int = 12,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    registry = _read_json(project_dir / "candidate_baseline_registry.json")
    baseline_rows = [dict(row) for row in registry.get("baselines") or []]
    baseline_rows = sorted(baseline_rows, key=lambda row: str(row.get("created_at") or ""))
    current_path = project_dir / "candidates.csv"
    current_row = {
        "baseline_id": CURRENT_ID,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "current",
        "baseline_path": str(current_path),
        "note": "Current candidate set.",
    }
    all_rows = [*baseline_rows, current_row]

    summary_rows: list[dict[str, Any]] = []
    for row in all_rows:
        baseline_id = str(row.get("baseline_id") or "")
        path = _baseline_path(root_path, project_name, baseline_id, row)
        summary_rows.append(
            {
                "row_type": "baseline",
                "baseline_id": baseline_id,
                "head_baseline_id": "",
                "created_at": row.get("created_at", ""),
                "status": row.get("status", ""),
                "candidate_count": _read_csv_count(path),
                "changed_candidate_count": "",
                "entered_candidate_count": "",
                "exited_candidate_count": "",
                "path": str(path),
                "summary": row.get("note") or row.get("description") or "",
                "next_action": "Select this baseline as a compare endpoint before pinning a new baseline.",
            }
        )

    pair_rows: list[dict[str, Any]] = []
    ids = [str(row.get("baseline_id") or "") for row in all_rows if row.get("baseline_id")]
    pairs: list[tuple[str, str]] = []
    if len(ids) >= 2:
        for left_index, base_id in enumerate(ids[:-1]):
            for head_id in ids[left_index + 1 :]:
                pairs.append((base_id, head_id))
    for index, (base_id, head_id) in enumerate(pairs[-int(max_pairwise) :], start=1):
        compare = build_baseline_lineage_compare(root=root_path, project_name=project_name, base_baseline_id=base_id, head_baseline_id=head_id)
        pair_rows.append(
            {
                "row_type": "comparison",
                "baseline_id": base_id,
                "head_baseline_id": head_id,
                "created_at": compare.get("created_at", ""),
                "status": compare.get("status", ""),
                "candidate_count": compare.get("row_count", 0),
                "changed_candidate_count": compare.get("changed_candidate_count", 0),
                "entered_candidate_count": compare.get("entered_candidate_count", 0),
                "exited_candidate_count": compare.get("exited_candidate_count", 0),
                "path": f"{base_id}->{head_id}",
                "summary": f"changed={compare.get('changed_candidate_count', 0)}; entered={compare.get('entered_candidate_count', 0)}; exited={compare.get('exited_candidate_count', 0)}",
                "next_action": "Open baseline lineage compare for candidate-level rationale.",
            }
        )
    rows = [*summary_rows, *pair_rows]
    chart_rows = _build_chart_rows(root_path, project_name, pair_rows)
    active_baseline_id = _latest_active_baseline_id(baseline_rows)
    active_preview = _build_active_preview(root_path, project_name, active_baseline_id)
    rollback_rows = _build_rollback_rows(root_path, project_name, baseline_rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if summary_rows else "missing_baselines",
        "mode": "candidate_baseline_history_explorer",
        "project_name": project_name,
        "active_baseline_id": active_baseline_id,
        "baseline_count": len(summary_rows),
        "comparison_count": len(pair_rows),
        "matrix_row_count": len(pair_rows),
        "rollback_option_count": len(rollback_rows),
        "chart_count": len(chart_rows),
        "row_count": len(rows),
        "rows": rows,
        "matrix_rows": pair_rows,
        "active_preview": active_preview,
        "rollback_rows": rollback_rows,
        "chart_rows": chart_rows,
        "recommended_next_actions": [
            "Use the history explorer to choose any two saved baselines before reviewing lineage rows.",
            "Preview active_to_current movement before changing active baseline assumptions.",
            "Use rollback explanation rows for local review only; do not trigger procurement or real experiment feedback automation.",
            "Pin a new baseline only after entered, exited, and changed candidates are locally reviewed.",
        ],
        "real_experiment_feedback_used": False,
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_baseline_history_explorer_markdown(report: dict) -> str:
    lines = [
        "# Baseline History Explorer",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Active baseline: `{report.get('active_baseline_id')}`",
        f"- Baselines / comparisons: `{report.get('baseline_count')}` / `{report.get('comparison_count')}`",
        f"- Rollback options: `{report.get('rollback_option_count')}`",
        "",
        "| Type | Base | Head | Status | Candidates | Changed | Entered | Exited | Summary |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("row_type") or ""),
                    str(row.get("baseline_id") or ""),
                    str(row.get("head_baseline_id") or ""),
                    str(row.get("status") or ""),
                    str(row.get("candidate_count") or ""),
                    str(row.get("changed_candidate_count") or ""),
                    str(row.get("entered_candidate_count") or ""),
                    str(row.get("exited_candidate_count") or ""),
                    str(row.get("summary") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    for chart in report.get("chart_rows") or []:
        image = chart.get("preview_path") or chart.get("image_path") or chart.get("chart_path")
        lines.extend(["", f"## {chart.get('label')}", "", f"![{chart.get('label')}]({image})"])
    preview = (report.get("active_preview") or {}).get("preview") or {}
    if preview:
        lines.extend(
            [
                "",
                "## Active Baseline Preview",
                "",
                "| Base | Head | Changed | Entered | Exited | Next Action |",
                "| --- | --- | ---: | ---: | ---: | --- |",
                "| "
                + " | ".join(
                    [
                        str(preview.get("base_baseline_id") or ""),
                        str(preview.get("head_baseline_id") or ""),
                        str(preview.get("changed_candidate_count") or 0),
                        str(preview.get("entered_candidate_count") or 0),
                        str(preview.get("exited_candidate_count") or 0),
                        str(preview.get("next_action") or "").replace("|", "/"),
                    ]
                )
                + " |",
            ]
        )
    if report.get("rollback_rows"):
        lines.extend(["", "## Rollback Explanation", "", "| Target | Changed | Entered | Exited | Explanation |", "| --- | ---: | ---: | ---: | --- |"])
        for row in report.get("rollback_rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("rollback_candidate_baseline_id") or ""),
                        str(row.get("changed_candidate_count") or 0),
                        str(row.get("entered_candidate_count") or 0),
                        str(row.get("exited_candidate_count") or 0),
                        str(row.get("explanation") or "").replace("|", "/"),
                    ]
                )
                + " |"
            )
    lines.append("")
    return "\n".join(lines)


def render_baseline_rollback_markdown(report: dict) -> str:
    lines = [
        "# Baseline Rollback Explanation",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Active baseline: `{report.get('active_baseline_id')}`",
        f"- Rollback options: `{report.get('rollback_option_count')}`",
        "",
        "| Target Baseline | Changed | Entered | Exited | Explanation |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("rollback_rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("rollback_candidate_baseline_id") or ""),
                    str(row.get("changed_candidate_count") or 0),
                    str(row.get("entered_candidate_count") or 0),
                    str(row.get("exited_candidate_count") or 0),
                    str(row.get("explanation") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.extend(["", "Blocked scopes: `procurement`, `supplier_purchase`, `real_experiment_feedback_auto_import`.", ""])
    return "\n".join(lines)


def write_baseline_history_explorer(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_BASELINE_HISTORY_JSON,
    csv_path: str | Path | None = DEFAULT_BASELINE_HISTORY_CSV,
    markdown_path: str | Path | None = DEFAULT_BASELINE_HISTORY_MD,
    matrix_csv_path: str | Path | None = None,
    active_preview_json_path: str | Path | None = None,
    rollback_markdown_path: str | Path | None = None,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "row_type",
        "baseline_id",
        "head_baseline_id",
        "created_at",
        "status",
        "candidate_count",
        "changed_candidate_count",
        "entered_candidate_count",
        "exited_candidate_count",
        "path",
        "summary",
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
    matrix_target = Path(matrix_csv_path) if matrix_csv_path else json_file.parent / "baseline_history_explorer_matrix.csv"
    matrix_target.parent.mkdir(parents=True, exist_ok=True)
    with matrix_target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in report.get("matrix_rows") or []:
            writer.writerow({field: row.get(field, "") for field in fields})
    active_target = Path(active_preview_json_path) if active_preview_json_path else json_file.parent / "baseline_active_preview.json"
    active_target.parent.mkdir(parents=True, exist_ok=True)
    active_target.write_text(json.dumps(report.get("active_preview") or {}, indent=2, sort_keys=True), encoding="utf-8")
    if markdown_path:
        md_file = Path(markdown_path)
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(render_baseline_history_explorer_markdown(report), encoding="utf-8")
    rollback_target = Path(rollback_markdown_path) if rollback_markdown_path else Path("docs/baseline_rollback_explanation.md")
    if markdown_path and rollback_markdown_path is None:
        rollback_target = Path(markdown_path).parent / "baseline_rollback_explanation.md"
    rollback_target.parent.mkdir(parents=True, exist_ok=True)
    rollback_target.write_text(render_baseline_rollback_markdown(report), encoding="utf-8")
