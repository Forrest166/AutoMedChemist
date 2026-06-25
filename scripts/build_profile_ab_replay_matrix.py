from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.profile_ab_matrix import build_profile_ab_replay_matrix, write_profile_ab_replay_matrix  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a multi-scenario profile A/B replay matrix.")
    parser.add_argument("--base-profile", default=str(ROOT / "data" / "profiles" / "evidence_weighted.yaml"))
    parser.add_argument("--candidate-profile", default=str(ROOT / "data" / "profiles" / "evidence_weighted_residual_adjusted.yaml"))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--max-candidates", type=int, default=30)
    parser.add_argument("--max-substituents", type=int, default=30)
    parser.add_argument("--material-changed-top-n-threshold", type=int, default=3)
    parser.add_argument("--material-score-delta-threshold", type=float, default=5.0)
    parser.add_argument("--cache-dir", default=str(ROOT / "data" / "projects" / "demo" / "profile_ab_matrix_cache"))
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "profile_ab_replay_matrix.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "profile_ab_replay_matrix.csv"))
    args = parser.parse_args()
    report = build_profile_ab_replay_matrix(
        base_profile_path=args.base_profile,
        candidate_profile_path=args.candidate_profile,
        project_name=args.project_name,
        top_n=args.top_n,
        max_candidates=args.max_candidates,
        max_substituents=args.max_substituents,
        material_changed_top_n_threshold=args.material_changed_top_n_threshold,
        material_score_delta_threshold=args.material_score_delta_threshold,
        cache_dir=args.cache_dir,
        use_cache=not args.no_cache,
        force_refresh=args.force_refresh,
    )
    write_profile_ab_replay_matrix(report, args.output, csv_path=args.csv_out)
    print(json.dumps({key: report.get(key) for key in ["status", "scenario_count", "review_required_count", "material_change_count", "review_status_counts", "cache_status_counts", "max_changed_top_n_count", "max_score_delta"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
