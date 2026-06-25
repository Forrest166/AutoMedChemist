from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .profile_ab_replay import build_profile_ab_replay_report


DEFAULT_PROFILE_AB_MATRIX_PATH = Path("data/projects/demo/profile_ab_replay_matrix.json")
DEFAULT_PROFILE_AB_MATRIX_CSV_PATH = Path("data/projects/demo/profile_ab_replay_matrix.csv")
DEFAULT_PROFILE_AB_MATRIX_CACHE_DIR = Path("data/projects/demo/profile_ab_matrix_cache")

DEFAULT_PROFILE_AB_SCENARIOS = [
    {
        "scenario_id": "polarity-default",
        "smiles": "COc1ccc(Cl)cc1",
        "direction": "increase_polarity",
        "target_context": {},
    },
    {
        "scenario_id": "lipophilicity-potency-kinase",
        "smiles": "COc1ccc(Cl)cc1",
        "direction": "reduce_lipophilicity",
        "target_context": {"endpoint_group": "potency", "target_family": "kinase", "assay_type": "IC50"},
    },
    {
        "scenario_id": "stability-gpcr",
        "smiles": "COc1ccc(Cl)cc1",
        "direction": "metabolism_blocking",
        "target_context": {"endpoint_group": "metabolic_stability", "target_family": "gpcr", "assay_type": "microsome"},
    },
    {
        "scenario_id": "solubility-tail",
        "smiles": "COc1ccc(Cl)cc1",
        "direction": "improve_solubility",
        "target_context": {"endpoint_group": "solubility", "target_family": "all", "assay_type": "kinetic_solubility"},
    },
    {
        "scenario_id": "hydrolysis-ester",
        "smiles": "CCOC(=O)c1ccc(Cl)cc1",
        "direction": "reduce_hydrolysis",
        "site_class": "ester",
        "target_context": {"endpoint_group": "stability", "target_family": "all", "assay_type": "plasma_stability", "site_class": "ester"},
    },
    {
        "scenario_id": "methoxy-soft-spot",
        "smiles": "COc1ccc(F)cc1",
        "direction": "metabolism_blocking",
        "site_class": "methoxy_soft_spot",
        "target_context": {"endpoint_group": "metabolic_stability", "target_family": "kinase", "assay_type": "microsome", "site_class": "methoxy_soft_spot"},
    },
    {
        "scenario_id": "basic-amine-solubility",
        "smiles": "CN(C)CCOc1ccc(Cl)cc1",
        "direction": "improve_solubility",
        "site_class": "basic_amine",
        "target_context": {"endpoint_group": "solubility", "target_family": "gpcr", "assay_type": "kinetic_solubility", "site_class": "basic_amine"},
    },
    {
        "scenario_id": "terminal-tail-polarity",
        "smiles": "CCOc1ccc(Cl)cc1",
        "direction": "increase_polarity",
        "site_class": "terminal_tail",
        "target_context": {"endpoint_group": "permeability", "target_family": "kinase", "assay_type": "mdck", "site_class": "terminal_tail"},
    },
    {
        "scenario_id": "aromatic-halide-liability",
        "smiles": "Clc1ccc(OC)cc1Br",
        "direction": "reduce_lipophilicity",
        "site_class": "aromatic_halogen",
        "target_context": {"endpoint_group": "potency", "target_family": "kinase", "assay_type": "IC50", "site_class": "aromatic_halogen"},
    },
]


def _file_sha256(path: str | Path | None) -> str | None:
    if not path:
        return None
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return None
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scenario_cache_key(
    *,
    scenario: dict,
    project_name: str | None,
    base_profile_path: str | Path | None,
    candidate_profile_path: str | Path | None,
    top_n: int,
    max_candidates: int,
    max_substituents: int,
) -> str:
    payload = {
        "scenario": scenario,
        "project_name": project_name,
        "base_profile_path": str(base_profile_path) if base_profile_path else None,
        "candidate_profile_path": str(candidate_profile_path) if candidate_profile_path else None,
        "base_profile_sha256": _file_sha256(base_profile_path),
        "candidate_profile_sha256": _file_sha256(candidate_profile_path),
        "top_n": int(top_n),
        "max_candidates": int(max_candidates),
        "max_substituents": int(max_substituents),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _read_cached_report(cache_path: Path) -> dict | None:
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _write_cached_report(cache_path: Path, report: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def build_profile_ab_replay_matrix(
    *,
    base_profile_path: str | Path | None = None,
    candidate_profile_path: str | Path | None = None,
    project_name: str | None = "demo_learning",
    scenarios: list[dict] | None = None,
    top_n: int = 20,
    max_candidates: int = 30,
    max_substituents: int = 30,
    material_changed_top_n_threshold: int = 3,
    material_score_delta_threshold: float = 5.0,
    cache_dir: str | Path | None = DEFAULT_PROFILE_AB_MATRIX_CACHE_DIR,
    use_cache: bool = True,
    force_refresh: bool = False,
) -> dict:
    scenario_rows = [dict(row) for row in (scenarios or DEFAULT_PROFILE_AB_SCENARIOS)]
    reports = []
    summary_rows = []
    cache_status_counts: Counter[str] = Counter()
    resolved_cache_dir = Path(cache_dir) if cache_dir is not None else None
    for index, scenario in enumerate(scenario_rows, start=1):
        scenario_id = str(scenario.get("scenario_id") or f"scenario-{index}")
        cache_key = _scenario_cache_key(
            scenario=scenario,
            project_name=project_name,
            base_profile_path=base_profile_path,
            candidate_profile_path=candidate_profile_path,
            top_n=top_n,
            max_candidates=max_candidates,
            max_substituents=max_substituents,
        )
        cache_path = resolved_cache_dir / f"{scenario_id}-{cache_key}.json" if resolved_cache_dir else None
        cached = _read_cached_report(cache_path) if use_cache and not force_refresh and cache_path else None
        if cached:
            report = cached
            cache_status = "hit"
        else:
            report = build_profile_ab_replay_report(
                smiles=str(scenario.get("smiles") or "COc1ccc(Cl)cc1"),
                direction=str(scenario.get("direction") or "increase_polarity"),
                base_profile_path=base_profile_path,
                candidate_profile_path=candidate_profile_path,
                project_name=project_name,
                target_context=scenario.get("target_context") or {},
                site_index=int(scenario.get("site_index") or 0),
                top_n=top_n,
                max_candidates=max_candidates,
                max_substituents=max_substituents,
            )
            cache_status = "miss" if use_cache and cache_path else "disabled"
            if use_cache and cache_path:
                _write_cached_report(
                    cache_path,
                    {
                        **report,
                        "scenario_id": scenario_id,
                        "cache_key": cache_key,
                        "cache_created_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
        cache_status_counts[cache_status] += 1
        report["scenario_id"] = scenario_id
        report["cache_key"] = cache_key
        report["cache_status"] = cache_status
        report["cache_path"] = str(cache_path) if cache_path else None
        reports.append(report)
        changed_top_n = int(report.get("changed_top_n_count") or 0)
        max_score_delta = float(report.get("max_score_delta") or 0.0)
        material_change = (
            changed_top_n >= int(material_changed_top_n_threshold)
            or abs(max_score_delta) >= float(material_score_delta_threshold)
            or report.get("review_status") == "review_required"
        )
        summary_rows.append(
            {
                "scenario_id": scenario_id,
                "status": report.get("status"),
                "review_status": report.get("review_status"),
                "smiles": scenario.get("smiles"),
                "direction": scenario.get("direction"),
                "site_class": scenario.get("site_class"),
                "target_context": json.dumps(scenario.get("target_context") or {}, sort_keys=True),
                "changed_top_n_count": changed_top_n,
                "max_score_delta": max_score_delta,
                "mean_score_delta": report.get("mean_score_delta"),
                "material_change": material_change,
                "material_change_reason": (
                    "threshold_exceeded"
                    if material_change
                    else "below_threshold"
                ),
                "cache_status": cache_status,
                "cache_key": cache_key,
                "base_candidate_count": report.get("base_candidate_count"),
                "candidate_candidate_count": report.get("candidate_candidate_count"),
                "shared_candidate_count": report.get("shared_candidate_count"),
            }
        )
    review_required = [row for row in summary_rows if row.get("review_status") == "review_required"]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if summary_rows else "empty",
        "project_name": project_name,
        "base_profile_path": str(Path(base_profile_path).resolve()) if base_profile_path else None,
        "candidate_profile_path": str(Path(candidate_profile_path).resolve()) if candidate_profile_path else None,
        "scenario_count": len(summary_rows),
        "review_required_count": len(review_required),
        "material_change_count": sum(1 for row in summary_rows if row.get("material_change")),
        "material_change_thresholds": {
            "changed_top_n_count": int(material_changed_top_n_threshold),
            "max_score_delta": float(material_score_delta_threshold),
        },
        "cache": {
            "enabled": bool(use_cache and resolved_cache_dir),
            "cache_dir": str(resolved_cache_dir) if resolved_cache_dir else None,
            "force_refresh": bool(force_refresh),
        },
        "cache_status_counts": dict(cache_status_counts.most_common()),
        "cache_hit_count": cache_status_counts.get("hit", 0),
        "cache_miss_count": cache_status_counts.get("miss", 0),
        "status_counts": dict(Counter(str(row.get("status") or "unknown") for row in summary_rows).most_common()),
        "review_status_counts": dict(Counter(str(row.get("review_status") or "unknown") for row in summary_rows).most_common()),
        "max_changed_top_n_count": max((int(row.get("changed_top_n_count") or 0) for row in summary_rows), default=0),
        "max_score_delta": max((float(row.get("max_score_delta") or 0.0) for row in summary_rows), default=0.0),
        "summary_rows": summary_rows,
        "scenario_reports": reports,
    }


def write_profile_ab_replay_matrix(
    report: dict,
    output_path: str | Path = DEFAULT_PROFILE_AB_MATRIX_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_PROFILE_AB_MATRIX_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    rows = [dict(row) for row in report.get("summary_rows") or []]
    fieldnames = [
        "scenario_id",
        "status",
        "review_status",
        "smiles",
        "direction",
        "site_class",
        "target_context",
        "changed_top_n_count",
        "max_score_delta",
        "mean_score_delta",
        "material_change",
        "material_change_reason",
        "cache_status",
        "cache_key",
        "base_candidate_count",
        "candidate_candidate_count",
        "shared_candidate_count",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
