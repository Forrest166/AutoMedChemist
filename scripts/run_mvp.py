from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.pipeline import run_mvp  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 1 local enumeration MVP.")
    parser.add_argument("--smiles", default="COc1ccc(Cl)cc1")
    parser.add_argument("--direction", default="increase_polarity")
    parser.add_argument("--site-index", type=int, default=0)
    parser.add_argument("--library", default=str(ROOT / "data" / "substituents" / "core_substituent_library.yaml"))
    parser.add_argument("--direction-rules", default=str(ROOT / "data" / "rules" / "direction_rules.yaml"))
    parser.add_argument("--scoring-profile", default=None)
    parser.add_argument(
        "--functional-rules",
        default=str(ROOT / "data" / "rules" / "functional_group_replacements.yaml"),
    )
    parser.add_argument("--mmp-evidence", default=str(ROOT / "data" / "mmp" / "chembl_mmp_transform_evidence.yaml"))
    parser.add_argument("--transform-activity-report", default=str(ROOT / "data" / "substituents" / "transform_activity_report.json"))
    parser.add_argument("--evidence-confidence-report", default=str(ROOT / "data" / "substituents" / "evidence_confidence_report.json"))
    parser.add_argument("--public-strategy-signal-report", default=str(ROOT / "data" / "substituents" / "public_strategy_signal_report.json"))
    parser.add_argument("--queue-analog-series-delta", default=str(ROOT / "data" / "projects" / "closed_loop" / "queue_analog_series_delta.json"))
    parser.add_argument("--queue-analog-series-policy", default=str(ROOT / "data" / "rules" / "queue_analog_series_policy.yaml"))
    parser.add_argument("--target-context-profiles", default=str(ROOT / "data" / "rules" / "target_context_profiles.yaml"))
    parser.add_argument("--strategy-learning-policy", default=str(ROOT / "data" / "rules" / "strategy_learning_policy.yaml"))
    parser.add_argument("--rgroup-replacements", default=str(ROOT / "data" / "replacements" / "rgroup_replacements.yaml"))
    parser.add_argument("--ring-replacements", default=str(ROOT / "data" / "replacements" / "ring_replacements.yaml"))
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--target-family", default=None)
    parser.add_argument("--assay-type", default=None)
    parser.add_argument("--endpoint-group", default=None)
    parser.add_argument("--output-dir", default=str(ROOT / "data" / "projects" / "demo"))
    parser.add_argument("--max-candidates", type=int, default=80)
    parser.add_argument("--max-fragment-mw", type=float, default=None)
    parser.add_argument("--include-risky", action="store_true")
    parser.add_argument("--include-advanced", action="store_true")
    parser.add_argument("--disable-substituent-scan", action="store_true")
    parser.add_argument("--disable-functional-replacements", action="store_true")
    parser.add_argument("--disable-replacement-network", action="store_true")
    parser.add_argument("--disable-scaffold-replacements", action="store_true")
    parser.add_argument("--disable-ring-library-recommendations", action="store_true")
    parser.add_argument("--disable-ring-rgroup-joint", action="store_true")
    parser.add_argument("--replacement-network-source-fragment", default=None)
    parser.add_argument("--max-network-replacements", type=int, default=25)
    parser.add_argument("--max-scaffold-replacements", type=int, default=20)
    parser.add_argument("--max-ring-library-recommendations", type=int, default=12)
    parser.add_argument("--max-ring-library-source-rank", type=int, default=5000)
    parser.add_argument("--max-ring-library-per-diversity-bucket", type=int, default=2)
    parser.add_argument("--max-ring-library-similarity", type=float, default=0.86)
    parser.add_argument("--max-ring-rgroup-joint-candidates", type=int, default=8)
    parser.add_argument(
        "--ring-recommendation-cache",
        default=str(ROOT / "data" / "substituents" / "ring_recommendation_cache.json"),
    )
    parser.add_argument("--ring-recommendation-cache-ttl-seconds", type=float, default=86400)
    parser.add_argument("--diverse-top-n", type=int, default=20)
    parser.add_argument("--per-cluster-limit", type=int, default=1)
    parser.add_argument("--novelty-batch-size", type=int, default=24)
    parser.add_argument("--novelty-batch-per-bucket-limit", type=int, default=3)
    parser.add_argument(
        "--score-weights",
        default=None,
        help='Optional JSON object, for example {"direction":0.5,"property":0.2,"similarity":0.1,"synthetic":0.1,"risk":0.1}.',
    )
    args = parser.parse_args()

    score_weights = json.loads(args.score_weights) if args.score_weights else None
    result = run_mvp(
        smiles=args.smiles,
        direction=args.direction,
        library_path=args.library,
        direction_rules_path=args.direction_rules,
        functional_rules_path=args.functional_rules,
        scoring_profile_path=args.scoring_profile,
        mmp_evidence_path=args.mmp_evidence,
        transform_activity_report_path=args.transform_activity_report,
        evidence_confidence_report_path=args.evidence_confidence_report,
        public_strategy_signal_report_path=args.public_strategy_signal_report,
        queue_analog_series_delta_path=args.queue_analog_series_delta,
        queue_analog_series_policy_path=args.queue_analog_series_policy,
        target_context_profiles_path=args.target_context_profiles,
        strategy_learning_policy_path=args.strategy_learning_policy,
        rgroup_replacements_path=args.rgroup_replacements,
        ring_replacements_path=args.ring_replacements,
        db_path=args.db_path,
        project_name=args.project_name,
        target_context={
            "target_family": args.target_family,
            "assay_type": args.assay_type,
            "endpoint_group": args.endpoint_group,
        },
        site_index=args.site_index,
        max_candidates=args.max_candidates,
        max_fragment_mw=args.max_fragment_mw,
        include_risky=args.include_risky,
        include_advanced=args.include_advanced,
        include_substituent_scan=not args.disable_substituent_scan,
        include_functional_replacements=not args.disable_functional_replacements,
        include_replacement_network=not args.disable_replacement_network,
        include_scaffold_replacements=not args.disable_scaffold_replacements,
        include_ring_library_recommendations=not args.disable_ring_library_recommendations,
        include_ring_rgroup_joint=not args.disable_ring_rgroup_joint,
        replacement_network_source_fragment=args.replacement_network_source_fragment,
        max_network_replacements=args.max_network_replacements,
        max_scaffold_replacements=args.max_scaffold_replacements,
        max_ring_library_recommendations=args.max_ring_library_recommendations,
        max_ring_library_source_rank=args.max_ring_library_source_rank,
        max_ring_library_per_diversity_bucket=args.max_ring_library_per_diversity_bucket,
        max_ring_library_similarity=args.max_ring_library_similarity,
        max_ring_rgroup_joint_candidates=args.max_ring_rgroup_joint_candidates,
        ring_recommendation_cache_path=args.ring_recommendation_cache,
        ring_recommendation_cache_ttl_seconds=args.ring_recommendation_cache_ttl_seconds,
        score_weights=score_weights,
        diverse_top_n=args.diverse_top_n,
        per_cluster_limit=args.per_cluster_limit,
        novelty_batch_size=args.novelty_batch_size,
        novelty_batch_per_bucket_limit=args.novelty_batch_per_bucket_limit,
        output_dir=args.output_dir,
    )
    summary = {
        "parent_smiles": result["parent_smiles"],
        "selected_site": result["selected_site"],
        "selected_site_guidance": result.get("selected_site_guidance", {}),
        "site_count": len(result["sites"]),
        "substituent_count": result["substituent_count"],
        "functional_replacement_count": result.get("functional_replacement_count", 0),
        "network_replacement_count": result.get("network_replacement_count", 0),
        "scaffold_replacement_count": result.get("scaffold_replacement_count", 0),
        "ring_library_recommendation_count": result.get("ring_library_recommendation_count", 0),
        "ring_rgroup_joint_recommendation_count": result.get("ring_rgroup_joint_recommendation_count", 0),
        "replacement_network_summary": result.get("replacement_network_summary", {}),
        "ring_library_summary": result.get("ring_library_summary", {}),
        "candidate_count": result["candidate_count"],
        "score_weights": result.get("score_weights"),
        "top_candidates": result["candidates"][:10],
        "diverse_top_candidates": result.get("analysis", {}).get("diverse_top_n", [])[:10],
        "novelty_diversity_batch": result.get("analysis", {}).get("novelty_diversity_batch", [])[:10],
        "novelty_diversity_batch_summary": result.get("analysis", {}).get("novelty_diversity_batch_summary", {}),
        "output_dir": str(Path(args.output_dir).resolve()),
        "enumeration_error_count": len(result["enumeration_errors"]),
        "status_message": result.get("status_message"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
