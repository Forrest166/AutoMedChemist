from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASELINE_LINEAGE_JSON = Path("data/projects/demo/candidate_baseline_lineage.json")
DEFAULT_BASELINE_LINEAGE_CSV = Path("data/projects/demo/candidate_baseline_lineage.csv")
DEFAULT_BASELINE_LINEAGE_MD = Path("docs/candidate_baseline_lineage.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]
COMPARE_FIELDS = ["rank", "score", "smiles", "site_class", "site_type", "local_decision", "why_review"]


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
        return list(csv.DictReader(handle))


def _resolve(root: Path, path: object) -> Path | None:
    text = str(path or "").strip()
    if not text:
        return None
    item = Path(text)
    return item if item.is_absolute() else root / item


def _candidate_key(row: dict) -> str:
    candidate_id = str(row.get("candidate_id") or "").strip()
    if candidate_id:
        return f"id:{candidate_id}"
    smiles = str(row.get("smiles") or "").strip()
    if smiles:
        return f"smiles:{smiles}"
    return f"row:{json.dumps(row, sort_keys=True)}"


def _pick_baselines(registry: dict, base_baseline_id: str = "", head_baseline_id: str = "") -> tuple[dict, dict]:
    rows = [dict(row) for row in registry.get("baselines") or []]
    rows.sort(key=lambda row: str(row.get("created_at") or ""))
    by_id = {str(row.get("baseline_id") or ""): row for row in rows}
    base = by_id.get(base_baseline_id, {}) if base_baseline_id else {}
    head = by_id.get(head_baseline_id, {}) if head_baseline_id else {}
    if base and head:
        return base, head
    if len(rows) >= 2:
        return rows[-2], rows[-1]
    if len(rows) == 1:
        return rows[0], {}
    return {}, {}


def _compare_rows(
    *,
    base_rows: list[dict[str, str]],
    head_rows: list[dict[str, str]],
    base_id: str,
    head_id: str,
) -> list[dict[str, Any]]:
    base_by_key = {_candidate_key(row): row for row in base_rows}
    head_by_key = {_candidate_key(row): row for row in head_rows}
    rows: list[dict[str, Any]] = []
    for key in sorted(set(base_by_key) | set(head_by_key)):
        base = base_by_key.get(key) or {}
        head = head_by_key.get(key) or {}
        if base and head:
            changed_fields = [field for field in COMPARE_FIELDS if str(base.get(field) or "") != str(head.get(field) or "")]
            status = "changed" if changed_fields else "unchanged"
            reason = "field movement" if changed_fields else "no compared field movement"
        elif head:
            changed_fields = []
            status = "entered"
            reason = "candidate entered head set"
        else:
            changed_fields = []
            status = "exited"
            reason = "candidate exited head set"
        rows.append(
            {
                "candidate_key": key,
                "candidate_id": head.get("candidate_id") or base.get("candidate_id", ""),
                "status": status,
                "base_baseline_id": base_id,
                "head_baseline_id": head_id,
                "base_score": base.get("score", ""),
                "head_score": head.get("score", ""),
                "base_rank": base.get("rank", ""),
                "head_rank": head.get("rank", ""),
                "changed_fields": ";".join(changed_fields),
                "lineage_reason": reason,
                "base_smiles": base.get("smiles", ""),
                "head_smiles": head.get("smiles", ""),
            }
        )
    return rows


def build_candidate_baseline_lineage(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    base_baseline_id: str = "",
    head_baseline_id: str = "",
    candidates_csv: str | Path | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    registry = _read_json(project_dir / "candidate_baseline_registry.json")
    base, head = _pick_baselines(registry, base_baseline_id, head_baseline_id)
    current_csv = _resolve(root_path, candidates_csv or Path("data/projects") / project_name / "candidates.csv")
    base_id = str(base.get("baseline_id") or base_baseline_id or "")
    head_id = str(head.get("baseline_id") or head_baseline_id or "current_candidates")
    base_path = _resolve(root_path, base.get("baseline_path", "")) if base else None
    head_path = _resolve(root_path, head.get("baseline_path", "")) if head else current_csv
    base_rows = _read_csv_rows(base_path) if base_path else []
    head_rows = _read_csv_rows(head_path) if head_path else []
    rows = _compare_rows(base_rows=base_rows, head_rows=head_rows, base_id=base_id, head_id=head_id) if base_rows and head_rows else []
    counts = Counter(str(row.get("status") or "") for row in rows)
    if rows:
        status = "ready"
    elif not registry:
        status = "missing_baseline_registry"
    elif not base_rows:
        status = "missing_base_baseline"
    else:
        status = "missing_head_baseline"
    comparison_mode = "baseline_to_baseline" if head else "baseline_to_current"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "candidate_baseline_lineage_compare",
        "comparison_mode": comparison_mode,
        "project_name": project_name,
        "base_baseline_id": base_id,
        "head_baseline_id": head_id,
        "base_path": str(base_path) if base_path else "",
        "head_path": str(head_path) if head_path else "",
        "row_count": len(rows),
        "entered_count": counts.get("entered", 0),
        "exited_count": counts.get("exited", 0),
        "changed_count": counts.get("changed", 0),
        "unchanged_count": counts.get("unchanged", 0),
        "status_counts": dict(counts.most_common()),
        "rows": rows,
        "recommended_next_actions": [
            "Inspect entered, exited, and changed rows before pinning a new candidate baseline.",
            "Use lineage as local release context, not as an experimental trigger.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_candidate_baseline_lineage_markdown(report: dict) -> str:
    lines = [
        "# Candidate Baseline Lineage",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Base / head: `{report.get('base_baseline_id')}` / `{report.get('head_baseline_id')}`",
        f"- Entered / exited / changed: `{report.get('entered_count')}` / `{report.get('exited_count')}` / `{report.get('changed_count')}`",
        "",
        "| ID | Status | Base Score | Head Score | Base Rank | Head Rank | Fields | Reason |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in (report.get("rows") or [])[:120]:
        if row.get("status") == "unchanged":
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or row.get("candidate_key") or ""),
                    str(row.get("status") or ""),
                    str(row.get("base_score") or ""),
                    str(row.get("head_score") or ""),
                    str(row.get("base_rank") or ""),
                    str(row.get("head_rank") or ""),
                    str(row.get("changed_fields") or ""),
                    str(row.get("lineage_reason") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_candidate_baseline_lineage(
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
        "status",
        "base_baseline_id",
        "head_baseline_id",
        "base_score",
        "head_score",
        "base_rank",
        "head_rank",
        "changed_fields",
        "lineage_reason",
        "base_smiles",
        "head_smiles",
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
        md_file.write_text(render_candidate_baseline_lineage_markdown(report), encoding="utf-8")
