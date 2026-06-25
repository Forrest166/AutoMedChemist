from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - optional native preview dependency
    Image = None
    ImageDraw = None
    ImageFont = None


DEFAULT_BASELINE_LINEAGE_PREVIEW_JSON = Path("data/projects/demo/baseline_lineage_preview.json")
DEFAULT_BASELINE_LINEAGE_PREVIEW_CSV = Path("data/projects/demo/baseline_lineage_preview.csv")
DEFAULT_BASELINE_LINEAGE_PREVIEW_MD = Path("docs/baseline_lineage_preview.md")
DEFAULT_BASELINE_LINEAGE_PREVIEW_DIR = Path("data/projects/demo/baseline_lineage_previews")
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


def _read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: object) -> int:
    return int(_number(value))


def _short(value: object, limit: int = 58) -> str:
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


def _write_png_preview(path: Path, chart_rows: list[dict[str, Any]], pairwise_rows: list[dict[str, Any]]) -> bool:
    if Image is None or ImageDraw is None:
        return False
    chart_tail = chart_rows[-12:] or [{"snapshot_index": 1, "movement_total": 0, "entered_candidate_count": 0, "exited_candidate_count": 0, "changed_candidate_count": 0}]
    pair_tail = pairwise_rows[-6:]
    width = 1280
    height = 520
    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    title_font = _font(30, bold=True)
    text_font = _font(18)
    small_font = _font(16)
    draw.text((32, 24), "Baseline Lineage Movement Preview", fill="#17202A", font=title_font)
    draw.text((32, 64), "snapshot movement totals plus latest pairwise deltas", fill="#52616F", font=text_font)
    max_total = max([1, *[_int(row.get("movement_total")) for row in chart_tail]])
    left = 70
    bottom = 310
    chart_width = 760
    bar_gap = 12
    bar_width = max(18, int((chart_width - bar_gap * len(chart_tail)) / max(1, len(chart_tail))))
    colors = {"entered_candidate_count": "#0F766E", "exited_candidate_count": "#B45309", "changed_candidate_count": "#2563EB"}
    for idx, row in enumerate(chart_tail):
        x = left + idx * (bar_width + bar_gap)
        y = bottom
        for field, color in colors.items():
            value = _int(row.get(field))
            part_height = int(190 * value / max_total) if value else 3
            draw.rectangle((x, y - part_height, x + bar_width, y), fill=color)
            y -= part_height
        draw.text((x, bottom + 8), str(row.get("snapshot_index") or idx + 1), fill="#52616F", font=small_font)
    draw.line((left, bottom, left + chart_width, bottom), fill="#CBD5E1", width=2)
    draw.text((32, 344), "Pairwise deltas", fill="#17202A", font=text_font)
    y = 378
    for row in pair_tail:
        label = _short(f"{row.get('pair_id')} {row.get('movement_signal')}", 34)
        details = f"entered={row.get('entered_delta')}; exited={row.get('exited_delta')}; changed={row.get('changed_delta')}; score_d={row.get('max_abs_score_delta_change')}"
        draw.text((32, y), label, fill="#17202A", font=small_font)
        draw.text((280, y), details, fill="#52616F", font=small_font)
        y += 26
    draw.text((900, 112), "Legend", fill="#17202A", font=text_font)
    legend_y = 148
    for field, color in colors.items():
        draw.rectangle((900, legend_y, 930, legend_y + 18), fill=color)
        draw.text((944, legend_y - 2), field.replace("_candidate_count", ""), fill="#52616F", font=small_font)
        legend_y += 34
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    return True


def _top_movers(rows: list[dict[str, Any]], limit: int = 40) -> list[dict[str, Any]]:
    def score(row: dict[str, Any]) -> float:
        return abs(_number(row.get("score_delta"))) + abs(_number(row.get("rank_delta"))) + (10 if row.get("lineage_status") in {"entered", "exited"} else 0)

    ranked = sorted((dict(row) for row in rows), key=score, reverse=True)
    out: list[dict[str, Any]] = []
    for index, row in enumerate(ranked[:limit], start=1):
        out.append(
            {
                "row_id": f"BLPREV-MOVER-{index:03d}",
                "row_type": "top_mover",
                "candidate_id": row.get("candidate_id") or row.get("candidate_key", ""),
                "lineage_status": row.get("lineage_status", ""),
                "movement_total": "",
                "entered_delta": "",
                "exited_delta": "",
                "changed_delta": "",
                "score_delta": row.get("score_delta", ""),
                "rank_delta": row.get("rank_delta", ""),
                "details": row.get("rationale", ""),
                "preview_path": "",
            }
        )
    return out


def build_baseline_lineage_preview(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    preview_dir: str | Path | None = DEFAULT_BASELINE_LINEAGE_PREVIEW_DIR,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    history = _read_json(project_dir / "baseline_lineage_history.json")
    chart_csv_rows = _read_csv_rows(project_dir / "baseline_lineage_history_chart.csv")
    pairwise_csv_rows = _read_csv_rows(project_dir / "baseline_lineage_history_pairwise.csv")
    chart_rows = [dict(row) for row in (history.get("movement_chart_rows") or chart_csv_rows)]
    pairwise_rows = [dict(row) for row in (history.get("pairwise_movement_rows") or pairwise_csv_rows)]
    movement_rows = [dict(row) for row in history.get("latest_movement_rows") or []]
    preview_root = root_path / preview_dir if preview_dir else project_dir / "baseline_lineage_previews"
    if Path(preview_root) == root_path / DEFAULT_BASELINE_LINEAGE_PREVIEW_DIR:
        preview_root = project_dir / "baseline_lineage_previews"
    png_path = preview_root / "baseline_lineage_movement_preview.png"
    preview_available = _write_png_preview(png_path, chart_rows, pairwise_rows)
    rows: list[dict[str, Any]] = []
    rows.append(
        {
            "row_id": "BLPREV-CHART-001",
            "row_type": "movement_chart",
            "candidate_id": "",
            "lineage_status": history.get("status", ""),
            "movement_total": sum(_int(row.get("movement_total")) for row in chart_rows[-12:]),
            "entered_delta": "",
            "exited_delta": "",
            "changed_delta": "",
            "score_delta": "",
            "rank_delta": "",
            "details": f"snapshots={len(chart_rows)}; pairwise={len(pairwise_rows)}",
            "preview_path": str(png_path.resolve()) if preview_available else "",
        }
    )
    for index, row in enumerate(pairwise_rows[-40:], start=1):
        rows.append(
            {
                "row_id": f"BLPREV-PAIR-{index:03d}",
                "row_type": "pairwise_delta",
                "candidate_id": "",
                "lineage_status": row.get("movement_signal", ""),
                "movement_total": abs(_int(row.get("entered_delta"))) + abs(_int(row.get("exited_delta"))) + abs(_int(row.get("changed_delta"))),
                "entered_delta": row.get("entered_delta", ""),
                "exited_delta": row.get("exited_delta", ""),
                "changed_delta": row.get("changed_delta", ""),
                "score_delta": row.get("max_abs_score_delta_change", ""),
                "rank_delta": row.get("max_abs_rank_delta_change", ""),
                "details": f"{row.get('from_created_at')} -> {row.get('to_created_at')}",
                "preview_path": str(png_path.resolve()) if preview_available else "",
            }
        )
    rows.extend(_top_movers(movement_rows))
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if chart_rows or pairwise_rows or movement_rows else "empty",
        "mode": "baseline_lineage_preview",
        "project_name": project_name,
        "row_count": len(rows),
        "chart_point_count": len(chart_rows),
        "pairwise_row_count": len(pairwise_rows),
        "top_mover_count": len(movement_rows),
        "preview_path": str(png_path.resolve()) if preview_available else "",
        "preview_available": preview_available,
        "rows": rows,
        "recommended_next_actions": [
            "Use the PNG preview to scan movement spikes before pinning or archiving baselines.",
            "Use top_mover rows to explain candidate entry, exit, and score/rank movement.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_baseline_lineage_preview_markdown(report: dict) -> str:
    lines = [
        "# Baseline Lineage Preview",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Preview: `{report.get('preview_path')}`",
        f"- Chart / pairwise / top movers: `{report.get('chart_point_count')}` / `{report.get('pairwise_row_count')}` / `{report.get('top_mover_count')}`",
        "",
        "| Row | Type | Candidate | Status | Movement | dScore | dRank | Details |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in (report.get("rows") or [])[:160]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("row_id") or ""),
                    str(row.get("row_type") or ""),
                    str(row.get("candidate_id") or ""),
                    str(row.get("lineage_status") or ""),
                    str(row.get("movement_total") or ""),
                    str(row.get("score_delta") or ""),
                    str(row.get("rank_delta") or ""),
                    str(row.get("details") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_baseline_lineage_preview(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_BASELINE_LINEAGE_PREVIEW_JSON,
    csv_path: str | Path | None = DEFAULT_BASELINE_LINEAGE_PREVIEW_CSV,
    markdown_path: str | Path | None = DEFAULT_BASELINE_LINEAGE_PREVIEW_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "row_id",
        "row_type",
        "candidate_id",
        "lineage_status",
        "movement_total",
        "entered_delta",
        "exited_delta",
        "changed_delta",
        "score_delta",
        "rank_delta",
        "details",
        "preview_path",
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
        md_file.write_text(render_baseline_lineage_preview_markdown(report), encoding="utf-8")
