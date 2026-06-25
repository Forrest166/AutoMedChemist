from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from compare_release_manifests import _load_manifest, compare_manifests, render_markdown  # noqa: E402


def _latest_release_zips(releases_dir: Path) -> list[Path]:
    return sorted(releases_dir.glob("localmedchem_release_*.zip"), key=lambda path: path.stat().st_mtime)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _sqlite_pair_rows(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT normalized_pair_key,
                       normalized_source_smiles,
                       normalized_target_smiles,
                       aggregate_edge_weight,
                       source_record_count,
                       source_names,
                       source_confidence_tiers
                FROM rgroup_replacement_normalized
                """
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return {}
    out: dict[str, dict] = {}
    for row in rows:
        item = dict(row)
        key = str(item.get("normalized_pair_key") or "").strip()
        if key:
            out[key] = item
    return out


def _report_pair_rows(report: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in report.get("top_duplicate_groups") or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("normalized_pair_key") or "").strip()
        if key:
            out[key] = dict(row)
    return out


def _zip_json(path: Path, member: str) -> dict:
    try:
        with zipfile.ZipFile(path) as archive:
            if member not in archive.namelist():
                return {}
            return json.loads(archive.read(member).decode("utf-8")) or {}
    except Exception:
        return {}


def _zip_sqlite_pair_rows(path: Path, member: str = "data/localmedchem.sqlite") -> dict[str, dict]:
    try:
        with zipfile.ZipFile(path) as archive:
            if member not in archive.namelist():
                return {}
            with tempfile.TemporaryDirectory(prefix="localmedchem_weekly_pair_") as tmpdir:
                sqlite_path = Path(tmpdir) / "localmedchem.sqlite"
                sqlite_path.write_bytes(archive.read(member))
                return _sqlite_pair_rows(sqlite_path)
    except Exception:
        return {}


def _load_normalized_pair_rows(source: str | Path | None, *, root: Path) -> dict[str, dict]:
    if source is None:
        sqlite_rows = _sqlite_pair_rows(root / "data" / "localmedchem.sqlite")
        if sqlite_rows:
            return sqlite_rows
        return _report_pair_rows(_read_json(root / "data" / "substituents" / "rgroup_normalization_report.json"))

    path = Path(source)
    if path.suffix.lower() == ".zip":
        sqlite_rows = _zip_sqlite_pair_rows(path)
        if sqlite_rows:
            return sqlite_rows
        return _report_pair_rows(_zip_json(path, "data/substituents/rgroup_normalization_report.json"))
    if path.suffix.lower() in {".sqlite", ".db"}:
        return _sqlite_pair_rows(path)
    if path.is_dir():
        return _load_normalized_pair_rows(None, root=path)
    return _report_pair_rows(_read_json(path))


def _int(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _pair_delta_row(key: str, base_row: dict | None, head_row: dict | None) -> dict:
    base_row = base_row or {}
    head_row = head_row or {}
    base_weight = _int(base_row.get("aggregate_edge_weight"))
    head_weight = _int(head_row.get("aggregate_edge_weight"))
    base_records = _int(base_row.get("source_record_count"))
    head_records = _int(head_row.get("source_record_count"))
    source = head_row or base_row
    return {
        "normalized_pair_key": key,
        "normalized_source_smiles": source.get("normalized_source_smiles"),
        "normalized_target_smiles": source.get("normalized_target_smiles"),
        "base_aggregate_edge_weight": base_weight,
        "head_aggregate_edge_weight": head_weight,
        "aggregate_edge_weight_delta": head_weight - base_weight,
        "base_source_record_count": base_records,
        "head_source_record_count": head_records,
        "source_record_count_delta": head_records - base_records,
        "head_source_names": head_row.get("source_names"),
        "head_source_confidence_tiers": head_row.get("source_confidence_tiers"),
    }


def normalized_pair_delta_summary(
    *,
    base_rows: dict[str, dict],
    head_rows: dict[str, dict],
    label: str,
    top_n: int = 15,
) -> dict:
    if not base_rows and not head_rows:
        status = "unavailable"
    elif not base_rows:
        status = "no_baseline"
    elif not head_rows:
        status = "no_head"
    else:
        status = "ok"
    base_keys = set(base_rows)
    head_keys = set(head_rows)
    added = [_pair_delta_row(key, None, head_rows[key]) for key in sorted(head_keys - base_keys)]
    removed = [_pair_delta_row(key, base_rows[key], None) for key in sorted(base_keys - head_keys)]
    changed = [
        row
        for key in sorted(base_keys & head_keys)
        for row in [_pair_delta_row(key, base_rows[key], head_rows[key])]
        if row["aggregate_edge_weight_delta"] or row["source_record_count_delta"]
    ]
    changed.sort(
        key=lambda item: (
            -abs(int(item.get("aggregate_edge_weight_delta") or 0)),
            -abs(int(item.get("source_record_count_delta") or 0)),
            str(item.get("normalized_pair_key") or ""),
        )
    )
    added.sort(
        key=lambda item: (
            -int(item.get("head_aggregate_edge_weight") or 0),
            -int(item.get("head_source_record_count") or 0),
            str(item.get("normalized_pair_key") or ""),
        )
    )
    removed.sort(
        key=lambda item: (
            -int(item.get("base_aggregate_edge_weight") or 0),
            -int(item.get("base_source_record_count") or 0),
            str(item.get("normalized_pair_key") or ""),
        )
    )
    return {
        "label": label,
        "status": status,
        "base_pair_count": len(base_rows),
        "head_pair_count": len(head_rows),
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "top_changed": changed[:top_n],
        "top_added": added[:top_n],
        "top_removed": removed[:top_n],
    }


def build_weekly_release_diff_summary(*, root: str | Path = ROOT, base: str | Path | None = None, head: str | Path | None = None, operator_note: str = "") -> dict:
    root_path = Path(root)
    releases_dir = root_path / "data" / "releases"
    zips = _latest_release_zips(releases_dir)
    if head is None and zips:
        head = zips[-1]
    if base is None and len(zips) >= 2:
        base = zips[-2]
    manifest_diff = compare_manifests(_load_manifest(base), _load_manifest(head)) if base and head else _read_json(releases_dir / "manifest_diff_latest.json")
    foundation = _read_json(root_path / "data" / "substituents" / "data_foundation_report.json")
    drift = foundation.get("data_drift") or {}
    table_counts = foundation.get("table_counts") or {}
    rgroup_feed_governance = foundation.get("rgroup_feed_governance") or {}
    owner_packet = _read_json(root_path / "data" / "substituents" / "rgroup_pair_conflict_owner_review_packet.json")
    owner_ledger = _read_json(root_path / "data" / "substituents" / "rgroup_pair_conflict_owner_decision_ledger.json")
    feed_onboarding = _read_json(root_path / "data" / "substituents" / "rgroup_feed_onboarding_gate.json")
    feed_staging = _read_json(root_path / "data" / "substituents" / "rgroup_next_feed_drop_staging.json")
    feed_staging_gate = _read_json(root_path / "data" / "substituents" / "rgroup_next_feed_drop_staging_gate.json")
    feed_promotion = _read_json(root_path / "data" / "substituents" / "rgroup_next_feed_drop_promotion.json")
    ring_readiness = _read_json(root_path / "data" / "projects" / "demo" / "ring_outcome_production_readiness.json")
    ring_package = _read_json(root_path / "data" / "projects" / "demo" / "ring_outcome_result_package.json")
    ring_import_gate = _read_json(root_path / "data" / "projects" / "demo" / "ring_outcome_result_package_import_gate.json")
    ring_holdout = _read_json(root_path / "data" / "projects" / "demo" / "ring_outcome_holdout_report.json")
    base_pair_rows = _load_normalized_pair_rows(base, root=root_path) if base else {}
    head_pair_rows = _load_normalized_pair_rows(head, root=root_path) if head else {}
    current_pair_rows = _load_normalized_pair_rows(None, root=root_path)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "base": str(Path(base).resolve()) if base else None,
        "head": str(Path(head).resolve()) if head else None,
        "release_manifest_diff": manifest_diff,
        "data_drift": {
            "status": drift.get("status"),
            "warning_count": drift.get("warning_count"),
            "error_count": drift.get("error_count"),
            "count_deltas": drift.get("count_deltas") or [],
        },
        "key_table_counts": {
            key: table_counts.get(key)
            for key in [
                "ring_system",
                "rgroup_replacement",
                "rgroup_replacement_normalized",
                "mmp_transform_evidence",
                "chembl_activity_evidence",
                "project_feedback",
            ]
        },
        "rgroup_feed_governance": rgroup_feed_governance,
        "operator_notes": {
            "note": operator_note,
            "rgroup_owner_review": {
                "packet_status": owner_packet.get("status"),
                "ledger_status": owner_ledger.get("status"),
                "deferred_conflict_count": owner_packet.get("deferred_conflict_count"),
                "pending_owner_review_count": owner_packet.get("pending_owner_review_count"),
                "owner_decision_counts": owner_ledger.get("decision_counts") or owner_packet.get("owner_decision_counts") or {},
            },
            "rgroup_feed_onboarding": {
                "status": feed_onboarding.get("status"),
                "feed_file_count": feed_onboarding.get("feed_file_count"),
                "feed_row_count": feed_onboarding.get("feed_row_count"),
                "unmanifested_file_count": feed_onboarding.get("unmanifested_file_count"),
                "pending_source_owner_review_count": feed_onboarding.get("pending_source_owner_review_count"),
                "staging_status": feed_staging.get("status"),
                "staging_template_file_count": feed_staging.get("template_file_count"),
                "staging_gate_status": feed_staging_gate.get("status"),
                "staging_gate_row_count": feed_staging_gate.get("staged_row_count"),
                "staging_gate_blocker_count": feed_staging_gate.get("blocker_count"),
                "staging_gate_warning_count": feed_staging_gate.get("warning_count"),
                "promotion_status": feed_promotion.get("status"),
                "promoted_row_count": feed_promotion.get("promoted_row_count"),
            },
            "ring_outcome": {
                "readiness_status": ring_readiness.get("status"),
                "importable_result_count": ring_readiness.get("importable_result_count"),
                "pending_result_count": ring_readiness.get("pending_result_count"),
                "result_package_status": ring_package.get("status"),
                "result_package_row_count": ring_package.get("result_row_count"),
                "result_package_importable_count": ring_package.get("importable_result_count"),
                "import_gate_status": ring_import_gate.get("status"),
                "import_attempted": ring_import_gate.get("import_attempted"),
                "holdout_status": ring_holdout.get("status"),
                "holdout_ready_endpoint_count": ring_holdout.get("holdout_ready_endpoint_count"),
            },
        },
        "normalized_pair_deltas": {
            "release": normalized_pair_delta_summary(
                base_rows=base_pair_rows,
                head_rows=head_pair_rows,
                label="base_vs_head_release",
            ),
            "workspace_since_head": normalized_pair_delta_summary(
                base_rows=head_pair_rows,
                head_rows=current_pair_rows,
                label="head_release_vs_workspace",
            ),
        },
    }


def render_weekly_markdown(report: dict) -> str:
    def pct(value: object) -> str:
        if value in {None, ""}:
            return ""
        try:
            return f"{float(value) * 100:.1f}%"
        except (TypeError, ValueError):
            return str(value)

    lines = [
        "# Weekly Release And Data Diff Summary",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Base: `{report.get('base')}`",
        f"- Head: `{report.get('head')}`",
        "",
        "## Release Manifest",
        "",
        render_markdown(report.get("release_manifest_diff") or {}),
        "",
        "## Key Table Counts",
        "",
    ]
    for key, value in (report.get("key_table_counts") or {}).items():
        lines.append(f"- `{key}`: `{value}`")
    feed_governance = report.get("rgroup_feed_governance") or {}
    operator_notes = report.get("operator_notes") or {}
    if operator_notes:
        owner = operator_notes.get("rgroup_owner_review") or {}
        feed = operator_notes.get("rgroup_feed_onboarding") or {}
        ring = operator_notes.get("ring_outcome") or {}
        lines.extend(
            [
                "",
                "## Operator Notes",
                "",
                f"- Note: `{operator_notes.get('note') or ''}`",
                f"- R-group owner review: packet `{owner.get('packet_status')}`, ledger `{owner.get('ledger_status')}`, deferred `{owner.get('deferred_conflict_count')}`, pending `{owner.get('pending_owner_review_count')}`, decisions `{owner.get('owner_decision_counts')}`",
                f"- Feed onboarding: status `{feed.get('status')}`, files `{feed.get('feed_file_count')}`, rows `{feed.get('feed_row_count')}`, unmanifested `{feed.get('unmanifested_file_count')}`, pending owner review `{feed.get('pending_source_owner_review_count')}`",
                f"- Feed staging: status `{feed.get('staging_status')}`, template files `{feed.get('staging_template_file_count')}`, gate `{feed.get('staging_gate_status')}`, staged rows `{feed.get('staging_gate_row_count')}`, blockers `{feed.get('staging_gate_blocker_count')}`, promotion `{feed.get('promotion_status')}`",
                f"- Ring outcome: readiness `{ring.get('readiness_status')}`, package `{ring.get('result_package_status')}`, import gate `{ring.get('import_gate_status')}`, holdout `{ring.get('holdout_status')}`, importable `{ring.get('importable_result_count')}`, pending `{ring.get('pending_result_count')}`",
            ]
        )
    if feed_governance.get("available"):
        lines.extend(
            [
                "",
                "## R-group Feed Governance",
                "",
                f"- Status: `{feed_governance.get('status')}`",
                f"- Feeds / rows: `{feed_governance.get('feed_count')}` / `{feed_governance.get('row_count')}`",
                f"- Row-count delta: `{feed_governance.get('row_count_delta')}`",
                f"- Provenance completeness: `{pct(feed_governance.get('provenance_complete_fraction'))}`",
                f"- Allowlist / freshness issues: `{feed_governance.get('allowlist_issue_count')}` / `{feed_governance.get('freshness_issue_count')}`",
                f"- Review coverage cells: `{feed_governance.get('covered_count')}` covered, `{feed_governance.get('no_review_count')}` no-review, `{feed_governance.get('low_coverage_count')}` low-coverage",
                "",
                "| Feed | Rows | Delta | Provenance |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for row in feed_governance.get("per_feed") or []:
            lines.append(
                f"| `{row.get('feed_name')}` | {row.get('row_count')} | {row.get('row_count_delta')} | {pct(row.get('provenance_complete_fraction'))} |"
            )
    pair_deltas = report.get("normalized_pair_deltas") or {}
    if pair_deltas:
        lines.extend(["", "## Normalized Pair Deltas", ""])
        for section_key, section_title in [
            ("release", "Release base -> head"),
            ("workspace_since_head", "Head release -> workspace"),
        ]:
            section = pair_deltas.get(section_key) or {}
            if not section:
                continue
            lines.extend(
                [
                    f"### {section_title}",
                    "",
                    f"- Status: `{section.get('status')}`",
                    f"- Pair counts: `{section.get('base_pair_count')}` -> `{section.get('head_pair_count')}`",
                    f"- Added / changed / removed: `{section.get('added_count')}` / `{section.get('changed_count')}` / `{section.get('removed_count')}`",
                    "",
                ]
            )
            changed = section.get("top_changed") or []
            if changed:
                lines.extend(["| Pair | Weight delta | Records delta | Head sources |", "| --- | ---: | ---: | --- |"])
                for row in changed[:10]:
                    lines.append(
                        "| {pair} | {weight} | {records} | {sources} |".format(
                            pair=str(row.get("normalized_pair_key") or "").replace("|", "\\|"),
                            weight=row.get("aggregate_edge_weight_delta") or 0,
                            records=row.get("source_record_count_delta") or 0,
                            sources=str(row.get("head_source_names") or "").replace("|", "\\|"),
                        )
                    )
                lines.append("")
            added = section.get("top_added") or []
            if added:
                lines.extend(["| Added pair | Head weight | Head records | Head sources |", "| --- | ---: | ---: | --- |"])
                for row in added[:10]:
                    lines.append(
                        "| {pair} | {weight} | {records} | {sources} |".format(
                            pair=str(row.get("normalized_pair_key") or "").replace("|", "\\|"),
                            weight=row.get("head_aggregate_edge_weight") or 0,
                            records=row.get("head_source_record_count") or 0,
                            sources=str(row.get("head_source_names") or "").replace("|", "\\|"),
                        )
                    )
                lines.append("")
    data_drift = report.get("data_drift") or {}
    lines.extend(
        [
            "",
            "## Data Drift",
            "",
            f"- Status: `{data_drift.get('status')}`",
            f"- Warnings: `{data_drift.get('warning_count')}`",
            f"- Errors: `{data_drift.get('error_count')}`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a weekly release manifest and data-count diff summary.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--base", default=None)
    parser.add_argument("--head", default=None)
    parser.add_argument("--json-out", default=str(ROOT / "data" / "releases" / "weekly_release_diff_summary.json"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs" / "weekly_release_diff_summary.md"))
    parser.add_argument("--operator-note", default="")
    args = parser.parse_args()
    report = build_weekly_release_diff_summary(root=args.root, base=args.base, head=args.head, operator_note=args.operator_note)
    Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json_out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    Path(args.markdown_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.markdown_out).write_text(render_weekly_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
