from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .governance_diff import COMPARE_FIELDS, _candidate_key, _float, _read_csv_rows


DEFAULT_BASELINE_LINEAGE_JSON = Path("data/projects/demo/baseline_lineage_compare.json")
DEFAULT_BASELINE_LINEAGE_CSV = Path("data/projects/demo/baseline_lineage_compare.csv")
DEFAULT_BASELINE_LINEAGE_MD = Path("docs/baseline_lineage_compare.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]
CURRENT_ID = "current_candidates"


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _safe_id(value: object) -> str:
    text = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in str(value or ""))
    return text.strip("._-")


def _registry_rows(root_path: Path, project_name: str) -> list[dict]:
    registry = _read_json(root_path / "data" / "projects" / project_name / "candidate_baseline_registry.json")
    rows = [dict(row) for row in registry.get("baselines") or []]
    return sorted(rows, key=lambda row: str(row.get("created_at") or ""))


def _choose_default_ids(rows: list[dict]) -> tuple[str, str]:
    if len(rows) >= 2:
        return str(rows[-2].get("baseline_id") or ""), str(rows[-1].get("baseline_id") or "")
    if len(rows) == 1:
        return str(rows[-1].get("baseline_id") or ""), CURRENT_ID
    return "", CURRENT_ID


def _baseline_csv_path(root_path: Path, project_name: str, baseline_id: str, rows: list[dict]) -> Path:
    safe = _safe_id(baseline_id)
    if safe == CURRENT_ID:
        return root_path / "data" / "projects" / project_name / "candidates.csv"
    for row in rows:
        if str(row.get("baseline_id") or "") == safe and row.get("baseline_path"):
            return _resolve(root_path, str(row.get("baseline_path")))
    return root_path / "data" / "projects" / project_name / "candidate_baselines" / safe / "candidates.csv"


def _rationale(status: str, changed_fields: list[str], base: dict, head: dict) -> str:
    if status == "entered":
        return "Candidate entered the head baseline or current candidate set."
    if status == "exited":
        return "Candidate exited the head baseline or current candidate set."
    if status == "changed":
        score_delta = round(_float(head.get("score")) - _float(base.get("score")), 4)
        rank_delta = round(_float(head.get("rank")) - _float(base.get("rank")), 4)
        return f"Changed fields={';'.join(changed_fields)}; score_delta={score_delta}; rank_delta={rank_delta}."
    return "Candidate is unchanged between compared baselines."


def build_baseline_lineage_compare(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    base_baseline_id: str | None = None,
    head_baseline_id: str | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    rows = _registry_rows(root_path, project_name)
    default_base, default_head = _choose_default_ids(rows)
    base_id = _safe_id(base_baseline_id or default_base)
    head_id = _safe_id(head_baseline_id or default_head)
    base_path = _baseline_csv_path(root_path, project_name, base_id, rows)
    head_path = _baseline_csv_path(root_path, project_name, head_id, rows)
    missing = []
    if not base_path.exists():
        missing.append(str(base_path))
    if not head_path.exists():
        missing.append(str(head_path))
    if missing:
        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "missing_baseline_sources",
            "mode": "candidate_baseline_lineage_compare",
            "project_name": project_name,
            "base_baseline_id": base_id,
            "head_baseline_id": head_id,
            "missing_sources": missing,
            "row_count": 0,
            "rows": [],
            "recommended_next_actions": ["Pin at least one candidate baseline and keep current candidates available before lineage compare."],
            "blocked_scopes": BLOCKED_SCOPES,
        }
    base_rows = _read_csv_rows(base_path)
    head_rows = _read_csv_rows(head_path)
    base_by_key = {_candidate_key(row): row for row in base_rows}
    head_by_key = {_candidate_key(row): row for row in head_rows}
    lineage_rows: list[dict[str, Any]] = []
    for key in sorted(set(base_by_key) | set(head_by_key)):
        base = base_by_key.get(key) or {}
        head = head_by_key.get(key) or {}
        if base and head:
            changed_fields = [field for field in COMPARE_FIELDS if str(base.get(field) or "") != str(head.get(field) or "")]
            status = "changed" if changed_fields else "unchanged"
        elif head:
            changed_fields = []
            status = "entered"
        else:
            changed_fields = []
            status = "exited"
        lineage_rows.append(
            {
                "candidate_key": key,
                "candidate_id": head.get("candidate_id") or base.get("candidate_id"),
                "lineage_status": status,
                "smiles": head.get("smiles") or base.get("smiles"),
                "site_class": head.get("site_class") or base.get("site_class", ""),
                "base_rank": base.get("rank", ""),
                "head_rank": head.get("rank", ""),
                "rank_delta": round(_float(head.get("rank")) - _float(base.get("rank")), 4) if base and head else "",
                "base_score": base.get("score", ""),
                "head_score": head.get("score", ""),
                "score_delta": round(_float(head.get("score")) - _float(base.get("score")), 4) if base and head else "",
                "changed_fields": ";".join(changed_fields),
                "rationale": _rationale(status, changed_fields, base, head),
                "base_why_review": base.get("why_review", ""),
                "head_why_review": head.get("why_review", ""),
            }
        )
    counts = Counter(str(row.get("lineage_status") or "") for row in lineage_rows)
    changed_like = [row for row in lineage_rows if row.get("lineage_status") in {"entered", "exited", "changed"}]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "compared",
        "mode": "candidate_baseline_lineage_compare",
        "project_name": project_name,
        "base_baseline_id": base_id,
        "head_baseline_id": head_id,
        "base_path": str(base_path),
        "head_path": str(head_path),
        "row_count": len(lineage_rows),
        "entered_candidate_count": counts.get("entered", 0),
        "exited_candidate_count": counts.get("exited", 0),
        "changed_candidate_count": counts.get("changed", 0),
        "unchanged_candidate_count": counts.get("unchanged", 0),
        "lineage_status_counts": dict(counts.most_common()),
        "max_abs_score_delta": max([abs(_float(row.get("score_delta"))) for row in changed_like if row.get("score_delta") != ""] or [0.0]),
        "max_abs_rank_delta": max([abs(_float(row.get("rank_delta"))) for row in changed_like if row.get("rank_delta") != ""] or [0.0]),
        "rows": lineage_rows,
        "real_experiment_feedback_used": False,
        "recommended_next_actions": [
            "Review entered, exited, and changed candidates before pinning a new baseline.",
            "Use lineage rationale as local scoring/profile/rule movement context only.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_baseline_lineage_compare_markdown(report: dict) -> str:
    lines = [
        "# Baseline Lineage Compare",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Base -> head: `{report.get('base_baseline_id')}` -> `{report.get('head_baseline_id')}`",
        f"- Entered / exited / changed: `{report.get('entered_candidate_count')}` / `{report.get('exited_candidate_count')}` / `{report.get('changed_candidate_count')}`",
        "",
        "| ID | Status | dScore | dRank | Fields | Rationale |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for row in (report.get("rows") or [])[:120]:
        if row.get("lineage_status") == "unchanged":
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("lineage_status") or ""),
                    str(row.get("score_delta") or ""),
                    str(row.get("rank_delta") or ""),
                    str(row.get("changed_fields") or ""),
                    str(row.get("rationale") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_baseline_lineage_compare(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_BASELINE_LINEAGE_JSON,
    csv_path: str | Path | None = DEFAULT_BASELINE_LINEAGE_CSV,
    markdown_path: str | Path | None = DEFAULT_BASELINE_LINEAGE_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "candidate_key",
        "candidate_id",
        "lineage_status",
        "smiles",
        "site_class",
        "base_rank",
        "head_rank",
        "rank_delta",
        "base_score",
        "head_score",
        "score_delta",
        "changed_fields",
        "rationale",
        "base_why_review",
        "head_why_review",
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
        md_file.write_text(render_baseline_lineage_compare_markdown(report), encoding="utf-8")
