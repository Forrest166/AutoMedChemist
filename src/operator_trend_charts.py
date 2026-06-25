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


DEFAULT_OPERATOR_TREND_CHART_JSON = Path("data/releases/operator_trend_charts.json")
DEFAULT_OPERATOR_TREND_CHART_CSV = Path("data/releases/operator_trend_charts.csv")
DEFAULT_OPERATOR_TREND_CHART_MD = Path("docs/operator_trend_charts.md")
DEFAULT_OPERATOR_TREND_CHART_DIR = Path("data/releases/operator_trend_charts")


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_name(value: object) -> str:
    text = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(value or "chart"))
    return text.strip("_") or "chart"


def _svg_card(label: str, status: str, value: object, trend: object, details: str) -> str:
    numeric = abs(_float(value, 0.0))
    trend_numeric = _float(trend, 0.0)
    bar = max(8, min(520, int(numeric * 12) if numeric <= 50 else 520))
    trend_width = max(0, min(180, int(abs(trend_numeric) * 16)))
    color = "#0F766E" if status == "ready" else "#B45309"
    trend_color = "#2563EB" if trend_numeric >= 0 else "#7C3AED"
    escaped = (
        str(details or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    label_escaped = str(label or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="720" height="160" viewBox="0 0 720 160">
  <rect x="0" y="0" width="720" height="160" fill="#ffffff"/>
  <text x="20" y="28" font-family="Segoe UI, Arial" font-size="18" font-weight="700" fill="#17202A">{label_escaped}</text>
  <text x="20" y="54" font-family="Segoe UI, Arial" font-size="12" fill="#52616F">status={status} value={value} trend={trend}</text>
  <rect x="20" y="76" width="560" height="22" fill="#E9EEF2"/>
  <rect x="20" y="76" width="{bar}" height="22" fill="{color}"/>
  <rect x="20" y="112" width="180" height="12" fill="#E9EEF2"/>
  <rect x="20" y="112" width="{trend_width}" height="12" fill="{trend_color}"/>
  <text x="220" y="123" font-family="Segoe UI, Arial" font-size="11" fill="#52616F">trend magnitude</text>
  <text x="20" y="146" font-family="Segoe UI, Arial" font-size="11" fill="#52616F">{escaped[:150]}</text>
</svg>
"""


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


def _short(value: object, limit: int = 118) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _png_card(path: Path, label: str, status: str, value: object, trend: object, details: str) -> bool:
    if Image is None or ImageDraw is None:
        return False
    numeric = abs(_float(value, 0.0))
    trend_numeric = _float(trend, 0.0)
    bar = max(16, min(1120, int(numeric * 24) if numeric <= 50 else 1120))
    trend_width = max(0, min(360, int(abs(trend_numeric) * 32)))
    color = "#0F766E" if status == "ready" else "#B45309"
    trend_color = "#2563EB" if trend_numeric >= 0 else "#7C3AED"
    image = Image.new("RGB", (1440, 320), "#ffffff")
    draw = ImageDraw.Draw(image)
    title_font = _font(38, bold=True)
    text_font = _font(24)
    small_font = _font(22)
    draw.text((40, 34), _short(label, 76), fill="#17202A", font=title_font)
    draw.text((40, 94), f"status={status}  value={value}  trend={trend}", fill="#52616F", font=text_font)
    draw.rounded_rectangle((40, 152, 1160, 196), radius=10, fill="#E9EEF2")
    draw.rounded_rectangle((40, 152, 40 + bar, 196), radius=10, fill=color)
    draw.rounded_rectangle((40, 226, 400, 250), radius=8, fill="#E9EEF2")
    draw.rounded_rectangle((40, 226, 40 + trend_width, 250), radius=8, fill=trend_color)
    draw.text((440, 220), "trend magnitude", fill="#52616F", font=small_font)
    draw.text((40, 284), _short(details, 150), fill="#52616F", font=small_font)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    return True


def build_operator_trend_charts(
    *,
    root: str | Path = ".",
    summary_path: str | Path | None = None,
    chart_dir: str | Path = DEFAULT_OPERATOR_TREND_CHART_DIR,
) -> dict[str, Any]:
    root_path = Path(root)
    summary = _read_json(root_path / (summary_path or "data/releases/operator_trend_summary.json"))
    out_dir = Path(chart_dir)
    if not out_dir.is_absolute():
        out_dir = root_path / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for card in summary.get("cards") or []:
        card_id = _safe_name(card.get("card_id"))
        svg_path = out_dir / f"{card_id}.svg"
        svg_path.write_text(
            _svg_card(
                str(card.get("label") or card_id),
                str(card.get("status") or ""),
                card.get("value", ""),
                card.get("trend", ""),
                str(card.get("details") or ""),
            ),
            encoding="utf-8",
        )
        png_path = out_dir / f"{card_id}.png"
        preview_available = _png_card(
            png_path,
            str(card.get("label") or card_id),
            str(card.get("status") or ""),
            card.get("value", ""),
            card.get("trend", ""),
            str(card.get("details") or ""),
        )
        rows.append(
            {
                "card_id": card_id,
                "label": card.get("label", ""),
                "status": card.get("status", ""),
                "value": card.get("value", ""),
                "trend": card.get("trend", ""),
                "chart_path": str(svg_path.resolve()),
                "image_path": str(png_path.resolve()) if preview_available else "",
                "preview_path": str(png_path.resolve()) if preview_available else "",
                "preview_available": preview_available,
                "next_action": card.get("next_action", ""),
            }
        )
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "missing_operator_trend_summary",
        "mode": "operator_trend_chart_pack",
        "chart_count": len(rows),
        "chart_dir": str(out_dir.resolve()),
        "rows": rows,
        "recommended_next_actions": ["Select a chart row in the native Reports view to preview the PNG card, or open chart_path for SVG."],
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }


def render_operator_trend_charts_markdown(report: dict) -> str:
    lines = [
        "# Operator Trend Charts",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Charts: `{report.get('chart_count')}`",
        "",
    ]
    for row in report.get("rows") or []:
        image = row.get("preview_path") or row.get("image_path") or row.get("chart_path")
        lines.extend([f"## {row.get('label')}", "", f"![{row.get('label')}]({image})", ""])
    return "\n".join(lines)


def write_operator_trend_charts(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_OPERATOR_TREND_CHART_JSON,
    csv_path: str | Path | None = DEFAULT_OPERATOR_TREND_CHART_CSV,
    markdown_path: str | Path | None = DEFAULT_OPERATOR_TREND_CHART_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path:
        csv_file = Path(csv_path)
        csv_file.parent.mkdir(parents=True, exist_ok=True)
        fields = ["card_id", "label", "status", "value", "trend", "chart_path", "image_path", "preview_path", "preview_available", "next_action"]
        with csv_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in report.get("rows") or []:
                writer.writerow({field: row.get(field, "") for field in fields})
    if markdown_path:
        md_file = Path(markdown_path)
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(render_operator_trend_charts_markdown(report), encoding="utf-8")
