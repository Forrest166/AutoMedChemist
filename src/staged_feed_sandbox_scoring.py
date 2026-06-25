from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_STAGED_FEED_SANDBOX_JSON = Path("data/projects/demo/staged_feed_sandbox_scoring.json")
DEFAULT_STAGED_FEED_SANDBOX_CSV = Path("data/projects/demo/staged_feed_sandbox_scoring.csv")
DEFAULT_STAGED_FEED_SANDBOX_MD = Path("docs/staged_feed_sandbox_scoring.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import", "production_scoring_write"]


SITE_TOKEN_HINTS = {
    "methoxy": {"alkoxy", "methoxy", "metabolism", "soft_spot"},
    "ester": {"ester", "carbonyl", "hydrolysis", "amide"},
    "acid": {"acid", "acidic", "tetrazole", "sulfonamide"},
    "amide": {"amide", "nitrile", "urea", "sulfonamide"},
    "phenyl": {"phenyl", "pyridyl", "heteroaryl", "aryl"},
    "basic_amine": {"amine", "basic", "piperidine", "morpholine"},
}


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


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _staged_rows(staging_gate: dict) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for gate_row in staging_gate.get("rows") or []:
        path = Path(str(gate_row.get("template_path") or gate_row.get("path") or ""))
        for csv_row in _read_csv_rows(path):
            item = {key: value for key, value in csv_row.items()}
            item["staging_file"] = str(path)
            item["staging_source_dataset"] = gate_row.get("source_dataset") or item.get("source_dataset") or ""
            rows.append(item)
    return rows


def _tokens_for_candidate(row: dict[str, Any]) -> set[str]:
    text = " ".join(
        str(row.get(field) or "").lower()
        for field in [
            "candidate_id",
            "site_class",
            "qa_bucket",
            "baseline_lineage_status",
            "evidence_summary",
            "local_decision",
            "next_action",
        ]
    )
    tokens = {token for token in text.replace("-", "_").replace("/", "_").split() if token}
    for marker, hints in SITE_TOKEN_HINTS.items():
        if marker in text:
            tokens.update(hints)
    return tokens


def _tokens_for_staged_row(row: dict[str, Any]) -> set[str]:
    text = " ".join(
        str(row.get(field) or "").lower()
        for field in [
            "replacement_id",
            "source_smiles",
            "target_smiles",
            "replacement_class",
            "endpoint_group",
            "direction",
            "notes",
            "provenance_note",
            "source_reference",
            "source_confidence_basis",
        ]
    )
    return {token for token in text.replace("-", "_").replace("/", "_").replace(";", " ").split() if token}


def _matching_staged_rows(candidate: dict[str, Any], staged_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidate_tokens = _tokens_for_candidate(candidate)
    matched = []
    for staged in staged_rows:
        staged_tokens = _tokens_for_staged_row(staged)
        if candidate_tokens & staged_tokens:
            matched.append(staged)
    return matched


def build_staged_feed_sandbox_scoring(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    max_candidates: int = 25,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    matrix = _read_json(project_dir / "candidate_explanation_matrix.json")
    panel = _read_json(project_dir / "candidate_explanation_panel.json")
    staging_gate = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_staging_gate.json")
    simulator = _read_json(root_path / "data/substituents/feed_promotion_simulator.json")
    governed_batches = _read_json(root_path / "data/substituents/governed_ingestion_batches.json")
    staged = _staged_rows(staging_gate)
    candidate_rows = [dict(row) for row in matrix.get("rows") or panel.get("rows") or []][: max(1, int(max_candidates))]

    preview_rows: list[dict[str, Any]] = []
    for source in candidate_rows:
        matched = _matching_staged_rows(source, staged)
        confidence_values = [_number(row.get("source_confidence_score")) for row in matched if row.get("source_confidence_score")]
        confidence_mean = round(sum(confidence_values) / len(confidence_values), 3) if confidence_values else 0.0
        match_count = len(matched)
        score = _number(source.get("score") or source.get("score_component"))
        delta = 0.0 if not staged else round(min(3.0, match_count * 0.35 + confidence_mean * 0.5), 3)
        preview_rows.append(
            {
                "candidate_id": source.get("candidate_id", ""),
                "base_rank": source.get("rank") or source.get("matrix_rank") or "",
                "base_score": score,
                "sandbox_score_preview": round(score + delta, 3),
                "sandbox_score_delta_preview": delta,
                "matching_staged_rule_count": match_count,
                "matched_replacement_ids": ";".join(str(row.get("replacement_id") or "") for row in matched[:8]),
                "staged_confidence_mean": confidence_mean,
                "matrix_bucket": source.get("matrix_bucket", ""),
                "qa_bucket": source.get("qa_bucket", ""),
                "baseline_lineage_status": source.get("baseline_lineage_status", ""),
                "production_scoring_affected": False,
                "sandbox_scope": "staged_feed_preview_only",
                "next_action": "Fill governed staging rows before interpreting score deltas." if not staged else "Review matched staged rules before any promotion or production scoring rebuild.",
            }
        )

    ranked_preview = sorted(preview_rows, key=lambda row: (-_number(row.get("sandbox_score_preview")), str(row.get("candidate_id") or "")))
    rank_by_candidate = {str(row.get("candidate_id") or ""): index for index, row in enumerate(ranked_preview, start=1)}
    for row in preview_rows:
        candidate_id = str(row.get("candidate_id") or "")
        row["sandbox_rank_preview"] = rank_by_candidate.get(candidate_id, "")
        base_rank = _number(row.get("base_rank"))
        row["sandbox_rank_delta_preview"] = round((base_rank or rank_by_candidate.get(candidate_id, 0)) - _number(row.get("sandbox_rank_preview")), 3)

    staged_source_counts = Counter(str(row.get("source_dataset") or row.get("staging_source_dataset") or "unknown") for row in staged)
    status = "blocked" if int(staging_gate.get("blocker_count") or 0) else "awaiting_staged_rows" if not staged else "ready"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "staged_feed_sandbox_scoring",
        "project_name": project_name,
        "candidate_count": len(preview_rows),
        "row_count": len(preview_rows),
        "staged_row_count": len(staged),
        "staged_source_counts": dict(staged_source_counts.most_common()),
        "candidate_with_staged_match_count": sum(1 for row in preview_rows if int(row.get("matching_staged_rule_count") or 0) > 0),
        "max_abs_score_delta_preview": max([abs(_number(row.get("sandbox_score_delta_preview"))) for row in preview_rows] or [0.0]),
        "staging_gate_status": staging_gate.get("status") or "missing",
        "promotion_simulator_status": simulator.get("status") or "missing",
        "governed_ingestion_status": governed_batches.get("status") or "missing",
        "production_scoring_affected": False,
        "rows": preview_rows,
        "recommended_next_actions": [
            "Use sandbox rows to preview staged feed impact before promotion.",
            "Do not let staged rows affect production ranking until promotion simulator, governed ingestion batches, and production CI pass.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_staged_feed_sandbox_scoring_markdown(report: dict) -> str:
    lines = [
        "# Staged Feed Sandbox Scoring",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Staged rows: `{report.get('staged_row_count')}`",
        f"- Production scoring affected: `{report.get('production_scoring_affected')}`",
        "",
        "| Candidate | Base Rank | Sandbox Rank | Base Score | Delta | Matches | Bucket | Next Action |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("base_rank") or ""),
                    str(row.get("sandbox_rank_preview") or ""),
                    str(row.get("base_score") or 0),
                    str(row.get("sandbox_score_delta_preview") or 0),
                    str(row.get("matching_staged_rule_count") or 0),
                    str(row.get("matrix_bucket") or ""),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_staged_feed_sandbox_scoring(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_STAGED_FEED_SANDBOX_JSON,
    csv_path: str | Path | None = DEFAULT_STAGED_FEED_SANDBOX_CSV,
    markdown_path: str | Path | None = DEFAULT_STAGED_FEED_SANDBOX_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "candidate_id",
        "base_rank",
        "sandbox_rank_preview",
        "sandbox_rank_delta_preview",
        "base_score",
        "sandbox_score_preview",
        "sandbox_score_delta_preview",
        "matching_staged_rule_count",
        "matched_replacement_ids",
        "staged_confidence_mean",
        "matrix_bucket",
        "qa_bucket",
        "baseline_lineage_status",
        "production_scoring_affected",
        "sandbox_scope",
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
        md_file.write_text(render_staged_feed_sandbox_scoring_markdown(report), encoding="utf-8")
