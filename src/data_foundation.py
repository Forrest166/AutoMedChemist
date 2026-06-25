from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .database import initialize_database, insert_data_foundation_snapshot
from .manifest import file_sha256
from .ring_import_status import build_ring_import_status


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")
DEFAULT_DRIFT_THRESHOLDS_PATH = Path("data/rules/data_drift_thresholds.yaml")
DEFAULT_SOURCE_ACCEPTANCE_MANIFEST_PATH = Path("data/rules/source_acceptance_manifest.yaml")

DEFAULT_ASSETS = [
    {
        "asset_id": "core_substituent_library",
        "category": "substituent_library",
        "path": "data/substituents/core_substituent_library.yaml",
        "db_table": "substituent",
        "purpose": "Governed substituent records used by enumeration and scoring.",
    },
    {
        "asset_id": "review_queue",
        "category": "governance",
        "path": "data/substituents/review_queue.csv",
        "purpose": "Human review worklist for substituent approval and blocking.",
    },
    {
        "asset_id": "substituent_version_diff_browser",
        "category": "substituent_library",
        "path": "data/substituents/substituent_version_diff_browser.json",
        "purpose": "Version/review diff browser linking substituent records, context constraints, and current candidate impact.",
    },
    {
        "asset_id": "substituent_version_diff_browser_csv",
        "category": "substituent_library",
        "path": "data/substituents/substituent_version_diff_browser.csv",
        "purpose": "Tabular substituent version diff and candidate-impact rows.",
    },
    {
        "asset_id": "substituent_version_diff_browser_md",
        "category": "substituent_library",
        "path": "docs/substituent_version_diff_browser.md",
        "purpose": "Markdown substituent version diff browser handoff.",
    },
    {
        "asset_id": "candidate_sources",
        "category": "staging",
        "path": "data/sources",
        "db_table": "candidate_substituent",
        "purpose": "Staged public-data substituent candidates before promotion.",
    },
    {
        "asset_id": "mmp_transform_evidence",
        "category": "evidence",
        "path": "data/mmp/chembl_mmp_transform_evidence.yaml",
        "db_table": "mmp_transform_evidence",
        "purpose": "Public matched molecular pair transform evidence.",
    },
    {
        "asset_id": "chembl_activity_evidence",
        "category": "evidence",
        "path": "data/activity/chembl_activity_evidence.yaml",
        "db_table": "chembl_activity_evidence",
        "purpose": "Target-level ChEMBL activity evidence for transform context.",
    },
    {
        "asset_id": "ring_system_library",
        "category": "ring_scaffold",
        "path": "data/rings/ring_system_library.yaml",
        "db_table": "ring_system",
        "purpose": "Drug, clinical, and imported medchem ring-system records.",
    },
    {
        "asset_id": "literature_substituents",
        "category": "literature_substituent",
        "path": "data/substituents/literature_substituent_library.yaml",
        "db_table": "literature_substituent",
        "purpose": "Literature-derived natural-product substituent patterns.",
    },
    {
        "asset_id": "ring_replacements",
        "category": "replacement_network",
        "path": "data/replacements/ring_replacements.yaml",
        "db_table": "ring_replacement",
        "purpose": "Ertl ring replacement network used for SAR-neighborhood and generation.",
    },
    {
        "asset_id": "rgroup_replacements",
        "category": "replacement_network",
        "path": "data/replacements/rgroup_replacements.yaml",
        "db_table": "rgroup_replacement",
        "purpose": "Bajorath R-group replacement network used for SAR-neighborhood and generation.",
    },
    {
        "asset_id": "rgroup_normalization_report",
        "category": "replacement_network",
        "path": "data/substituents/rgroup_normalization_report.json",
        "db_table": "rgroup_replacement_normalized",
        "purpose": "Normalized and de-duplicated R-group endpoint pairs with source provenance.",
    },
    {
        "asset_id": "rgroup_source_expansion_report",
        "category": "replacement_network",
        "path": "data/substituents/rgroup_source_expansion_report.json",
        "purpose": "Source expansion report for Bajorath seed rows plus public MMP-derived R-group replacements.",
    },
    {
        "asset_id": "rgroup_feed_metadata_report",
        "category": "governance",
        "path": "data/substituents/rgroup_feed_metadata_report.json",
        "purpose": "Row-level provenance, allowlist, freshness, and feed-count governance report for R-group source feeds.",
    },
    {
        "asset_id": "feed_absorption_audit",
        "category": "governance",
        "path": "data/substituents/feed_absorption_audit.json",
        "purpose": "Unified audit for manifest, review coverage, owner ledger, normalization, contradiction, staging, and promotion gates before feed absorption.",
    },
    {
        "asset_id": "feed_absorption_audit_csv",
        "category": "governance",
        "path": "data/substituents/feed_absorption_audit.csv",
        "purpose": "Tabular feed absorption audit gates.",
    },
    {
        "asset_id": "feed_absorption_audit_md",
        "category": "governance",
        "path": "docs/feed_absorption_audit.md",
        "purpose": "Markdown feed absorption audit handoff.",
    },
    {
        "asset_id": "feed_absorption_diff_navigator",
        "category": "governance",
        "path": "data/substituents/feed_absorption_diff_navigator.json",
        "purpose": "Drill-down navigator for feed row deltas, duplicate normalized pairs, owner-ledger reuse, and coverage gaps.",
    },
    {
        "asset_id": "feed_absorption_diff_navigator_csv",
        "category": "governance",
        "path": "data/substituents/feed_absorption_diff_navigator.csv",
        "purpose": "Tabular feed absorption drill-down rows.",
    },
    {
        "asset_id": "feed_absorption_diff_navigator_md",
        "category": "governance",
        "path": "docs/feed_absorption_diff_navigator.md",
        "purpose": "Markdown feed absorption drill-down handoff.",
    },
    {
        "asset_id": "source_expansion_governance",
        "category": "governance",
        "path": "data/substituents/source_expansion_governance.json",
        "purpose": "Governance-only guard for expanding ring, R-group, literature-substituent, and substituent sources.",
    },
    {
        "asset_id": "source_expansion_governance_csv",
        "category": "governance",
        "path": "data/substituents/source_expansion_governance.csv",
        "purpose": "Tabular source expansion governance gate rows.",
    },
    {
        "asset_id": "source_expansion_governance_md",
        "category": "governance",
        "path": "docs/source_expansion_governance.md",
        "purpose": "Markdown source expansion governance handoff.",
    },
    {
        "asset_id": "feed_promotion_simulator",
        "category": "governance",
        "path": "data/substituents/feed_promotion_simulator.json",
        "purpose": "Pre-promotion simulator for staged feed-row impact, duplicate watch, owner reuse, and coverage gaps.",
    },
    {
        "asset_id": "feed_promotion_simulator_csv",
        "category": "governance",
        "path": "data/substituents/feed_promotion_simulator.csv",
        "purpose": "Tabular feed-promotion simulation rows.",
    },
    {
        "asset_id": "feed_promotion_simulator_md",
        "category": "governance",
        "path": "docs/feed_promotion_simulator.md",
        "purpose": "Markdown feed-promotion simulator handoff.",
    },
    {
        "asset_id": "rgroup_staging_quality_budget",
        "category": "governance",
        "path": "data/substituents/rgroup_staging_quality_budget.json",
        "purpose": "Source-level row caps, duplicate thresholds, provenance completeness, and signoff prerequisites for staged R-group feed rows.",
    },
    {
        "asset_id": "rgroup_staging_quality_budget_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_staging_quality_budget.csv",
        "purpose": "Tabular source-level staging quality budget rows.",
    },
    {
        "asset_id": "rgroup_staging_quality_budget_md",
        "category": "governance",
        "path": "docs/rgroup_staging_quality_budget.md",
        "purpose": "Markdown staging quality budget handoff.",
    },
    {
        "asset_id": "rgroup_staging_admission_scorecard",
        "category": "governance",
        "path": "data/substituents/rgroup_staging_admission_scorecard.json",
        "purpose": "Native-readable staged-source admission scorecard for governed R-group feed review.",
    },
    {
        "asset_id": "rgroup_staging_admission_scorecard_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_staging_admission_scorecard.csv",
        "purpose": "Tabular staged-source admission scorecard.",
    },
    {
        "asset_id": "rgroup_staging_admission_scorecard_md",
        "category": "governance",
        "path": "docs/rgroup_staging_admission_scorecard.md",
        "purpose": "Markdown staged-source admission scorecard handoff.",
    },
    {
        "asset_id": "rgroup_staging_fill_report",
        "category": "governance",
        "path": "data/substituents/rgroup_staging_fill_report.json",
        "purpose": "Reviewed-source fill report for provenance-complete rows staged into the next R-group feed drop.",
    },
    {
        "asset_id": "rgroup_staging_fill_report_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_staging_fill_report.csv",
        "purpose": "Tabular reviewed-source staging fill report.",
    },
    {
        "asset_id": "rgroup_staging_fill_report_md",
        "category": "governance",
        "path": "docs/rgroup_staging_fill_report.md",
        "purpose": "Markdown reviewed-source staging fill handoff.",
    },
    {
        "asset_id": "governed_ingestion_batches",
        "category": "governance",
        "path": "data/substituents/governed_ingestion_batches.json",
        "purpose": "Governed intake batch plan for ring, R-group, substituent, and literature source expansion.",
    },
    {
        "asset_id": "governed_ingestion_batches_csv",
        "category": "governance",
        "path": "data/substituents/governed_ingestion_batches.csv",
        "purpose": "Tabular governed ingestion batch rows.",
    },
    {
        "asset_id": "governed_ingestion_batches_md",
        "category": "governance",
        "path": "docs/governed_ingestion_batches.md",
        "purpose": "Markdown governed ingestion batch handoff.",
    },
    {
        "asset_id": "staged_feed_sandbox_scoring",
        "category": "governance",
        "path": "data/projects/demo/staged_feed_sandbox_scoring.json",
        "purpose": "Sandbox-only preview of staged feed effects on candidate scores before production promotion.",
    },
    {
        "asset_id": "staged_feed_sandbox_scoring_csv",
        "category": "governance",
        "path": "data/projects/demo/staged_feed_sandbox_scoring.csv",
        "purpose": "Tabular staged-feed sandbox scoring preview rows.",
    },
    {
        "asset_id": "staged_feed_sandbox_scoring_md",
        "category": "governance",
        "path": "docs/staged_feed_sandbox_scoring.md",
        "purpose": "Markdown staged-feed sandbox scoring handoff.",
    },
    {
        "asset_id": "sandbox_score_delta_review_packet",
        "category": "governance",
        "path": "data/projects/demo/sandbox_score_delta_review_packet.json",
        "purpose": "Operator signoff packet for staged-feed sandbox score and rank deltas before production scoring can be affected.",
    },
    {
        "asset_id": "sandbox_score_delta_review_packet_csv",
        "category": "governance",
        "path": "data/projects/demo/sandbox_score_delta_review_packet.csv",
        "purpose": "Tabular sandbox score-delta review rows.",
    },
    {
        "asset_id": "sandbox_score_delta_review_packet_md",
        "category": "governance",
        "path": "docs/sandbox_score_delta_review_packet.md",
        "purpose": "Markdown sandbox score-delta review handoff.",
    },
    {
        "asset_id": "sandbox_score_delta_signoff_ledger",
        "category": "governance",
        "path": "data/projects/demo/sandbox_score_delta_signoff_ledger.json",
        "purpose": "Operator decision ledger for sandbox score-delta review rows.",
    },
    {
        "asset_id": "sandbox_score_delta_signoff_ledger_csv",
        "category": "governance",
        "path": "data/projects/demo/sandbox_score_delta_signoff_ledger.csv",
        "purpose": "Tabular operator decision ledger for sandbox score-delta review rows.",
    },
    {
        "asset_id": "sandbox_score_delta_signoff_ledger_md",
        "category": "governance",
        "path": "docs/sandbox_score_delta_signoff_ledger.md",
        "purpose": "Markdown sandbox score-delta signoff ledger handoff.",
    },
    {
        "asset_id": "rgroup_feed_digestion_ledger",
        "category": "governance",
        "path": "data/substituents/rgroup_feed_digestion_ledger.json",
        "purpose": "Row-level digestion ledger classifying staged R-group feed rows as accepted, deferred, rejected, or held out.",
    },
    {
        "asset_id": "rgroup_feed_digestion_ledger_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_feed_digestion_ledger.csv",
        "purpose": "Tabular R-group feed digestion ledger.",
    },
    {
        "asset_id": "rgroup_feed_digestion_ledger_md",
        "category": "governance",
        "path": "docs/rgroup_feed_digestion_ledger.md",
        "purpose": "Markdown R-group feed digestion ledger handoff.",
    },
    {
        "asset_id": "staging_sandbox_filter_views",
        "category": "governance",
        "path": "data/projects/demo/staging_sandbox_filter_views.json",
        "purpose": "Native-filterable slices for staging budget blockers, sandbox risk/review status, signoff decisions, and digestion statuses.",
    },
    {
        "asset_id": "staging_sandbox_filter_views_csv",
        "category": "governance",
        "path": "data/projects/demo/staging_sandbox_filter_views.csv",
        "purpose": "Tabular staging/sandbox filter views.",
    },
    {
        "asset_id": "staging_sandbox_filter_views_md",
        "category": "governance",
        "path": "docs/staging_sandbox_filter_views.md",
        "purpose": "Markdown staging/sandbox filter view handoff.",
    },
    {
        "asset_id": "rgroup_promotion_approval_decisions_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_promotion_approval_decisions.csv",
        "purpose": "Reviewer-editable template for selective staged R-group promotion approval.",
    },
    {
        "asset_id": "rgroup_promotion_approval_ledger",
        "category": "governance",
        "path": "data/substituents/rgroup_promotion_approval_ledger.json",
        "purpose": "Row-level promotion approval ledger binding staged checksums, source owners, promotion diffs, and digestion status.",
    },
    {
        "asset_id": "rgroup_promotion_approval_ledger_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_promotion_approval_ledger.csv",
        "purpose": "Tabular R-group promotion approval ledger.",
    },
    {
        "asset_id": "rgroup_promotion_approval_ledger_md",
        "category": "governance",
        "path": "docs/rgroup_promotion_approval_ledger.md",
        "purpose": "Markdown R-group promotion approval handoff.",
    },
    {
        "asset_id": "rgroup_digestion_quality_metrics",
        "category": "governance",
        "path": "data/substituents/rgroup_digestion_quality_metrics.json",
        "purpose": "Quality metrics for staged R-group digestion by source, confidence, endpoint, duplicate pressure, and candidate impact.",
    },
    {
        "asset_id": "rgroup_digestion_quality_metrics_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_digestion_quality_metrics.csv",
        "purpose": "Tabular R-group digestion quality metrics.",
    },
    {
        "asset_id": "rgroup_digestion_quality_metrics_md",
        "category": "governance",
        "path": "docs/rgroup_digestion_quality_metrics.md",
        "purpose": "Markdown R-group digestion quality metrics handoff.",
    },
    {
        "asset_id": "rgroup_selective_approval_batch",
        "category": "governance",
        "path": "data/substituents/rgroup_selective_approval_batch.json",
        "purpose": "Positive-control R-group approval batch that approves only provenance-clear high-confidence rows while keeping production promotion disabled.",
    },
    {
        "asset_id": "rgroup_selective_approval_batch_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_selective_approval_batch.csv",
        "purpose": "Tabular selective R-group approval batch.",
    },
    {
        "asset_id": "rgroup_selective_approval_batch_md",
        "category": "governance",
        "path": "docs/rgroup_selective_approval_batch.md",
        "purpose": "Markdown selective R-group approval batch handoff.",
    },
    {
        "asset_id": "rgroup_digestion_quality_closure_queue",
        "category": "governance",
        "path": "data/substituents/rgroup_digestion_quality_closure_queue.json",
        "purpose": "Owner-routed closure queue for R-group digestion quality watch slices.",
    },
    {
        "asset_id": "rgroup_digestion_quality_closure_queue_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_digestion_quality_closure_queue.csv",
        "purpose": "Tabular digestion quality closure queue.",
    },
    {
        "asset_id": "rgroup_digestion_quality_closure_queue_md",
        "category": "governance",
        "path": "docs/rgroup_digestion_quality_closure_queue.md",
        "purpose": "Markdown digestion quality closure queue handoff.",
    },
    {
        "asset_id": "feed_promotion_rollback_audit",
        "category": "governance",
        "path": "data/substituents/feed_promotion_rollback_audit.json",
        "purpose": "Rollback replay checkpoint for approved staged R-group feed promotion rows.",
    },
    {
        "asset_id": "feed_promotion_rollback_audit_csv",
        "category": "governance",
        "path": "data/substituents/feed_promotion_rollback_audit.csv",
        "purpose": "Tabular feed promotion rollback audit.",
    },
    {
        "asset_id": "feed_promotion_rollback_audit_md",
        "category": "governance",
        "path": "docs/feed_promotion_rollback_audit.md",
        "purpose": "Markdown feed promotion rollback audit handoff.",
    },
    {
        "asset_id": "rgroup_approval_workbench",
        "category": "governance",
        "path": "data/substituents/rgroup_approval_workbench.json",
        "purpose": "Native-filterable R-group promotion approval workbench.",
    },
    {
        "asset_id": "rgroup_approval_workbench_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_approval_workbench.csv",
        "purpose": "Tabular R-group approval workbench.",
    },
    {
        "asset_id": "rgroup_approval_workbench_md",
        "category": "governance",
        "path": "docs/rgroup_approval_workbench.md",
        "purpose": "Markdown R-group approval workbench handoff.",
    },
    {
        "asset_id": "rgroup_ring_context_alignment",
        "category": "governance",
        "path": "data/substituents/rgroup_ring_context_alignment.json",
        "purpose": "Ring plus R-group alignment layer for replacement-axis governance.",
    },
    {
        "asset_id": "rgroup_ring_context_alignment_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_ring_context_alignment.csv",
        "purpose": "Tabular R-group ring-context alignment.",
    },
    {
        "asset_id": "rgroup_ring_context_alignment_md",
        "category": "governance",
        "path": "docs/rgroup_ring_context_alignment.md",
        "purpose": "Markdown R-group ring-context alignment handoff.",
    },
    {
        "asset_id": "rgroup_digestion_quality_closure_ledger",
        "category": "governance",
        "path": "data/substituents/rgroup_digestion_quality_closure_ledger.json",
        "purpose": "Signed conservative closure ledger for R-group digestion quality tasks.",
    },
    {
        "asset_id": "rgroup_digestion_quality_closure_ledger_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_digestion_quality_closure_ledger.csv",
        "purpose": "Tabular R-group digestion quality closure decisions.",
    },
    {
        "asset_id": "rgroup_digestion_quality_closure_ledger_md",
        "category": "governance",
        "path": "docs/rgroup_digestion_quality_closure_ledger.md",
        "purpose": "Markdown R-group digestion quality closure ledger handoff.",
    },
    {
        "asset_id": "rgroup_approval_workbench_decisions",
        "category": "governance",
        "path": "data/substituents/rgroup_approval_workbench_decisions.json",
        "purpose": "Signed local decisions for the native R-group approval workbench.",
    },
    {
        "asset_id": "rgroup_approval_workbench_decisions_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_approval_workbench_decisions.csv",
        "purpose": "Tabular local R-group approval workbench decisions.",
    },
    {
        "asset_id": "rgroup_approval_workbench_decisions_md",
        "category": "governance",
        "path": "docs/rgroup_approval_workbench_decisions.md",
        "purpose": "Markdown local R-group approval workbench decisions.",
    },
    {
        "asset_id": "rgroup_guarded_promotion_rehearsal",
        "category": "governance",
        "path": "data/substituents/rgroup_guarded_promotion_rehearsal.json",
        "purpose": "Rollback-backed dry-run promotion rehearsal for approved positive-control R-group rows.",
    },
    {
        "asset_id": "rgroup_guarded_promotion_rehearsal_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_guarded_promotion_rehearsal.csv",
        "purpose": "Tabular R-group guarded promotion rehearsal rows.",
    },
    {
        "asset_id": "rgroup_guarded_promotion_rehearsal_md",
        "category": "governance",
        "path": "docs/rgroup_guarded_promotion_rehearsal.md",
        "purpose": "Markdown R-group guarded promotion rehearsal handoff.",
    },
    {
        "asset_id": "ring_rgroup_axis_governance",
        "category": "governance",
        "path": "data/substituents/ring_rgroup_axis_governance.json",
        "purpose": "First-class governance budgets for ring and R-group modification axes.",
    },
    {
        "asset_id": "ring_rgroup_axis_governance_csv",
        "category": "governance",
        "path": "data/substituents/ring_rgroup_axis_governance.csv",
        "purpose": "Tabular ring/R-group axis governance rows.",
    },
    {
        "asset_id": "ring_rgroup_axis_governance_md",
        "category": "governance",
        "path": "docs/ring_rgroup_axis_governance.md",
        "purpose": "Markdown ring/R-group axis governance handoff.",
    },
    {
        "asset_id": "rgroup_next_expansion_batch_plan",
        "category": "governance",
        "path": "data/substituents/rgroup_next_expansion_batch_plan.json",
        "purpose": "Governed next-batch expansion plan for analog-series and literature R-group source drops.",
    },
    {
        "asset_id": "rgroup_next_expansion_batch_plan_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_next_expansion_batch_plan.csv",
        "purpose": "Tabular next R-group expansion batch plan.",
    },
    {
        "asset_id": "rgroup_next_expansion_batch_plan_md",
        "category": "governance",
        "path": "docs/rgroup_next_expansion_batch_plan.md",
        "purpose": "Markdown next R-group expansion batch plan.",
    },
    {
        "asset_id": "rgroup_approval_trend_views",
        "category": "governance",
        "path": "data/substituents/rgroup_approval_trend_views.json",
        "purpose": "Trend views for R-group approval outcomes, quality closure, rollback readiness, axis distribution, and expansion capacity.",
    },
    {
        "asset_id": "rgroup_approval_trend_views_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_approval_trend_views.csv",
        "purpose": "Tabular R-group approval trend views.",
    },
    {
        "asset_id": "rgroup_approval_trend_views_md",
        "category": "governance",
        "path": "docs/rgroup_approval_trend_views.md",
        "purpose": "Markdown R-group approval trend views.",
    },
    {
        "asset_id": "rgroup_feed_review_coverage",
        "category": "governance",
        "path": "data/substituents/rgroup_feed_review_coverage.json",
        "purpose": "Coverage report for sample review decisions across R-group feed source, replacement-class, and endpoint strata.",
    },
    {
        "asset_id": "rgroup_feed_sample_review_queue",
        "category": "governance",
        "path": "data/substituents/rgroup_feed_sample_review_queue.csv",
        "purpose": "Sampled R-group feed rows requiring or recording source-level review decisions.",
    },
    {
        "asset_id": "rgroup_normalized_pair_contradictions",
        "category": "governance",
        "path": "data/substituents/rgroup_normalized_pair_contradictions.json",
        "purpose": "Review queue for governed R-group feed rows that point opposite to high-support normalized-pair evidence.",
    },
    {
        "asset_id": "rgroup_normalized_pair_contradiction_reviews",
        "category": "governance",
        "path": "data/substituents/rgroup_normalized_pair_contradiction_reviews.csv",
        "purpose": "Operator decisions for normalized-pair contradiction rows, including context-dependent, deferred, and reverse-preferred classifications.",
    },
    {
        "asset_id": "rgroup_normalized_pair_contradiction_decisions",
        "category": "governance",
        "path": "data/substituents/rgroup_normalized_pair_contradiction_decisions.json",
        "purpose": "Decision summary for normalized-pair contradiction governance and production release checks.",
    },
    {
        "asset_id": "rgroup_pair_conflict_owner_review_packet",
        "category": "governance",
        "path": "data/substituents/rgroup_pair_conflict_owner_review_packet.json",
        "purpose": "Source-owner review packet for pair conflicts kept deferred after first-pass contradiction triage.",
    },
    {
        "asset_id": "rgroup_pair_conflict_owner_review_packet_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_pair_conflict_owner_review_packet.csv",
        "purpose": "Tabular owner-scoped review packet for deferred pair conflicts.",
    },
    {
        "asset_id": "rgroup_pair_conflict_owner_decision_ledger",
        "category": "governance",
        "path": "data/substituents/rgroup_pair_conflict_owner_decision_ledger.json",
        "purpose": "Source-owner decision ledger for deferred pair conflicts, including conservative keep-deferred records.",
    },
    {
        "asset_id": "rgroup_pair_conflict_owner_decision_ledger_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_pair_conflict_owner_decision_ledger.csv",
        "purpose": "Tabular source-owner decision ledger for deferred pair conflicts.",
    },
    {
        "asset_id": "rgroup_feed_onboarding_gate",
        "category": "governance",
        "path": "data/substituents/rgroup_feed_onboarding_gate.json",
        "purpose": "Pre-expansion onboarding gate for the next large R-group feed drop.",
    },
    {
        "asset_id": "rgroup_feed_onboarding_gate_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_feed_onboarding_gate.csv",
        "purpose": "Per-feed onboarding gate rows covering manifest coverage and required columns.",
    },
    {
        "asset_id": "rgroup_feed_onboarding_template",
        "category": "replacement_network",
        "path": "data/replacements/feed_onboarding_template.csv",
        "purpose": "Column template for source-specific governed R-group feed drops.",
    },
    {
        "asset_id": "rgroup_next_feed_drop_staging",
        "category": "replacement_network",
        "path": "data/substituents/rgroup_next_feed_drop_staging.json",
        "purpose": "Staging report for the next source-specific R-group feed drop templates.",
    },
    {
        "asset_id": "rgroup_next_feed_drop_staging_csv",
        "category": "replacement_network",
        "path": "data/substituents/rgroup_next_feed_drop_staging.csv",
        "purpose": "Tabular staging rows for next R-group feed-drop templates.",
    },
    {
        "asset_id": "rgroup_next_feed_drop_staging_gate",
        "category": "governance",
        "path": "data/substituents/rgroup_next_feed_drop_staging_gate.json",
        "purpose": "Validation gate for filled next-feed-drop staging files before production promotion.",
    },
    {
        "asset_id": "rgroup_next_feed_drop_staging_gate_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_next_feed_drop_staging_gate.csv",
        "purpose": "Tabular validation rows for filled next-feed-drop staging files.",
    },
    {
        "asset_id": "rgroup_next_feed_drop_promotion",
        "category": "governance",
        "path": "data/substituents/rgroup_next_feed_drop_promotion.json",
        "purpose": "Promotion report for moving validated staged R-group feeds into governed feed files.",
    },
    {
        "asset_id": "rgroup_next_feed_drop_promotion_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_next_feed_drop_promotion.csv",
        "purpose": "Tabular promotion rows for validated staged R-group feed drops.",
    },
    {
        "asset_id": "rgroup_next_feed_drop_promotion_diff",
        "category": "governance",
        "path": "data/substituents/rgroup_next_feed_drop_promotion_diff.json",
        "purpose": "Pre-promotion staged-vs-production feed diff and operator review packet.",
    },
    {
        "asset_id": "rgroup_next_feed_drop_promotion_diff_csv",
        "category": "governance",
        "path": "data/substituents/rgroup_next_feed_drop_promotion_diff.csv",
        "purpose": "Tabular staged-vs-production feed promotion diff rows.",
    },
    {
        "asset_id": "rgroup_next_feed_drop_staging_dir",
        "category": "replacement_network",
        "path": "data/replacements/feed_drops/next_rgroup_feed_drop",
        "purpose": "Source-specific staged CSV templates and manifest for the next R-group feed drop.",
    },
    {
        "asset_id": "rgroup_mined_replacement_feed",
        "category": "replacement_network",
        "path": "data/replacements/rgroup_mined_replacement_feed.csv",
        "purpose": "Governed CSV feed for literature, analog-series, and patent-mined R-group replacements.",
    },
    {
        "asset_id": "vendor_overlay",
        "category": "route_vendor",
        "path": "data/vendor/reagent_availability_overlay.csv",
        "db_table": "substituent_vendor_overlay",
        "purpose": "Availability, price tier, lead-time, and route confidence overlay.",
    },
    {
        "asset_id": "synthesis_routes",
        "category": "route_vendor",
        "path": "data/vendor/synthesis_route_templates.yaml",
        "purpose": "Route-class templates used by availability scoring and batch grouping.",
    },
    {
        "asset_id": "scaffold_replacements",
        "category": "replacement_network",
        "path": "data/rules/scaffold_replacements.yaml",
        "db_table": "scaffold_replacement",
        "purpose": "Curated scaffold/ring replacement seeds.",
    },
    {
        "asset_id": "scaffold_calibration_set",
        "category": "model_context",
        "path": "data/rules/scaffold_calibration_set.yaml",
        "purpose": "Curated positive/negative cases for calibrating scaffold and ring operators.",
    },
    {
        "asset_id": "scaffold_rule_reviews",
        "category": "governance",
        "path": "data/rules/scaffold_rule_reviews.yaml",
        "db_table": "scaffold_rule_review_event",
        "purpose": "Human review overlays for scaffold/ring/linker replacement rules.",
    },
    {
        "asset_id": "data_drift_thresholds",
        "category": "data_automation",
        "path": "data/rules/data_drift_thresholds.yaml",
        "purpose": "Count and checksum drift thresholds for daily maintenance.",
    },
    {
        "asset_id": "source_acceptance_manifest",
        "category": "data_automation",
        "path": "data/rules/source_acceptance_manifest.yaml",
        "purpose": "Explicit acceptances for reviewed large data-count or checksum shifts.",
    },
    {
        "asset_id": "strategy_learning_policy",
        "category": "model_context",
        "path": "data/rules/strategy_learning_policy.yaml",
        "purpose": "Endpoint-specific policy for strategy priors, ranking adjustments, and time windows.",
    },
    {
        "asset_id": "ring_outcome_maturation_policy",
        "category": "model_context",
        "path": "data/profiles/ring_outcome_maturation_policy.yaml",
        "purpose": "Endpoint-specific maturity and approval gates for ring outcome scoring overlays.",
    },
    {
        "asset_id": "ring_outcome_overlay_activation",
        "category": "governance",
        "path": "data/profiles/calibrated/ring_outcome_overlay_activation.json",
        "purpose": "Activation gate and snapshot status for approved nonzero ring outcome scoring overlay contexts.",
    },
    {
        "asset_id": "ring_outcome_production_readiness",
        "category": "governance",
        "path": "data/projects/demo/ring_outcome_production_readiness.json",
        "purpose": "Production readiness gate for real ring outcome result intake and overlay activation.",
    },
    {
        "asset_id": "ring_outcome_production_readiness_csv",
        "category": "governance",
        "path": "data/projects/demo/ring_outcome_production_readiness.csv",
        "purpose": "Tabular ring outcome result intake readiness rows.",
    },
    {
        "asset_id": "ring_outcome_result_package",
        "category": "governance",
        "path": "data/projects/demo/ring_outcome_result_package.json",
        "purpose": "Production-named ring outcome result package manifest for real measured payload intake.",
    },
    {
        "asset_id": "ring_outcome_result_package_csv",
        "category": "governance",
        "path": "data/projects/demo/ring_outcome_result_package.csv",
        "purpose": "Tabular ring outcome result package rows for operator review.",
    },
    {
        "asset_id": "ring_outcome_production_result_csv",
        "category": "project_memory",
        "path": "data/projects/demo/ring_outcome_result_drops/production_ring_outcome_results_pending.csv",
        "purpose": "Production-named CSV intake target for real ring outcome assay/ADME/safety payloads.",
    },
    {
        "asset_id": "ring_outcome_result_package_import_gate",
        "category": "governance",
        "path": "data/projects/demo/ring_outcome_result_package_import_gate.json",
        "purpose": "Strict import gate for the production ring outcome result package.",
    },
    {
        "asset_id": "ring_outcome_result_package_review",
        "category": "governance",
        "path": "data/projects/demo/ring_outcome_result_package_review.json",
        "purpose": "Operator review packet for ring outcome package rows, payload gaps, and import readiness.",
    },
    {
        "asset_id": "ring_outcome_result_package_review_csv",
        "category": "governance",
        "path": "data/projects/demo/ring_outcome_result_package_review.csv",
        "purpose": "Tabular ring outcome package review rows.",
    },
    {
        "asset_id": "ring_outcome_holdout_report",
        "category": "governance",
        "path": "data/projects/demo/ring_outcome_holdout_report.json",
        "purpose": "Endpoint-level holdout readiness report for ring outcome overlay activation.",
    },
    {
        "asset_id": "ring_outcome_holdout_report_csv",
        "category": "governance",
        "path": "data/projects/demo/ring_outcome_holdout_report.csv",
        "purpose": "Tabular endpoint-level ring outcome holdout readiness rows.",
    },
    {
        "asset_id": "queue_analog_series_policy",
        "category": "model_context",
        "path": "data/rules/queue_analog_series_policy.yaml",
        "purpose": "Versioned policy used to translate analog-series priority deltas into next-generation score adjustments.",
    },
    {
        "asset_id": "target_context_profiles",
        "category": "model_context",
        "path": "data/rules/target_context_profiles.yaml",
        "purpose": "Multi-objective target-context profiles balancing potency, stability, permeability, and liability.",
    },
    {
        "asset_id": "closed_loop_acceptance_policy",
        "category": "project_memory",
        "path": "data/rules/closed_loop_acceptance.yaml",
        "purpose": "Acceptance thresholds for the closed-loop drill and feedback-driven generation checks.",
    },
    {
        "asset_id": "evidence_confidence_report",
        "category": "evidence",
        "path": "data/substituents/evidence_confidence_report.json",
        "purpose": "Endpoint-specific confidence calibration curves for public/project/scaffold evidence.",
    },
    {
        "asset_id": "evidence_residual_trend_chart",
        "category": "evidence",
        "path": "data/substituents/evidence_residual_trend_chart.json",
        "purpose": "Chart-friendly residual trend rows for evidence calibration governance.",
    },
    {
        "asset_id": "endpoint_family_residual_model",
        "category": "evidence",
        "path": "data/substituents/endpoint_family_residual_model.json",
        "purpose": "Endpoint-family residual model for source-specific evidence calibration.",
    },
    {
        "asset_id": "evidence_residual_tasks",
        "category": "evidence",
        "path": "data/substituents/evidence_residual_tasks.json",
        "purpose": "Residual-driven data-strengthening tasks for thin or miscalibrated evidence contexts.",
    },
    {
        "asset_id": "evidence_residual_task_registry",
        "category": "evidence",
        "path": "data/substituents/evidence_residual_task_registry.json",
        "purpose": "Lifecycle registry for residual data-strengthening tasks and closure history.",
    },
    {
        "asset_id": "residual_experiment_plan",
        "category": "project_memory",
        "path": "data/projects/demo/residual_experiment_plan.csv",
        "purpose": "Experiment-plan rows generated from evidence residual tasks for closed-loop calibration.",
    },
    {
        "asset_id": "residual_experiment_results_template",
        "category": "project_memory",
        "path": "data/projects/demo/residual_experiment_results_template.csv",
        "purpose": "Fillable result-import template for closing residual evidence calibration experiment plans.",
    },
    {
        "asset_id": "residual_result_import_report",
        "category": "project_memory",
        "path": "data/projects/demo/residual_result_import_report.json",
        "purpose": "Validation/import report for filled residual experiment results, including skipped blank-template rows and closed task counts.",
    },
    {
        "asset_id": "residual_result_intake_manifest",
        "category": "project_memory",
        "path": "data/projects/demo/residual_result_intake_manifest.json",
        "purpose": "Real-result intake checklist for residual experiment CSVs; prevents blank/status-only closure.",
    },
    {
        "asset_id": "multi_objective_calibration_report",
        "category": "model_context",
        "path": "data/projects/demo/multi_objective_calibration_report.json",
        "purpose": "Project-specific historical calibration report for multi-objective score weights.",
    },
    {
        "asset_id": "public_strategy_signal_report",
        "category": "evidence",
        "path": "data/substituents/public_strategy_signal_report.json",
        "purpose": "Public ChEMBL/MMP/ring evidence mapped into candidate strategy signals.",
    },
    {
        "asset_id": "project_evidence_pack",
        "category": "project_memory",
        "path": "data/projects/demo/project_evidence_pack.json",
        "purpose": "Project-focused evidence pack combining outcomes, public SAR priors, residual gaps, analog series, and scaffold review readiness.",
    },
    {
        "asset_id": "project_evidence_pack_summary",
        "category": "project_memory",
        "path": "data/projects/demo/project_evidence_pack_summary.csv",
        "purpose": "Tabular summary of project evidence contexts and residual gaps for review/export.",
    },
    {
        "asset_id": "project_evidence_expansion_plan",
        "category": "project_memory",
        "path": "data/projects/demo/project_evidence_expansion_plan.json",
        "purpose": "Project-scoped evidence expansion tasks for assay/outcome, MMP/SAR, scaffold, and ring evidence only.",
    },
    {
        "asset_id": "project_evidence_expansion_plan_csv",
        "category": "project_memory",
        "path": "data/projects/demo/project_evidence_expansion_plan.csv",
        "purpose": "Tabular project evidence expansion task list excluding procurement/vendor work.",
    },
    {
        "asset_id": "project_evidence_execution_report",
        "category": "project_memory",
        "path": "data/projects/demo/project_evidence_execution_report.json",
        "purpose": "Execution report for project evidence expansion tasks using existing local evidence only.",
    },
    {
        "asset_id": "public_sar_validation_report",
        "category": "project_memory",
        "path": "data/projects/demo/public_sar_validation_report.json",
        "purpose": "Public SAR validation map for evidence-expansion tasks against active project contexts.",
    },
    {
        "asset_id": "endpoint_family_residual_adjustment_reviews",
        "category": "governance",
        "path": "data/profiles/calibrated/endpoint_family_residual_adjustment_reviews.csv",
        "purpose": "Reviewer sign-off rows for endpoint-family residual score-profile adjustments.",
    },
    {
        "asset_id": "project_evidence_gap_adjustment_candidates",
        "category": "governance",
        "path": "data/profiles/calibrated/project_evidence_gap_adjustment_candidates.csv",
        "purpose": "Project evidence-gap score-profile adjustment candidates requiring explicit manual review decisions.",
    },
    {
        "asset_id": "endpoint_family_residual_adjustment_apply_report",
        "category": "model_context",
        "path": "data/profiles/calibrated/endpoint_family_residual_adjustment_apply_report.json",
        "purpose": "Application report for reviewed endpoint-family residual profile adjustments.",
    },
    {
        "asset_id": "profile_promotion_registry",
        "category": "governance",
        "path": "data/profiles/profile_promotion_registry.json",
        "purpose": "Promotion registry linking profile/policy activation requests to evidence pack, promotion gate, release smoke, and iteration comparison snapshots.",
    },
    {
        "asset_id": "profile_ab_replay_report",
        "category": "project_memory",
        "path": "data/projects/demo/profile_ab_replay_report.json",
        "purpose": "A/B replay comparing candidate ranking under active/base and candidate scoring profiles.",
    },
    {
        "asset_id": "profile_ab_replay_report_csv",
        "category": "project_memory",
        "path": "data/projects/demo/profile_ab_replay_report.csv",
        "purpose": "Tabular candidate-level profile A/B replay score and rank deltas.",
    },
    {
        "asset_id": "profile_ab_replay_matrix",
        "category": "project_memory",
        "path": "data/projects/demo/profile_ab_replay_matrix.json",
        "purpose": "Multi-scenario profile A/B replay matrix across directions and target contexts.",
    },
    {
        "asset_id": "profile_ab_replay_matrix_csv",
        "category": "project_memory",
        "path": "data/projects/demo/profile_ab_replay_matrix.csv",
        "purpose": "Tabular multi-scenario profile A/B replay matrix summary.",
    },
    {
        "asset_id": "profile_ab_material_change_review",
        "category": "governance",
        "path": "data/projects/demo/profile_ab_material_change_review.json",
        "purpose": "Candidate-level acceptance record for material profile A/B replay changes.",
    },
    {
        "asset_id": "profile_ab_material_change_review_csv",
        "category": "governance",
        "path": "data/projects/demo/profile_ab_material_change_review.csv",
        "purpose": "Tabular candidate-level material profile A/B diff audit.",
    },
    {
        "asset_id": "candidate_evidence_priority_report",
        "category": "project_memory",
        "path": "data/projects/demo/candidate_evidence_priority_report.json",
        "purpose": "Candidate-level priority view merging public SAR links, material profile A/B diffs, queue state, and analog-series sufficiency.",
    },
    {
        "asset_id": "candidate_evidence_priority_report_csv",
        "category": "project_memory",
        "path": "data/projects/demo/candidate_evidence_priority_report.csv",
        "purpose": "Tabular candidate evidence priority view for review/export.",
    },
    {
        "asset_id": "public_sar_contradiction_triage",
        "category": "project_memory",
        "path": "data/projects/demo/public_sar_contradiction_triage.json",
        "purpose": "Contradiction-driven public SAR triage rows linked to candidates, analog series, or reference-only watch status.",
    },
    {
        "asset_id": "public_sar_contradiction_triage_csv",
        "category": "project_memory",
        "path": "data/projects/demo/public_sar_contradiction_triage.csv",
        "purpose": "Tabular contradiction-driven public SAR triage worklist.",
    },
    {
        "asset_id": "public_sar_contradiction_resolution_batch",
        "category": "project_memory",
        "path": "data/projects/demo/public_sar_contradiction_resolution_batch.json",
        "purpose": "First-pass high-priority public SAR contradiction resolution and measurement-gating batch.",
    },
    {
        "asset_id": "public_sar_contradiction_resolution_batch_csv",
        "category": "project_memory",
        "path": "data/projects/demo/public_sar_contradiction_resolution_batch.csv",
        "purpose": "Tabular SAR contradiction resolution batch decisions.",
    },
    {
        "asset_id": "public_sar_contradiction_watchlist",
        "category": "project_memory",
        "path": "data/projects/demo/public_sar_contradiction_watchlist.json",
        "purpose": "Actionable watchlist for unresolved SAR contradictions with candidate or analog-series overlap.",
    },
    {
        "asset_id": "public_sar_contradiction_watchlist_csv",
        "category": "project_memory",
        "path": "data/projects/demo/public_sar_contradiction_watchlist.csv",
        "purpose": "Tabular actionable SAR contradiction watchlist.",
    },
    {
        "asset_id": "evidence_value_report",
        "category": "project_memory",
        "path": "data/projects/demo/evidence_value_report.json",
        "purpose": "Candidate-level evidence value scoring across SAR links, contradictions, sufficiency gaps, material A/B changes, and rollback impact.",
    },
    {
        "asset_id": "evidence_value_report_csv",
        "category": "project_memory",
        "path": "data/projects/demo/evidence_value_report.csv",
        "purpose": "Tabular candidate evidence value scoring report.",
    },
    {
        "asset_id": "measurement_feedback_plan",
        "category": "project_memory",
        "path": "data/projects/demo/measurement_feedback_plan.json",
        "purpose": "Measurement feedback plan for high-value candidates and analog-series evidence gaps.",
    },
    {
        "asset_id": "measurement_feedback_plan_csv",
        "category": "project_memory",
        "path": "data/projects/demo/measurement_feedback_plan.csv",
        "purpose": "Tabular measurement feedback plan for medchem evidence closure.",
    },
    {
        "asset_id": "measurement_feedback_results_template",
        "category": "project_memory",
        "path": "data/projects/demo/measurement_feedback_results_template.csv",
        "purpose": "Fillable template for importing real measured feedback rows from the measurement feedback plan.",
    },
    {
        "asset_id": "measurement_feedback_result_import_report",
        "category": "project_memory",
        "path": "data/projects/demo/measurement_feedback_result_import_report.json",
        "purpose": "Validation/import report for explicitly supplied local measurement evidence rows; blank templates remain open.",
    },
    {
        "asset_id": "measurement_feedback_result_import_report_csv",
        "category": "project_memory",
        "path": "data/projects/demo/measurement_feedback_result_import_report.csv",
        "purpose": "Tabular import trace for measurement feedback rows used by evidence-value calibration.",
    },
    {
        "asset_id": "measurement_feedback_gap_closure",
        "category": "project_memory",
        "path": "data/projects/demo/measurement_feedback_gap_closure.json",
        "purpose": "Manual closure tasks for unmatched measurement feedback plan rows without cross-endpoint auto-mapping.",
    },
    {
        "asset_id": "measurement_feedback_gap_closure_csv",
        "category": "project_memory",
        "path": "data/projects/demo/measurement_feedback_gap_closure.csv",
        "purpose": "Tabular measurement feedback gap closure worklist.",
    },
    {
        "asset_id": "measurement_gap_exact_result_intake",
        "category": "project_memory",
        "path": "data/projects/demo/measurement_gap_exact_result_intake.json",
        "purpose": "Exact-endpoint result intake manifest for measurement gap closure rows.",
    },
    {
        "asset_id": "measurement_gap_exact_result_intake_csv",
        "category": "project_memory",
        "path": "data/projects/demo/measurement_gap_exact_result_intake.csv",
        "purpose": "Tabular exact-endpoint intake manifest for measurement gap rows.",
    },
    {
        "asset_id": "measurement_gap_exact_results_template",
        "category": "project_memory",
        "path": "data/projects/demo/measurement_gap_exact_results_template.csv",
        "purpose": "Blank exact-endpoint result template for local governance; no cross-endpoint remap is automatic.",
    },
    {
        "asset_id": "measurement_gap_endpoint_governance",
        "category": "project_memory",
        "path": "data/projects/demo/measurement_gap_endpoint_governance.json",
        "purpose": "Non-experimental strict endpoint governance report for measurement gaps.",
    },
    {
        "asset_id": "measurement_gap_endpoint_governance_csv",
        "category": "project_memory",
        "path": "data/projects/demo/measurement_gap_endpoint_governance.csv",
        "purpose": "Tabular strict endpoint governance rows for measurement gaps.",
    },
    {
        "asset_id": "site_class_policy_pack",
        "category": "project_memory",
        "path": "data/projects/demo/site_class_policy_pack.json",
        "purpose": "Candidate-facing non-experimental guidance for methoxy, ester, basic amine, and terminal-tail edits.",
    },
    {
        "asset_id": "site_class_policy_pack_csv",
        "category": "project_memory",
        "path": "data/projects/demo/site_class_policy_pack.csv",
        "purpose": "Tabular site-class policy guidance with review status, scenarios, and version changelog.",
    },
    {
        "asset_id": "site_detection_regression_report",
        "category": "project_memory",
        "path": "data/projects/demo/site_detection_regression_report.json",
        "purpose": "Local regression suite for methoxy, ester, basic amine, terminal-tail, and false-positive site detection guards.",
    },
    {
        "asset_id": "site_detection_regression_report_csv",
        "category": "project_memory",
        "path": "data/projects/demo/site_detection_regression_report.csv",
        "purpose": "Tabular site detection regression cases and outcomes.",
    },
    {
        "asset_id": "site_detection_regression_report_md",
        "category": "project_memory",
        "path": "docs/site_detection_regression_report.md",
        "purpose": "Markdown site detection regression handoff.",
    },
    {
        "asset_id": "site_detection_regression_coverage_csv",
        "category": "project_memory",
        "path": "data/projects/demo/site_detection_regression_coverage.csv",
        "purpose": "Coverage gate requiring positive, negative, and boundary examples per new site class.",
    },
    {
        "asset_id": "site_detection_project_sample_pack_csv",
        "category": "project_memory",
        "path": "data/projects/demo/site_detection_project_sample_pack.csv",
        "purpose": "Observed project candidate sample pack for local site-detection grounding.",
    },
    {
        "asset_id": "site_detection_confidence",
        "category": "project_memory",
        "path": "data/projects/demo/site_detection_confidence.json",
        "purpose": "Explainable parser confidence rows for rule hits, boundary guards, and false-positive tiers.",
    },
    {
        "asset_id": "site_detection_confidence_csv",
        "category": "project_memory",
        "path": "data/projects/demo/site_detection_confidence.csv",
        "purpose": "Tabular site detection confidence rows for native review.",
    },
    {
        "asset_id": "site_detection_confidence_md",
        "category": "project_memory",
        "path": "docs/site_detection_confidence.md",
        "purpose": "Markdown site detection confidence handoff.",
    },
    {
        "asset_id": "evidence_value_calibration_report",
        "category": "model_context",
        "path": "data/projects/demo/evidence_value_calibration_report.json",
        "purpose": "Calibration report comparing heuristic evidence-value scores to local normalized measurement evidence.",
    },
    {
        "asset_id": "evidence_value_calibration_report_csv",
        "category": "model_context",
        "path": "data/projects/demo/evidence_value_calibration_report.csv",
        "purpose": "Tabular evidence-value calibration rows and score errors.",
    },
    {
        "asset_id": "evidence_value_policy_proposal",
        "category": "model_context",
        "path": "data/projects/demo/evidence_value_policy_proposal.json",
        "purpose": "Versioned evidence-value weight proposal generated from calibration and held for manual approval before activation.",
    },
    {
        "asset_id": "evidence_value_policy_proposal_csv",
        "category": "model_context",
        "path": "data/projects/demo/evidence_value_policy_proposal.csv",
        "purpose": "Tabular evidence-value policy weight changes for approval review.",
    },
    {
        "asset_id": "evidence_value_policy_replay",
        "category": "model_context",
        "path": "data/projects/demo/evidence_value_policy_replay.json",
        "purpose": "Pre-activation replay comparing current and proposed evidence-value policy rankings.",
    },
    {
        "asset_id": "evidence_value_policy_replay_csv",
        "category": "model_context",
        "path": "data/projects/demo/evidence_value_policy_replay.csv",
        "purpose": "Tabular pre-activation evidence-value policy replay deltas.",
    },
    {
        "asset_id": "evidence_value_policy_activation",
        "category": "model_context",
        "path": "data/projects/demo/evidence_value_policy_activation.json",
        "purpose": "Auditable manual activation record for an approved evidence-value policy proposal.",
    },
    {
        "asset_id": "evidence_value_policy_activation_csv",
        "category": "model_context",
        "path": "data/projects/demo/evidence_value_policy_activation.csv",
        "purpose": "Tabular activation summary for evidence-value policy governance.",
    },
    {
        "asset_id": "evidence_value_policy_active",
        "category": "model_context",
        "path": "data/projects/demo/evidence_value_policy_active.json",
        "purpose": "Current active evidence-value scoring policy snapshot used by Project Memory scoring.",
    },
    {
        "asset_id": "evidence_value_policy_active_compare",
        "category": "model_context",
        "path": "data/projects/demo/evidence_value_policy_active_compare.json",
        "purpose": "Active-vs-baseline evidence-value policy comparison with profile impact flags.",
    },
    {
        "asset_id": "evidence_value_policy_active_compare_csv",
        "category": "model_context",
        "path": "data/projects/demo/evidence_value_policy_active_compare.csv",
        "purpose": "Tabular active-vs-baseline evidence-value policy comparison.",
    },
    {
        "asset_id": "profile_impact_review_queue",
        "category": "project_memory",
        "path": "data/projects/demo/profile_impact_review_queue.json",
        "purpose": "Non-experimental review queue for profile-impact rows raised by active policy comparison.",
    },
    {
        "asset_id": "profile_impact_review_queue_csv",
        "category": "project_memory",
        "path": "data/projects/demo/profile_impact_review_queue.csv",
        "purpose": "Tabular profile-impact review queue.",
    },
    {
        "asset_id": "project_memory_review_queue",
        "category": "project_memory",
        "path": "data/projects/demo/project_memory_review_queue.json",
        "purpose": "Consolidated Project Memory review queue for policy, measurement gaps, calibration drivers, and SAR watch items.",
    },
    {
        "asset_id": "project_memory_review_queue_csv",
        "category": "project_memory",
        "path": "data/projects/demo/project_memory_review_queue.csv",
        "purpose": "Tabular Project Memory review queue.",
    },
    {
        "asset_id": "project_memory_review_dashboard",
        "category": "project_memory",
        "path": "data/projects/demo/project_memory_review_dashboard.json",
        "purpose": "Dashboard summary of Project Memory review lanes, assignee load, and attention rows.",
    },
    {
        "asset_id": "project_memory_review_dashboard_csv",
        "category": "project_memory",
        "path": "data/projects/demo/project_memory_review_dashboard.csv",
        "purpose": "Tabular Project Memory review-lane dashboard.",
    },
    {
        "asset_id": "promotion_readiness_packet",
        "category": "project_memory",
        "path": "data/projects/demo/promotion_readiness_packet.json",
        "purpose": "Non-experimental promotion readiness packet combining policy compare, profile impact, endpoint governance, and Project Memory review state.",
    },
    {
        "asset_id": "promotion_readiness_packet_csv",
        "category": "project_memory",
        "path": "data/projects/demo/promotion_readiness_packet.csv",
        "purpose": "Tabular summary rows for the promotion readiness packet.",
    },
    {
        "asset_id": "assay_event_triage_report",
        "category": "project_memory",
        "path": "data/projects/demo/assay_event_triage_report.json",
        "purpose": "Triage register for low-confidence and retest assay events in project memory.",
    },
    {
        "asset_id": "assay_followup_result_template",
        "category": "project_memory",
        "path": "data/projects/demo/assay_followup_results_template.csv",
        "purpose": "Blank follow-up result template generated from assay-event triage rows.",
    },
    {
        "asset_id": "assay_followup_result_import_report",
        "category": "project_memory",
        "path": "data/projects/demo/assay_followup_result_import_report.json",
        "purpose": "Validation/import report for real follow-up assay result rows.",
    },
    {
        "asset_id": "profile_promotion_freeze_manifest",
        "category": "governance",
        "path": "data/projects/demo/profile_promotion_freeze_manifest.json",
        "purpose": "Latest profile-promotion freeze manifest tying gate, evidence, A/B replay, and data-foundation snapshots together.",
    },
    {
        "asset_id": "profile_promotion_freeze_approvals",
        "category": "governance",
        "path": "data/projects/demo/profile_promotion_freeze_approvals.json",
        "purpose": "Approval, rejection, and rollback history for profile-promotion freeze packages.",
    },
    {
        "asset_id": "profile_promotion_release_tags",
        "category": "governance",
        "path": "data/projects/demo/profile_promotion_release_tags.json",
        "purpose": "Auditable release tags created from approved profile-promotion freeze packages.",
    },
    {
        "asset_id": "profile_promotion_freeze_rollback_drill",
        "category": "governance",
        "path": "data/projects/demo/profile_promotion_freeze_rollback_drill.json",
        "purpose": "Dry-run rollback drill proving active freeze, release tag, gate snapshot, and rollback action traceability.",
    },
    {
        "asset_id": "profile_promotion_rollback_replay",
        "category": "governance",
        "path": "data/projects/demo/profile_promotion_rollback_replay.json",
        "purpose": "Dry-run profile rollback replay showing candidate rank, score, and recommendation impacts.",
    },
    {
        "asset_id": "profile_promotion_rollback_replay_csv",
        "category": "governance",
        "path": "data/projects/demo/profile_promotion_rollback_replay.csv",
        "purpose": "Tabular profile rollback replay candidate-level diff.",
    },
    {
        "asset_id": "profile_rollback_history",
        "category": "governance",
        "path": "data/projects/demo/profile_rollback_history.json",
        "purpose": "Multi-freeze and multi-iteration rollback history comparing candidate rank and score impacts over time.",
    },
    {
        "asset_id": "profile_rollback_history_csv",
        "category": "governance",
        "path": "data/projects/demo/profile_rollback_history.csv",
        "purpose": "Tabular snapshot-level profile rollback history.",
    },
    {
        "asset_id": "profile_rollback_candidate_history_csv",
        "category": "governance",
        "path": "data/projects/demo/profile_rollback_candidate_history.csv",
        "purpose": "Tabular candidate-level rollback history across current, iteration, and freeze snapshots.",
    },
    {
        "asset_id": "profile_rollback_snapshot_compare",
        "category": "governance",
        "path": "data/projects/demo/profile_rollback_snapshot_compare.json",
        "purpose": "Pairwise profile rollback snapshot drift comparison for candidate rank and rollback action changes.",
    },
    {
        "asset_id": "profile_rollback_snapshot_compare_csv",
        "category": "governance",
        "path": "data/projects/demo/profile_rollback_snapshot_compare.csv",
        "purpose": "Tabular candidate-level profile rollback snapshot drift comparison.",
    },
    {
        "asset_id": "project_memory_refresh_report",
        "category": "project_memory",
        "path": "data/projects/demo/project_memory_refresh_report.json",
        "purpose": "One-command project memory refresh report spanning evidence, SAR, profile replay, gates, and release smoke.",
    },
    {
        "asset_id": "scaffold_review_workspace_report",
        "category": "governance",
        "path": "data/substituents/scaffold_review_workspace_report.json",
        "purpose": "Scaffold/ring review workspace with examples, rule status, and evidence summaries.",
    },
    {
        "asset_id": "scaffold_calibration_audit_report",
        "category": "governance",
        "path": "data/substituents/scaffold_calibration_audit_report.json",
        "purpose": "Before/after audit report for scaffold calibration changes and workspace alignment.",
    },
    {
        "asset_id": "scaffold_rule_review_drafts",
        "category": "governance",
        "path": "data/substituents/scaffold_rule_review_drafts.csv",
        "purpose": "Manual-review draft rows generated from scaffold calibration audit suggestions before rule changes are applied.",
    },
    {
        "asset_id": "analog_series_report",
        "category": "project_memory",
        "path": "data/projects/demo/analog_series_report.json",
        "purpose": "Analog-series summaries linking novelty batches, decisions, and observed outcomes.",
    },
    {
        "asset_id": "quality_warning_policy",
        "category": "governance",
        "path": "data/rules/quality_warning_policy.yaml",
        "purpose": "Warning classification policy for accepted vs must-fix quality warnings.",
    },
    {
        "asset_id": "medchem_decision_packets",
        "category": "project_memory",
        "path": "data/projects/demo",
        "purpose": "Candidate make/defer/reject decision packets for medchem review.",
    },
    {
        "asset_id": "next_design_queue",
        "category": "project_memory",
        "path": "data/projects/closed_loop",
        "purpose": "Priority-delta-derived next-batch design queues for closed-loop review.",
    },
    {
        "asset_id": "next_design_queue_decision_templates",
        "category": "project_memory",
        "path": "data/projects/closed_loop",
        "purpose": "Accepted/deferred/retired next-design queue decision templates and applied review outputs.",
    },
    {
        "asset_id": "next_design_queue_decision_quality",
        "category": "project_memory",
        "path": "data/projects/closed_loop/next_design_queue_decision_quality.json",
        "purpose": "Observed outcome quality report for accepted/deferred/retired queue decisions.",
    },
    {
        "asset_id": "queue_analog_series_delta",
        "category": "project_memory",
        "path": "data/projects/closed_loop/queue_analog_series_delta.json",
        "purpose": "Analog-series level priority deltas used to adjust the next generation strategy.",
    },
    {
        "asset_id": "closed_loop_drill_report",
        "category": "project_memory",
        "path": "data/projects/closed_loop_drill/closed_loop_drill_report.json",
        "purpose": "End-to-end closed-loop drill output covering generation, packet review, feedback, queue delta, and next generation.",
    },
    {
        "asset_id": "closed_loop_drill_acceptance",
        "category": "project_memory",
        "path": "data/projects/closed_loop_drill/closed_loop_drill_acceptance.json",
        "purpose": "Acceptance check output and golden-style metric snapshot for the closed-loop drill.",
    },
    {
        "asset_id": "project_closed_loop_dashboard",
        "category": "project_memory",
        "path": "data/projects/demo/project_closed_loop_dashboard.json",
        "purpose": "Project-level closed-loop dashboard combining feedback, experiments, queue decisions, residual tasks, and active policies.",
    },
    {
        "asset_id": "closed_loop_replay_report",
        "category": "project_memory",
        "path": "data/projects/demo/closed_loop_replay_report.json",
        "purpose": "Holdout and replay validation report for multi-objective scoring and queue policy behavior.",
    },
    {
        "asset_id": "closed_loop_promotion_gate",
        "category": "project_memory",
        "path": "data/projects/demo/closed_loop_promotion_gate.json",
        "purpose": "Promotion gate combining replay, acceptance, residual-task, and scaffold-review readiness checks.",
    },
    {
        "asset_id": "iteration_comparison_report",
        "category": "project_memory",
        "path": "data/projects/demo/iteration_comparison_report.json",
        "purpose": "Comparison report for consecutive next-design iteration manifests and metric deltas.",
    },
    {
        "asset_id": "next_design_iteration_packages",
        "category": "project_memory",
        "path": "data/projects/iterations",
        "purpose": "Versioned next-design iteration packages with manifests and report snapshots for reproducible review.",
    },
    {
        "asset_id": "scoring_profiles",
        "category": "model_context",
        "path": "data/profiles",
        "purpose": "Project scoring profiles and calibrated endpoint profiles.",
    },
    {
        "asset_id": "localmedchem_sqlite",
        "category": "warehouse",
        "path": "data/localmedchem.sqlite",
        "purpose": "Queryable local warehouse for governed and project data.",
    },
    {
        "asset_id": "desktop_launchers",
        "category": "deployment",
        "path": "dist",
        "purpose": "Non-developer launchers for the interactive Streamlit app.",
    },
    {
        "asset_id": "data_automation_templates",
        "category": "data_automation",
        "path": "dist/tasks",
        "purpose": "Windows Task Scheduler templates for DB-only ring import and data-foundation refresh.",
    },
    {
        "asset_id": "weekly_release_diff_summary",
        "category": "release",
        "path": "data/releases/weekly_release_diff_summary.json",
        "purpose": "Weekly release-manifest and key data-count diff summary.",
    },
    {
        "asset_id": "production_dashboard_snapshot",
        "category": "release",
        "path": "data/releases/production_dashboard_snapshot.json",
        "purpose": "Compact production gate dashboard snapshot for native and release views.",
    },
    {
        "asset_id": "production_dashboard_snapshot_csv",
        "category": "release",
        "path": "data/releases/production_dashboard_snapshot.csv",
        "purpose": "Tabular production gate dashboard rows.",
    },
    {
        "asset_id": "production_dashboard_trend_history",
        "category": "release",
        "path": "data/releases/production_dashboard_trend_history.json",
        "purpose": "Append-only release cockpit trend history for feed diff, ring package review, smoke, and data-foundation counts.",
    },
    {
        "asset_id": "production_dashboard_trend_history_csv",
        "category": "release",
        "path": "data/releases/production_dashboard_trend_history.csv",
        "purpose": "Tabular production dashboard trend history.",
    },
    {
        "asset_id": "native_ui_quality_report",
        "category": "deployment",
        "path": "data/releases/native_ui_quality_report.json",
        "purpose": "Native UI high-DPI, typography, molecule-preview, and browser-free quality smoke report.",
    },
    {
        "asset_id": "local_db_health_report",
        "category": "deployment",
        "path": "data/releases/local_db_health_report.json",
        "purpose": "Local SQLite availability, integrity, row-count, and index health report for large local DB workflows.",
    },
    {
        "asset_id": "local_db_health_report_csv",
        "category": "deployment",
        "path": "data/releases/local_db_health_report.csv",
        "purpose": "Tabular expected-table availability and row-count details from the local DB health report.",
    },
    {
        "asset_id": "local_db_maintenance_report",
        "category": "deployment",
        "path": "data/releases/local_db_maintenance_report.json",
        "purpose": "Local SQLite maintenance, ring-cache warm status, recommended-index coverage, and query latency-budget report.",
    },
    {
        "asset_id": "local_db_maintenance_report_csv",
        "category": "deployment",
        "path": "data/releases/local_db_maintenance_report.csv",
        "purpose": "Tabular rows for DB health, cache warm status, recommended indexes, and latency budgets.",
    },
    {
        "asset_id": "local_db_maintenance_release_gate",
        "category": "deployment",
        "path": "data/releases/local_db_maintenance_release_gate.json",
        "purpose": "Release-stop versus watch classification for local DB maintenance rows.",
    },
    {
        "asset_id": "local_db_maintenance_release_gate_csv",
        "category": "deployment",
        "path": "data/releases/local_db_maintenance_release_gate.csv",
        "purpose": "Tabular local DB release-stop/watch classification rows.",
    },
    {
        "asset_id": "local_db_maintenance_release_gate_md",
        "category": "deployment",
        "path": "docs/local_db_maintenance_release_gate.md",
        "purpose": "Markdown local DB release gate handoff.",
    },
    {
        "asset_id": "local_db_maintenance_trend_history",
        "category": "deployment",
        "path": "data/releases/local_db_maintenance_trend_history.json",
        "purpose": "Trend history for local SQLite latency budgets, cache warm status, and explicit maintenance runs.",
    },
    {
        "asset_id": "local_db_maintenance_trend_history_csv",
        "category": "deployment",
        "path": "data/releases/local_db_maintenance_trend_history.csv",
        "purpose": "Tabular DB maintenance trend rows for local performance review.",
    },
    {
        "asset_id": "native_ui_regression_snapshot",
        "category": "deployment",
        "path": "data/releases/native_ui_regression_snapshot.json",
        "purpose": "Native UI regression snapshot covering UI smoke, package manifest, candidate schema, and local DB health.",
    },
    {
        "asset_id": "native_ui_regression_snapshot_md",
        "category": "deployment",
        "path": "docs/native_ui_regression_snapshot.md",
        "purpose": "Markdown handoff for native UI regression checks.",
    },
    {
        "asset_id": "candidate_visual_compare",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_visual_compare.json",
        "purpose": "Candidate visual comparison packet with aligned molecule images, highlighted non-scaffold atoms, property deltas, MMP/SAR examples, and evidence thumbnails.",
    },
    {
        "asset_id": "candidate_visual_compare_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_visual_compare.csv",
        "purpose": "Tabular candidate visual comparison rows.",
    },
    {
        "asset_id": "candidate_visual_compare_md",
        "category": "project_candidate_review",
        "path": "docs/candidate_visual_compare.md",
        "purpose": "Markdown visual compare handoff with embedded local grid image.",
    },
    {
        "asset_id": "candidate_structure_interpretation",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_structure_interpretation.json",
        "purpose": "Candidate structure interpretation report linking 2D previews to score-component locators.",
    },
    {
        "asset_id": "candidate_structure_interpretation_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_structure_interpretation.csv",
        "purpose": "Tabular candidate structure interpretation rows.",
    },
    {
        "asset_id": "candidate_structure_interpretation_md",
        "category": "project_candidate_review",
        "path": "docs/candidate_structure_interpretation.md",
        "purpose": "Markdown candidate structure interpretation handoff.",
    },
    {
        "asset_id": "candidate_review_packet",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_review_packet.json",
        "purpose": "Non-experimental candidate review packet grouped by site class, evidence strength, and risk/governance buckets.",
    },
    {
        "asset_id": "candidate_review_packet_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_review_packet.csv",
        "purpose": "Tabular candidate review packet rows.",
    },
    {
        "asset_id": "candidate_review_packet_md",
        "category": "project_candidate_review",
        "path": "docs/candidate_review_packet.md",
        "purpose": "Markdown review packet summary for local human review.",
    },
    {
        "asset_id": "candidate_review_board",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_review_board.json",
        "purpose": "Local candidate review board with filters, focused rows, batch review status, and reviewer ledger merge.",
    },
    {
        "asset_id": "candidate_review_board_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_review_board.csv",
        "purpose": "Tabular local candidate review board rows.",
    },
    {
        "asset_id": "candidate_review_board_focused_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_review_board_focused.csv",
        "purpose": "Focused local review rows requiring attention before candidate priority changes.",
    },
    {
        "asset_id": "candidate_review_board_md",
        "category": "project_candidate_review",
        "path": "docs/candidate_review_board.md",
        "purpose": "Markdown candidate review board handoff.",
    },
    {
        "asset_id": "candidate_drilldown_packet",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_drilldown_packet.json",
        "purpose": "Candidate drill-down packet linking image, evidence depth, review packet, review board, and governance diff evidence.",
    },
    {
        "asset_id": "candidate_drilldown_packet_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_drilldown_packet.csv",
        "purpose": "Tabular candidate drill-down evidence rows.",
    },
    {
        "asset_id": "candidate_drilldown_packet_md",
        "category": "project_candidate_review",
        "path": "docs/candidate_drilldown_packet.md",
        "purpose": "Markdown candidate drill-down handoff.",
    },
    {
        "asset_id": "local_governance_diff",
        "category": "project_governance",
        "path": "data/projects/demo/local_governance_diff_report.json",
        "purpose": "Local candidate/scoring/profile/policy governance diff snapshot.",
    },
    {
        "asset_id": "local_governance_diff_csv",
        "category": "project_governance",
        "path": "data/projects/demo/local_governance_diff_report.csv",
        "purpose": "Tabular candidate movement rows for the local governance diff.",
    },
    {
        "asset_id": "local_governance_diff_md",
        "category": "project_governance",
        "path": "docs/local_governance_diff_report.md",
        "purpose": "Markdown governance diff handoff with candidate movement and policy fingerprints.",
    },
    {
        "asset_id": "named_governance_baseline_registry",
        "category": "project_governance",
        "path": "data/projects/demo/governance_baselines/baseline_registry.json",
        "purpose": "Named local governance baselines for scoring, profile, and policy diff workflows.",
    },
    {
        "asset_id": "candidate_baseline_registry",
        "category": "project_governance",
        "path": "data/projects/demo/candidate_baseline_registry.json",
        "purpose": "Named candidate-set baseline registry for local priority movement review.",
    },
    {
        "asset_id": "candidate_baseline_registry_csv",
        "category": "project_governance",
        "path": "data/projects/demo/candidate_baseline_registry.csv",
        "purpose": "Tabular named candidate-set baseline registry.",
    },
    {
        "asset_id": "candidate_baseline_compare",
        "category": "project_governance",
        "path": "data/projects/demo/candidate_baseline_compare.json",
        "purpose": "Named candidate-set baseline comparison report.",
    },
    {
        "asset_id": "candidate_baseline_compare_csv",
        "category": "project_governance",
        "path": "data/projects/demo/candidate_baseline_compare.csv",
        "purpose": "Tabular candidate baseline comparison rows.",
    },
    {
        "asset_id": "candidate_baseline_compare_md",
        "category": "project_governance",
        "path": "docs/candidate_baseline_compare.md",
        "purpose": "Markdown candidate baseline comparison handoff.",
    },
    {
        "asset_id": "candidate_review_analytics",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_review_analytics.json",
        "purpose": "Local review-board analytics for backlog, site-class coverage, risk buckets, and reviewer workload.",
    },
    {
        "asset_id": "candidate_review_analytics_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_review_analytics.csv",
        "purpose": "Tabular local candidate review-board analytics rows.",
    },
    {
        "asset_id": "candidate_review_analytics_md",
        "category": "project_candidate_review",
        "path": "docs/candidate_review_analytics.md",
        "purpose": "Markdown local review-board analytics handoff.",
    },
    {
        "asset_id": "candidate_decision_packet",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_decision_packet.json",
        "purpose": "Local accept/defer/reject/watch/needs-measurement candidate decision packet.",
    },
    {
        "asset_id": "candidate_decision_packet_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_decision_packet.csv",
        "purpose": "Tabular local candidate decision packet rows.",
    },
    {
        "asset_id": "candidate_decision_export_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_decision_export.csv",
        "purpose": "Decision-support export explicitly separated from procurement and real feedback automation.",
    },
    {
        "asset_id": "candidate_decision_packet_md",
        "category": "project_candidate_review",
        "path": "docs/candidate_decision_packet.md",
        "purpose": "Markdown local candidate decision handoff.",
    },
    {
        "asset_id": "candidate_evidence_drawer",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_evidence_drawer.json",
        "purpose": "Native candidate evidence drawer rows linking structure, evidence, review, baseline, and decision sections.",
    },
    {
        "asset_id": "candidate_evidence_drawer_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_evidence_drawer.csv",
        "purpose": "Tabular native evidence drawer rows.",
    },
    {
        "asset_id": "candidate_evidence_drawer_md",
        "category": "project_candidate_review",
        "path": "docs/candidate_evidence_drawer.md",
        "purpose": "Markdown candidate evidence drawer handoff.",
    },
    {
        "asset_id": "candidate_explanation_panel",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_explanation_panel.json",
        "purpose": "Single-candidate explanation panel linking score, evidence, baseline movement, decision QA, and remediation tasks.",
    },
    {
        "asset_id": "candidate_explanation_panel_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_explanation_panel.csv",
        "purpose": "Tabular candidate explanation panel rows.",
    },
    {
        "asset_id": "candidate_explanation_panel_md",
        "category": "project_candidate_review",
        "path": "docs/candidate_explanation_panel.md",
        "purpose": "Markdown candidate explanation panel handoff.",
    },
    {
        "asset_id": "candidate_explanation_compare",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_explanation_compare.json",
        "purpose": "Side-by-side local explanation comparison for two candidates.",
    },
    {
        "asset_id": "candidate_explanation_compare_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_explanation_compare.csv",
        "purpose": "Tabular score/evidence/QA/baseline/remediation comparison rows.",
    },
    {
        "asset_id": "candidate_explanation_compare_md",
        "category": "project_candidate_review",
        "path": "docs/candidate_explanation_compare.md",
        "purpose": "Markdown candidate explanation comparison handoff.",
    },
    {
        "asset_id": "candidate_explanation_drilldown",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_explanation_drilldown.json",
        "purpose": "Component-level candidate explanation drilldown linking score, evidence, QA, baseline, and remediation source artifacts.",
    },
    {
        "asset_id": "candidate_explanation_drilldown_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_explanation_drilldown.csv",
        "purpose": "Tabular component-level candidate explanation drilldown rows.",
    },
    {
        "asset_id": "candidate_explanation_drilldown_md",
        "category": "project_candidate_review",
        "path": "docs/candidate_explanation_drilldown.md",
        "purpose": "Markdown candidate explanation drilldown handoff.",
    },
    {
        "asset_id": "candidate_explanation_matrix",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_explanation_matrix.json",
        "purpose": "N-way candidate explanation matrix across score, evidence, QA, baseline, and remediation components.",
    },
    {
        "asset_id": "candidate_explanation_matrix_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_explanation_matrix.csv",
        "purpose": "Tabular N-way candidate explanation matrix rows.",
    },
    {
        "asset_id": "candidate_explanation_matrix_md",
        "category": "project_candidate_review",
        "path": "docs/candidate_explanation_matrix.md",
        "purpose": "Markdown N-way candidate explanation matrix handoff.",
    },
    {
        "asset_id": "candidate_explanation_score_breakdown_png",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_explanation_charts/candidate_explanation_score_breakdown.png",
        "purpose": "Native-readable score/evidence/QA/baseline/remediation breakdown chart for candidate explanation.",
    },
    {
        "asset_id": "candidate_decision_qa",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_decision_qa.json",
        "purpose": "Local decision QA report for accept/watch/needs-measurement/reject rows.",
    },
    {
        "asset_id": "candidate_decision_qa_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_decision_qa.csv",
        "purpose": "Tabular local decision QA rows.",
    },
    {
        "asset_id": "candidate_decision_qa_md",
        "category": "project_candidate_review",
        "path": "docs/candidate_decision_qa.md",
        "purpose": "Markdown local decision QA handoff.",
    },
    {
        "asset_id": "evidence_quality_scorecard",
        "category": "project_candidate_review",
        "path": "data/projects/demo/evidence_quality_scorecard.json",
        "purpose": "Local evidence-quality scorecard across evidence drawer, QA, review, and baseline context.",
    },
    {
        "asset_id": "evidence_quality_scorecard_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/evidence_quality_scorecard.csv",
        "purpose": "Tabular evidence-quality scorecard rows.",
    },
    {
        "asset_id": "evidence_quality_scorecard_md",
        "category": "project_candidate_review",
        "path": "docs/evidence_quality_scorecard.md",
        "purpose": "Markdown evidence-quality scorecard handoff.",
    },
    {
        "asset_id": "candidate_evidence_quality",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_evidence_quality.json",
        "purpose": "Legacy alias for the local evidence-quality scorecard.",
    },
    {
        "asset_id": "candidate_evidence_quality_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_evidence_quality.csv",
        "purpose": "Legacy tabular evidence-quality scorecard rows.",
    },
    {
        "asset_id": "candidate_evidence_quality_md",
        "category": "project_candidate_review",
        "path": "docs/candidate_evidence_quality.md",
        "purpose": "Legacy markdown evidence-quality scorecard handoff.",
    },
    {
        "asset_id": "candidate_baseline_manager",
        "category": "project_governance",
        "path": "data/projects/demo/candidate_baseline_manager.json",
        "purpose": "Local candidate baseline manager with active/archive status and stale baseline review prompts.",
    },
    {
        "asset_id": "candidate_baseline_manager_csv",
        "category": "project_governance",
        "path": "data/projects/demo/candidate_baseline_manager.csv",
        "purpose": "Tabular candidate baseline manager rows.",
    },
    {
        "asset_id": "candidate_baseline_manager_md",
        "category": "project_governance",
        "path": "docs/candidate_baseline_manager.md",
        "purpose": "Markdown candidate baseline manager handoff.",
    },
    {
        "asset_id": "reviewer_operations",
        "category": "project_candidate_review",
        "path": "data/projects/demo/reviewer_operations.json",
        "purpose": "Local reviewer operations report covering SLA, deferrals, handoff, and site-class closure.",
    },
    {
        "asset_id": "reviewer_operations_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/reviewer_operations.csv",
        "purpose": "Tabular reviewer operations rows.",
    },
    {
        "asset_id": "reviewer_operations_md",
        "category": "project_candidate_review",
        "path": "docs/reviewer_operations.md",
        "purpose": "Markdown reviewer operations handoff.",
    },
    {
        "asset_id": "baseline_lineage_compare",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_lineage_compare.json",
        "purpose": "Local baseline lineage compare for entered, exited, changed, and unchanged candidate rows.",
    },
    {
        "asset_id": "baseline_lineage_compare_csv",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_lineage_compare.csv",
        "purpose": "Tabular candidate baseline lineage rows.",
    },
    {
        "asset_id": "baseline_lineage_compare_md",
        "category": "project_governance",
        "path": "docs/baseline_lineage_compare.md",
        "purpose": "Markdown candidate baseline lineage handoff.",
    },
    {
        "asset_id": "candidate_baseline_lineage",
        "category": "project_governance",
        "path": "data/projects/demo/candidate_baseline_lineage.json",
        "purpose": "Legacy alias for local baseline lineage compare.",
    },
    {
        "asset_id": "candidate_baseline_lineage_csv",
        "category": "project_governance",
        "path": "data/projects/demo/candidate_baseline_lineage.csv",
        "purpose": "Legacy tabular candidate baseline lineage rows.",
    },
    {
        "asset_id": "candidate_baseline_lineage_md",
        "category": "project_governance",
        "path": "docs/candidate_baseline_lineage.md",
        "purpose": "Legacy markdown candidate baseline lineage handoff.",
    },
    {
        "asset_id": "review_command_center",
        "category": "project_candidate_review",
        "path": "data/projects/demo/review_command_center.json",
        "purpose": "Native command-center rows linking production gates, evidence quality, reviewer operations, and baseline movement.",
    },
    {
        "asset_id": "review_command_center_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/review_command_center.csv",
        "purpose": "Tabular review command-center rows for native drill-down.",
    },
    {
        "asset_id": "review_command_center_md",
        "category": "project_candidate_review",
        "path": "docs/review_command_center.md",
        "purpose": "Markdown review command-center handoff.",
    },
    {
        "asset_id": "candidate_remediation_queue",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_remediation_queue.json",
        "purpose": "Local-only candidate remediation queue for evidence quality, reviewer, decision QA, and baseline history follow-up tasks.",
    },
    {
        "asset_id": "candidate_remediation_queue_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_remediation_queue.csv",
        "purpose": "Tabular local candidate remediation queue.",
    },
    {
        "asset_id": "candidate_remediation_queue_md",
        "category": "project_candidate_review",
        "path": "docs/candidate_remediation_queue.md",
        "purpose": "Markdown local candidate remediation handoff.",
    },
    {
        "asset_id": "candidate_remediation_queue_history",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_remediation_queue_history.json",
        "purpose": "Immutable local history for candidate remediation task status, owner, due-date, and closure-note edits.",
    },
    {
        "asset_id": "candidate_remediation_queue_history_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_remediation_queue_history.csv",
        "purpose": "Tabular audit trail for local candidate remediation edits.",
    },
    {
        "asset_id": "candidate_remediation_queue_history_md",
        "category": "project_candidate_review",
        "path": "docs/candidate_remediation_queue_history.md",
        "purpose": "Markdown audit trail for local candidate remediation edits.",
    },
    {
        "asset_id": "candidate_remediation_saved_views_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_remediation_saved_views.csv",
        "purpose": "Saved remediation workbench views by priority, due age, task type, and owner.",
    },
    {
        "asset_id": "candidate_remediation_trends_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_remediation_trends.csv",
        "purpose": "Remediation workbench trend slices by status, priority, task type, owner, and age band.",
    },
    {
        "asset_id": "candidate_review_ops_console",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_review_ops_console.json",
        "purpose": "Merged local review operations console across review board, owner, risk, blockers, and remediation tasks.",
    },
    {
        "asset_id": "candidate_review_ops_console_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/candidate_review_ops_console.csv",
        "purpose": "Tabular candidate review operations rows for native UI review.",
    },
    {
        "asset_id": "candidate_review_ops_console_md",
        "category": "project_candidate_review",
        "path": "docs/candidate_review_ops_console.md",
        "purpose": "Markdown candidate review operations console handoff.",
    },
    {
        "asset_id": "baseline_history_explorer",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_history_explorer.json",
        "purpose": "Baseline history explorer tracking saved baselines and local comparison movement over time.",
    },
    {
        "asset_id": "baseline_scenario_board",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_scenario_board.json",
        "purpose": "Scenario board comparing active baseline, candidate baseline, lineage, and policy/profile movement.",
    },
    {
        "asset_id": "baseline_scenario_board_csv",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_scenario_board.csv",
        "purpose": "Tabular baseline scenario board rows for native UI review.",
    },
    {
        "asset_id": "baseline_scenario_board_md",
        "category": "project_governance",
        "path": "docs/baseline_scenario_board.md",
        "purpose": "Markdown baseline scenario board handoff.",
    },
    {
        "asset_id": "baseline_whatif_board",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_whatif_board.json",
        "purpose": "Per-candidate baseline what-if rows for current, active baseline, candidate baseline, evidence policy, and profile rollback scenarios.",
    },
    {
        "asset_id": "baseline_whatif_board_csv",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_whatif_board.csv",
        "purpose": "Tabular baseline what-if candidate movement rows.",
    },
    {
        "asset_id": "baseline_whatif_board_md",
        "category": "project_governance",
        "path": "docs/baseline_whatif_board.md",
        "purpose": "Markdown baseline what-if handoff.",
    },
    {
        "asset_id": "baseline_history_explorer_csv",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_history_explorer.csv",
        "purpose": "Tabular baseline history explorer rows.",
    },
    {
        "asset_id": "baseline_history_explorer_md",
        "category": "project_governance",
        "path": "docs/baseline_history_explorer.md",
        "purpose": "Markdown baseline history explorer handoff.",
    },
    {
        "asset_id": "baseline_history_explorer_chart_png",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_history_explorer_charts/baseline_history_movement.png",
        "purpose": "Native UI preview chart for baseline comparison movement.",
    },
    {
        "asset_id": "baseline_history_explorer_chart_svg",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_history_explorer_charts/baseline_history_movement.svg",
        "purpose": "Vector baseline movement chart for review and release handoff.",
    },
    {
        "asset_id": "baseline_history_explorer_matrix_csv",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_history_explorer_matrix.csv",
        "purpose": "Pairwise baseline comparison matrix for local baseline workflow review.",
    },
    {
        "asset_id": "baseline_active_preview",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_active_preview.json",
        "purpose": "Active baseline versus current candidate movement preview.",
    },
    {
        "asset_id": "baseline_rollback_explanation_md",
        "category": "project_governance",
        "path": "docs/baseline_rollback_explanation.md",
        "purpose": "Local-only rollback explanation page for candidate baseline movement.",
    },
    {
        "asset_id": "review_remediation_queue",
        "category": "project_candidate_review",
        "path": "data/projects/demo/review_remediation_queue.json",
        "purpose": "Local-only review remediation queue for evidence quality, reviewer, decision QA, and baseline lineage follow-up tasks.",
    },
    {
        "asset_id": "review_remediation_queue_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/review_remediation_queue.csv",
        "purpose": "Tabular local review remediation queue.",
    },
    {
        "asset_id": "review_remediation_closure_ledger",
        "category": "project_candidate_review",
        "path": "data/projects/demo/review_remediation_closure_ledger.csv",
        "purpose": "Append-only local closure ledger for review remediation queue events.",
    },
    {
        "asset_id": "review_remediation_queue_md",
        "category": "project_candidate_review",
        "path": "docs/review_remediation_queue.md",
        "purpose": "Markdown local review remediation handoff.",
    },
    {
        "asset_id": "review_closure_workbench",
        "category": "project_candidate_review",
        "path": "data/projects/demo/review_closure_workbench.json",
        "purpose": "Batch-oriented local review closure workbench with reason taxonomy, due-date policy, and filtered audit history.",
    },
    {
        "asset_id": "review_closure_workbench_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/review_closure_workbench.csv",
        "purpose": "Tabular review closure workbench rows.",
    },
    {
        "asset_id": "review_closure_workbench_md",
        "category": "project_candidate_review",
        "path": "docs/review_closure_workbench.md",
        "purpose": "Markdown review closure workbench handoff.",
    },
    {
        "asset_id": "review_closure_filter_views",
        "category": "project_candidate_review",
        "path": "data/projects/demo/review_closure_filter_views.json",
        "purpose": "Filtered local review closure views by owner, reason, batch, overdue band, audit state, and priority.",
    },
    {
        "asset_id": "review_closure_filter_views_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/review_closure_filter_views.csv",
        "purpose": "Tabular review closure filter-view rows.",
    },
    {
        "asset_id": "review_closure_filter_views_md",
        "category": "project_candidate_review",
        "path": "docs/review_closure_filter_views.md",
        "purpose": "Markdown review closure filter-view handoff.",
    },
    {
        "asset_id": "baseline_lineage_history",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_lineage_history.json",
        "purpose": "Baseline lineage history tracking local baseline comparison movement over time.",
    },
    {
        "asset_id": "baseline_lineage_history_csv",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_lineage_history.csv",
        "purpose": "Tabular baseline lineage history rows.",
    },
    {
        "asset_id": "baseline_lineage_history_pairwise_csv",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_lineage_history_pairwise.csv",
        "purpose": "Pairwise baseline lineage movement deltas between adjacent history snapshots.",
    },
    {
        "asset_id": "baseline_lineage_history_chart_csv",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_lineage_history_chart.csv",
        "purpose": "Chart-ready baseline lineage movement rows for native trend previews.",
    },
    {
        "asset_id": "baseline_lineage_history_md",
        "category": "project_governance",
        "path": "docs/baseline_lineage_history.md",
        "purpose": "Markdown baseline lineage history handoff.",
    },
    {
        "asset_id": "baseline_lineage_preview",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_lineage_preview.json",
        "purpose": "Native preview rows and PNG pointer for baseline lineage movement history.",
    },
    {
        "asset_id": "baseline_lineage_preview_csv",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_lineage_preview.csv",
        "purpose": "Tabular baseline lineage preview rows.",
    },
    {
        "asset_id": "baseline_lineage_preview_md",
        "category": "project_governance",
        "path": "docs/baseline_lineage_preview.md",
        "purpose": "Markdown baseline lineage preview handoff.",
    },
    {
        "asset_id": "baseline_lineage_filter_views",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_lineage_filter_views.json",
        "purpose": "Filtered baseline-lineage preview views by row type, lineage status, movement bucket, and candidate state.",
    },
    {
        "asset_id": "baseline_lineage_filter_views_csv",
        "category": "project_governance",
        "path": "data/projects/demo/baseline_lineage_filter_views.csv",
        "purpose": "Tabular baseline lineage filter-view rows.",
    },
    {
        "asset_id": "baseline_lineage_filter_views_md",
        "category": "project_governance",
        "path": "docs/baseline_lineage_filter_views.md",
        "purpose": "Markdown baseline lineage filter-view handoff.",
    },
    {
        "asset_id": "native_drilldown_actions",
        "category": "project_governance",
        "path": "data/projects/demo/native_drilldown_actions.json",
        "purpose": "Native Reports selected-row routing actions for closure, lineage, explanation, and sandbox rows.",
    },
    {
        "asset_id": "native_drilldown_actions_csv",
        "category": "project_governance",
        "path": "data/projects/demo/native_drilldown_actions.csv",
        "purpose": "Tabular native selected-row drilldown action rows.",
    },
    {
        "asset_id": "native_drilldown_actions_md",
        "category": "project_governance",
        "path": "docs/native_drilldown_actions.md",
        "purpose": "Markdown native selected-row drilldown action handoff.",
    },
    {
        "asset_id": "operator_trend_summary",
        "category": "release",
        "path": "data/releases/operator_trend_summary.json",
        "purpose": "Compact operator-facing trend cards for backlog, baseline movement, DB latency, and packet coverage.",
    },
    {
        "asset_id": "operator_trend_summary_csv",
        "category": "release",
        "path": "data/releases/operator_trend_summary.csv",
        "purpose": "Tabular operator trend cards.",
    },
    {
        "asset_id": "operator_trend_summary_md",
        "category": "release",
        "path": "docs/operator_trend_summary.md",
        "purpose": "Markdown operator trend summary handoff.",
    },
    {
        "asset_id": "operator_trend_charts",
        "category": "release",
        "path": "data/releases/operator_trend_charts.json",
        "purpose": "SVG chart-pack manifest for operator trend cards.",
    },
    {
        "asset_id": "operator_trend_charts_csv",
        "category": "release",
        "path": "data/releases/operator_trend_charts.csv",
        "purpose": "Tabular operator trend chart rows with chart paths.",
    },
    {
        "asset_id": "operator_trend_charts_md",
        "category": "release",
        "path": "docs/operator_trend_charts.md",
        "purpose": "Markdown operator trend chart handoff.",
    },
    {
        "asset_id": "operator_trend_charts_dir",
        "category": "release",
        "path": "data/releases/operator_trend_charts",
        "purpose": "Generated SVG chart files for operator trend cards.",
    },
    {
        "asset_id": "medchem_discussion_handoff",
        "category": "project_candidate_review",
        "path": "data/projects/demo/medchem_discussion_handoff.json",
        "purpose": "Local medchem discussion handoff separated from purchasing and experiment execution.",
    },
    {
        "asset_id": "medchem_discussion_handoff_csv",
        "category": "project_candidate_review",
        "path": "data/projects/demo/medchem_discussion_handoff.csv",
        "purpose": "Tabular local medchem discussion handoff rows.",
    },
    {
        "asset_id": "medchem_discussion_handoff_md",
        "category": "project_candidate_review",
        "path": "docs/medchem_discussion_handoff.md",
        "purpose": "Markdown local medchem discussion handoff.",
    },
    {
        "asset_id": "native_portable_package_manifest",
        "category": "deployment",
        "path": "data/releases/native_portable_package_manifest.json",
        "purpose": "Manifest for the lightweight native portable package, excluding the large local SQLite warehouse.",
    },
    {
        "asset_id": "latest_release_checksum",
        "category": "release",
        "path": "data/releases/latest_release_checksum.json",
        "purpose": "SHA-256 sidecar checksum report for the latest release bundle.",
    },
]

COUNT_TABLES = [
    "substituent",
    "candidate_substituent",
    "raw_source_record",
    "substituent_review",
    "substituent_version_log",
    "substituent_vendor_overlay",
    "mmp_transform_evidence",
    "transform_mmp_mapping",
    "chembl_activity_evidence",
    "transform_activity_summary",
    "ring_system",
    "literature_substituent",
    "ring_replacement",
    "rgroup_replacement",
    "rgroup_replacement_normalized",
    "scaffold_replacement",
    "scaffold_rule_review_event",
    "project_run",
    "project_candidate",
    "project_feedback",
    "project_model_calibration",
    "project_route_batch",
    "route_batch_status_event",
    "route_quote_request",
    "project_feedback_control",
    "project_experiment_plan",
    "project_experiment_event",
    "project_decision_packet",
    "project_decision_packet_event",
    "next_design_queue_decision_event",
    "data_foundation_snapshot",
]

CORE_RECORD_TABLES = [
    "substituent",
    "candidate_substituent",
    "mmp_transform_evidence",
    "chembl_activity_evidence",
    "ring_system",
    "literature_substituent",
    "ring_replacement",
    "rgroup_replacement",
    "rgroup_replacement_normalized",
    "scaffold_replacement",
]


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _load_drift_thresholds(root: Path) -> dict:
    path = root / DEFAULT_DRIFT_THRESHOLDS_PATH
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_source_acceptance_manifest(root: str | Path = ".") -> dict:
    root = Path(root).resolve()
    path = root / DEFAULT_SOURCE_ACCEPTANCE_MANIFEST_PATH
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    data.setdefault("accepted_changes", [])
    return data


def _load_source_acceptance_manifest(root: Path) -> dict:
    return load_source_acceptance_manifest(root)


def _latest_data_foundation_snapshot(conn: sqlite3.Connection) -> dict:
    try:
        row = conn.execute(
            "SELECT payload_json FROM data_foundation_snapshot ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    except sqlite3.Error:
        return {}
    if not row:
        return {}
    try:
        return json.loads(row[0] or "{}")
    except Exception:
        return {}


def _assets_by_id(report: dict) -> dict[str, dict]:
    return {str(asset.get("asset_id")): asset for asset in report.get("assets") or [] if asset.get("asset_id")}


def _feed_governance_previous_rows(previous_snapshot: dict | None) -> dict[str, dict]:
    governance = (previous_snapshot or {}).get("rgroup_feed_governance") or {}
    previous = {}
    for row in governance.get("per_feed") or []:
        path = str(row.get("path") or "").strip()
        if path:
            previous[path] = row
    return previous


def _ratio(numerator: object, denominator: object) -> float | None:
    try:
        den = int(denominator or 0)
        if den <= 0:
            return None
        return round(int(numerator or 0) / den, 4)
    except (TypeError, ValueError):
        return None


def _count_delta(current: object, previous: object | None) -> int | None:
    if previous is None:
        return None
    try:
        return int(current or 0) - int(previous or 0)
    except (TypeError, ValueError):
        return None


def _build_rgroup_feed_governance(root: Path, previous_snapshot: dict | None = None) -> dict:
    metadata = _read_json(root / "data/substituents/rgroup_feed_metadata_report.json")
    coverage = _read_json(root / "data/substituents/rgroup_feed_review_coverage.json")
    if not metadata and not coverage:
        return {"status": "missing", "available": False, "per_feed": []}

    previous = (previous_snapshot or {}).get("rgroup_feed_governance") or {}
    previous_rows = _feed_governance_previous_rows(previous_snapshot)
    per_feed = []
    for report in metadata.get("reports") or []:
        path = str(report.get("path") or "")
        row_count = int(report.get("row_count") or 0)
        provenance_count = int(report.get("row_level_provenance_count") or 0)
        previous_row = previous_rows.get(path) or {}
        previous_count = previous_row.get("row_count")
        per_feed.append(
            {
                "path": path,
                "feed_name": Path(path).name if path else "",
                "row_count": row_count,
                "previous_row_count": previous_count,
                "row_count_delta": _count_delta(row_count, previous_count),
                "row_level_provenance_count": provenance_count,
                "provenance_complete_fraction": _ratio(provenance_count, row_count),
                "allowlist_issue_count": int(report.get("allowlist_issue_count") or 0),
                "freshness_issue_count": int(report.get("freshness_issue_count") or 0),
                "review_status_counts": report.get("review_status_counts") or {},
                "source_counts": report.get("source_counts") or {},
            }
        )

    row_count = int(metadata.get("row_count") or 0)
    provenance_count = int(metadata.get("row_level_provenance_count") or 0)
    allowlist_issue_count = int(metadata.get("allowlist_issue_count") or 0)
    freshness_issue_count = int(metadata.get("freshness_issue_count") or 0)
    no_review_count = int(coverage.get("no_review_count") or 0)
    low_coverage_count = int(coverage.get("low_coverage_count") or 0)
    status = "ok"
    if allowlist_issue_count:
        status = "error"
    elif freshness_issue_count or no_review_count or low_coverage_count:
        status = "warning"
    return {
        "status": status,
        "available": True,
        "created_at": metadata.get("created_at") or coverage.get("created_at"),
        "feed_count": int(metadata.get("feed_count") or len(per_feed)),
        "row_count": row_count,
        "previous_row_count": previous.get("row_count"),
        "row_count_delta": _count_delta(row_count, previous.get("row_count")),
        "row_level_provenance_count": provenance_count,
        "provenance_complete_fraction": _ratio(provenance_count, row_count),
        "allowlist_issue_count": allowlist_issue_count,
        "freshness_issue_count": freshness_issue_count,
        "sample_review_count": int(metadata.get("sample_review_count") or coverage.get("review_row_count") or 0),
        "coverage_cell_count": int(coverage.get("coverage_cell_count") or 0),
        "covered_count": int(coverage.get("covered_count") or 0),
        "no_review_count": no_review_count,
        "low_coverage_count": low_coverage_count,
        "coverage_status_counts": coverage.get("coverage_status_counts") or {},
        "per_feed": per_feed,
    }


def _parse_manifest_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if len(text) == 10:
            return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _acceptance_matches_issue(issue: dict, acceptance_manifest: dict | None) -> dict | None:
    manifest = acceptance_manifest or {}
    now = datetime.now(timezone.utc)
    for item in manifest.get("accepted_changes") or manifest.get("acceptances") or []:
        check = str(item.get("check") or item.get("accepted_change") or "")
        accepted_checks = {check}
        if check == "count_jump":
            accepted_checks.add("unexpected_count_jump")
        if check == "unexpected_count_jump":
            accepted_checks.add("count_jump")
        if check and issue.get("check") not in accepted_checks:
            continue
        table = item.get("table")
        if table and str(table) != str(issue.get("table")):
            continue
        asset_id = item.get("asset_id")
        if asset_id and str(asset_id) != str(issue.get("asset_id")):
            continue
        expires_at = _parse_manifest_datetime(item.get("expires_at"))
        if expires_at and expires_at < now:
            continue
        if issue.get("check") in {"count_drop"} and item.get("max_accepted_drop_fraction") is not None:
            if float(issue.get("drop_fraction") or 0.0) > float(item.get("max_accepted_drop_fraction") or 0.0):
                continue
        if issue.get("check") in {"unexpected_count_jump", "count_jump"} and item.get("max_accepted_jump_fraction") is not None:
            if float(issue.get("jump_fraction") or 0.0) > float(item.get("max_accepted_jump_fraction") or 0.0):
                continue
        return item
    return None


def validate_source_expansion_acceptance(
    *,
    table: str | None = None,
    check: str = "unexpected_count_jump",
    change_fraction: float | None = None,
    asset_id: str | None = None,
    root: str | Path = ".",
    acceptance_manifest: dict | None = None,
) -> dict:
    manifest = acceptance_manifest or load_source_acceptance_manifest(root)
    issue = {
        "severity": "warning",
        "check": check,
        "message": "Source expansion requires manifest acceptance.",
        "table": table,
        "asset_id": asset_id,
    }
    if check in {"unexpected_count_jump", "count_jump"} and change_fraction is not None:
        issue["jump_fraction"] = round(float(change_fraction), 4)
    if check == "count_drop" and change_fraction is not None:
        issue["drop_fraction"] = round(float(change_fraction), 4)
    acceptance = _acceptance_matches_issue(issue, manifest)
    return {
        "accepted": bool(acceptance),
        "acceptance_id": (acceptance or {}).get("acceptance_id"),
        "accepted_until": (acceptance or {}).get("expires_at"),
        "reason": (acceptance or {}).get("reason") or (acceptance or {}).get("note"),
        "table": table,
        "asset_id": asset_id,
        "check": check,
        "change_fraction": change_fraction,
        "manifest_version": manifest.get("version"),
    }


def evaluate_data_drift(
    current_report: dict,
    previous_report: dict | None = None,
    thresholds: dict | None = None,
    acceptance_manifest: dict | None = None,
) -> dict:
    thresholds = thresholds or {}
    policy = thresholds.get("alert_policy") or {}
    count_thresholds = thresholds.get("count_thresholds") or {}
    issues: list[dict] = []
    accepted_issues: list[dict] = []

    def add(severity: str, check: str, message: str, **extra) -> None:
        issue = {"severity": severity, "check": check, "message": message, **extra}
        acceptance = _acceptance_matches_issue(issue, acceptance_manifest)
        if acceptance:
            issue["accepted_by"] = acceptance.get("acceptance_id")
            issue["accepted_reason"] = acceptance.get("reason") or acceptance.get("note")
            issue["accepted_until"] = acceptance.get("expires_at")
            accepted_issues.append(issue)
            return
        issues.append(issue)

    current_counts = current_report.get("table_counts") or {}
    previous_counts = (previous_report or {}).get("table_counts") or {}
    count_deltas = []
    for table, cfg in sorted(count_thresholds.items()):
        current = int(current_counts.get(table) or 0)
        previous = int(previous_counts.get(table) or 0)
        delta = current - previous if previous_report else None
        delta_fraction = round(delta / previous, 4) if previous and delta is not None else None
        count_deltas.append(
            {
                "table": table,
                "current_count": current,
                "previous_count": previous if previous_report else None,
                "delta": delta,
                "delta_fraction": delta_fraction,
                "minimum": cfg.get("min_count"),
            }
        )
        if cfg.get("min_count") is not None and current < int(cfg.get("min_count") or 0):
            add(
                policy.get("count_below_minimum", "warning"),
                "count_below_minimum",
                f"{table} is below configured minimum.",
                table=table,
                current_count=current,
                minimum=cfg.get("min_count"),
            )
        if previous and cfg.get("max_drop_fraction") is not None:
            drop_fraction = (previous - current) / previous
            if drop_fraction > float(cfg.get("max_drop_fraction") or 0):
                add(
                    policy.get("count_drop", "error"),
                    "count_drop",
                    f"{table} dropped more than allowed.",
                    table=table,
                    previous_count=previous,
                    current_count=current,
                    drop_fraction=round(drop_fraction, 4),
                )
        if previous and cfg.get("max_jump_fraction") is not None:
            jump_fraction = (current - previous) / previous
            if jump_fraction > float(cfg.get("max_jump_fraction") or 0):
                add(
                    policy.get("unexpected_count_jump", "warning"),
                    "unexpected_count_jump",
                    f"{table} increased more than the configured watch threshold.",
                    table=table,
                    previous_count=previous,
                    current_count=current,
                    jump_fraction=round(jump_fraction, 4),
                )

    checksum_changes = []
    current_assets = _assets_by_id(current_report)
    previous_assets = _assets_by_id(previous_report or {})
    for asset_id in thresholds.get("asset_checksum_watchlist") or []:
        current = current_assets.get(str(asset_id)) or {}
        previous = previous_assets.get(str(asset_id)) or {}
        current_sha = current.get("sha256")
        previous_sha = previous.get("sha256")
        if current_sha and previous_sha and current_sha != previous_sha:
            change = {
                "asset_id": asset_id,
                "previous_sha256": previous_sha,
                "current_sha256": current_sha,
                "current_modified_at": current.get("modified_at"),
            }
            checksum_changes.append(change)
            severity = policy.get("checksum_change", "watch")
            if severity not in {"ignore", "watch"}:
                add(severity, "checksum_change", f"{asset_id} checksum changed.", **change)

    if not previous_report:
        severity = policy.get("missing_previous_snapshot", "warning")
        if severity != "ignore":
            add(severity, "missing_previous_snapshot", "No previous data-foundation snapshot is available.")

    status = "error" if any(item["severity"] == "error" for item in issues) else "warning" if any(item["severity"] in {"warning", "watch"} for item in issues) else "ok"
    return {
        "status": status,
        "issue_count": len(issues),
        "error_count": sum(1 for item in issues if item["severity"] == "error"),
        "warning_count": sum(1 for item in issues if item["severity"] in {"warning", "watch"}),
        "issues": issues,
        "accepted_issue_count": len(accepted_issues),
        "accepted_issues": accepted_issues,
        "count_deltas": count_deltas,
        "checksum_change_count": len(checksum_changes),
        "checksum_changes": checksum_changes,
        "previous_snapshot_id": (previous_report or {}).get("snapshot_id"),
        "threshold_version": thresholds.get("version"),
        "acceptance_manifest_version": (acceptance_manifest or {}).get("version"),
    }


def data_currency_badge(report: dict, daily_alert: dict | None = None) -> dict:
    ring_status = ((report.get("import_state") or {}).get("ring_import_status") or {})
    quality = report.get("quality_gate") or {}
    drift = report.get("data_drift") or {}
    ci_gate = report.get("ci_gate") or {}
    alert_level = (daily_alert or {}).get("alert_level")
    bad = alert_level == "error" or ci_gate.get("status") == "error" or drift.get("status") == "error"
    warn = alert_level == "warning" or ci_gate.get("status") == "warning" or drift.get("status") == "warning"
    status = "error" if bad else "warning" if warn else "ok"
    return {
        "status": status,
        "label": f"Data currency: {status}",
        "last_snapshot_at": report.get("created_at"),
        "last_maintenance_at": (daily_alert or {}).get("created_at"),
        "alert_level": alert_level,
        "ring_next_offset": ring_status.get("next_offset"),
        "ring_progress_percent": ring_status.get("progress_percent"),
        "strict_quality_ok": quality.get("quality_report_ok"),
        "ci_gate": ci_gate.get("status"),
        "data_drift": drift.get("status"),
    }


def _path_entry(root: Path, asset: dict, *, include_checksums: bool) -> dict:
    path = root / asset["path"]
    entry = {
        "asset_id": asset["asset_id"],
        "category": asset["category"],
        "path": str(path.resolve()),
        "exists": path.exists(),
        "purpose": asset.get("purpose"),
        "db_table": asset.get("db_table"),
    }
    if path.is_file():
        entry.update(
            {
                "kind": "file",
                "size_bytes": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                "sha256": file_sha256(path) if include_checksums else None,
            }
        )
    elif path.is_dir():
        file_stats = []
        for item in path.rglob("*"):
            try:
                if not item.is_file():
                    continue
                file_stats.append(item.stat())
            except OSError:
                continue
        try:
            dir_mtime = path.stat().st_mtime
        except OSError:
            dir_mtime = datetime.now(timezone.utc).timestamp()
        entry.update(
            {
                "kind": "directory",
                "file_count": len(file_stats),
                "size_bytes": sum(stat.st_size for stat in file_stats),
                "modified_at": datetime.fromtimestamp(max((stat.st_mtime for stat in file_stats), default=dir_mtime), timezone.utc).isoformat(),
                "sha256": None,
            }
        )
    else:
        entry.update({"kind": "missing", "size_bytes": None, "modified_at": None, "sha256": None})
    return entry


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.Error:
        return 0


def _group_counts(conn: sqlite3.Connection, table: str, columns: list[str], *, limit: int = 50) -> list[dict]:
    col_sql = ", ".join(columns)
    try:
        rows = conn.execute(
            f"""
            SELECT {col_sql}, COUNT(*) AS count
            FROM {table}
            GROUP BY {col_sql}
            ORDER BY count DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.Error:
        return []
    results = []
    for row in rows:
        item = {column: row[idx] for idx, column in enumerate(columns)}
        item["count"] = int(row[len(columns)])
        results.append(item)
    return results


def _top_tags(conn: sqlite3.Connection, *, limit: int = 25) -> list[dict]:
    try:
        rows = conn.execute(
            """
            SELECT tag_type, tag_value, COUNT(*) AS count
            FROM substituent_tag
            GROUP BY tag_type, tag_value
            ORDER BY count DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.Error:
        return []
    return [{"tag_type": row[0], "tag_value": row[1], "count": int(row[2])} for row in rows]


def _route_template_count(root: Path) -> int:
    path = root / "data/vendor/synthesis_route_templates.yaml"
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")
    return text.count("template_id:")


def _profile_count(root: Path) -> int:
    path = root / "data/profiles"
    if not path.exists():
        return 0
    return len(list(path.rglob("*.yaml")))


def _recommendations(table_counts: dict, review_status_counts: list[dict], warnings: list[dict]) -> list[str]:
    recs = []
    review_counter = Counter({item.get("review_status") or "unknown": item["count"] for item in review_status_counts})
    if review_counter.get("needs_medchem_review", 0) > max(review_counter.get("approved", 0), 0):
        recs.append("Prioritize medchem review of the governed substituent library before widening automatic promotion.")
    if table_counts.get("project_feedback", 0) < 20:
        recs.append("Import more assay/ADME feedback so calibrated profiles and drift checks have enough signal.")
    if table_counts.get("transform_activity_summary", 0) < max(1, table_counts.get("transform_mmp_mapping", 0) // 3):
        recs.append("Expand transform activity summaries across more mapped MMP transforms.")
    if table_counts.get("ring_system", 0) < 100000:
        recs.append("Continue DB-only Ertl ring chunks until ring/scaffold search has broader coverage.")
    if warnings:
        recs.append("Clear missing or thin data assets before treating this bundle as a shared release baseline.")
    return recs


def _release_manifest_drift(root: Path) -> dict:
    path = root / "data/releases/manifest_diff_latest.json"
    diff = _read_json(path)
    if not diff:
        return {
            "available": False,
            "added_count": 0,
            "changed_count": 0,
            "removed_count": 0,
            "risk_level": "unknown",
        }
    removed = int(diff.get("removed_count") or 0)
    changed = int(diff.get("changed_count") or 0)
    added = int(diff.get("added_count") or 0)
    if removed:
        risk = "high"
    elif changed > 75 or added > 25:
        risk = "medium"
    else:
        risk = "low"
    return {
        "available": True,
        "path": str(path.resolve()),
        "base_file_count": diff.get("base_file_count"),
        "head_file_count": diff.get("head_file_count"),
        "added_count": added,
        "changed_count": changed,
        "removed_count": removed,
        "risk_level": risk,
    }


def _count_group(rows: list[dict], column: str, value: str) -> int:
    return sum(int(row.get("count") or 0) for row in rows if str(row.get(column) or "") == value)


def evaluate_data_foundation_gate(
    report: dict,
    *,
    min_ring_system_count: int = 20000,
    max_review_backlog_ratio: float = 0.75,
) -> dict:
    """Evaluate whether the local data foundation is healthy enough for release CI."""
    issues = []

    def add(severity: str, check: str, message: str, **extra) -> None:
        issues.append({"severity": severity, "check": check, "message": message, **extra})

    table_counts = report.get("table_counts") or {}
    quality_gate = report.get("quality_gate") or {}
    import_state = report.get("import_state") or {}
    ring_status = (import_state.get("ring_import_status") or {})
    checkpoint = ring_status.get("checkpoint_integrity") or {}
    drift = report.get("release_drift") or {}
    data_drift = report.get("data_drift") or {}
    coverage = report.get("coverage") or {}
    review_counts = report.get("review_status_counts") or []

    for warning in report.get("warnings") or []:
        if warning.get("severity") == "error":
            add("error", warning.get("check") or "warning_escalated", warning.get("message") or "Data foundation warning escalated.")

    if quality_gate.get("quality_report_ok") is False:
        add("error", "quality_report", "Latest data quality report is not green.")
    if drift.get("available") and drift.get("risk_level") == "high":
        add("error", "release_drift", "Release drift removed assets or records; review before release.")
    if data_drift.get("status") == "error":
        add("error", "data_drift", "Data count/checksum drift exceeded an error threshold.")
    elif data_drift.get("status") == "warning":
        add("warning", "data_drift", "Data count/checksum drift has warnings that should be reviewed.")
    if checkpoint.get("status") == "error":
        add("error", "ring_import_checkpoint", "Ring import checkpoint integrity failed.")
    elif checkpoint.get("status") == "warning":
        add("warning", "ring_import_checkpoint", "Ring import checkpoint has warnings.")

    if table_counts.get("ring_system", 0) < min_ring_system_count:
        add(
            "warning",
            "ring_system_count",
            f"Ring-system table has fewer than {min_ring_system_count} records.",
            current_count=table_counts.get("ring_system", 0),
            minimum=min_ring_system_count,
        )
    if table_counts.get("project_feedback", 0) < 20:
        add("warning", "project_feedback_count", "Project feedback is still thin for stable calibration.")
    if table_counts.get("mmp_transform_evidence", 0) == 0:
        add("warning", "mmp_transform_evidence", "No public MMP transform evidence is loaded.")

    review_total = sum(int(row.get("count") or 0) for row in review_counts)
    review_backlog = _count_group(review_counts, "review_status", "needs_medchem_review")
    if review_total and review_backlog / review_total > max_review_backlog_ratio:
        add(
            "warning",
            "review_backlog",
            "Most governed substituents are still waiting for medchem review.",
            backlog_count=review_backlog,
            review_total=review_total,
        )

    low_confidence_events = _count_group(coverage.get("assay_confidence") or [], "assay_confidence", "low")
    retest_events = _count_group(coverage.get("experiment_stop_go") or [], "stop_go_decision", "retest")
    triage = report.get("assay_event_triage") or {}
    addressed = triage.get("addressed_issue_counts") or {}
    triage_open = triage.get("open_issue_counts") or {}
    addressed_low_confidence = int(addressed.get("low_confidence_assay") or 0)
    addressed_retest = int(addressed.get("open_retest") or 0)
    if triage_open:
        open_low_confidence = int(triage_open.get("low_confidence_assay") or 0)
        open_retest = int(triage_open.get("open_retest") or 0)
        addressed_low_confidence = max(addressed_low_confidence, low_confidence_events - open_low_confidence)
        addressed_retest = max(addressed_retest, retest_events - open_retest)
    else:
        open_low_confidence = max(low_confidence_events - addressed_low_confidence, 0)
        open_retest = max(retest_events - addressed_retest, 0)
    if open_low_confidence:
        add(
            "warning",
            "low_confidence_assay_events",
            "Low-confidence assay events remain in project memory.",
            count=open_low_confidence,
            total_count=low_confidence_events,
            triaged_count=addressed_low_confidence,
        )
    if open_retest:
        add(
            "warning",
            "open_retest_events",
            "Retest events remain unresolved in project memory.",
            count=open_retest,
            total_count=retest_events,
            triaged_count=addressed_retest,
        )

    status = "error" if any(issue["severity"] == "error" for issue in issues) else "warning" if issues else "ok"
    return {
        "status": status,
        "passed": status != "error",
        "error_count": sum(1 for issue in issues if issue["severity"] == "error"),
        "warning_count": sum(1 for issue in issues if issue["severity"] == "warning"),
        "issues": issues,
        "thresholds": {
            "min_ring_system_count": min_ring_system_count,
            "max_review_backlog_ratio": max_review_backlog_ratio,
        },
    }


def build_data_foundation_report(
    root: str | Path = ".",
    *,
    db_path: str | Path | None = None,
    include_checksums: bool = True,
) -> dict:
    root_path = Path(root).resolve()
    db_file = Path(db_path) if db_path is not None else root_path / DEFAULT_DB_PATH
    db_file = db_file if db_file.is_absolute() else root_path / db_file
    created_at = datetime.now(timezone.utc).isoformat()

    assets = [_path_entry(root_path, asset, include_checksums=include_checksums) for asset in DEFAULT_ASSETS]
    for asset in assets:
        modified_at = asset.get("modified_at")
        if modified_at:
            try:
                modified_dt = datetime.fromisoformat(str(modified_at).replace("Z", "+00:00"))
                asset["freshness_days"] = round((datetime.now(timezone.utc) - modified_dt).total_seconds() / 86400, 2)
            except ValueError:
                asset["freshness_days"] = None
    previous_snapshot = {}
    conn = initialize_database(db_file)
    try:
        table_counts = {table: _table_count(conn, table) for table in COUNT_TABLES}
        review_status_counts = _group_counts(conn, "substituent_review", ["review_status"])
        site_coverage = _group_counts(conn, "substituent_site_compatibility", ["site_type"])
        source_breakdown = {
            "raw_source_record": _group_counts(conn, "raw_source_record", ["source_name"]),
            "candidate_substituent": _group_counts(conn, "candidate_substituent", ["source_name"]),
            "ring_system": _group_counts(conn, "ring_system", ["source_name", "source_dataset"]),
            "literature_substituent": _group_counts(conn, "literature_substituent", ["source_name", "source_dataset"]),
            "ring_replacement": _group_counts(conn, "ring_replacement", ["source_name"]),
            "rgroup_replacement": _group_counts(conn, "rgroup_replacement", ["source_name"]),
            "rgroup_replacement_normalized": _group_counts(conn, "rgroup_replacement_normalized", ["source_names"]),
            "mmp_transform_evidence": _group_counts(conn, "mmp_transform_evidence", ["source_name"]),
        }
        coverage = {
            "top_substituent_tags": _top_tags(conn),
            "site_compatibility": site_coverage,
            "vendor_availability": _group_counts(conn, "substituent_vendor_overlay", ["availability_tier"]),
            "project_run_contexts": _group_counts(conn, "project_run", ["scoring_profile_id", "calibration_id"]),
            "experiment_plan_status": _group_counts(conn, "project_experiment_plan", ["status"]),
            "experiment_result_status": _group_counts(conn, "project_experiment_event", ["status"]),
            "experiment_stop_go": _group_counts(conn, "project_experiment_event", ["stop_go_decision"]),
            "assay_confidence": _group_counts(conn, "project_experiment_event", ["assay_confidence"]),
            "decision_packet_status": _group_counts(conn, "project_decision_packet", ["status"]),
            "route_batch_status": _group_counts(conn, "project_route_batch", ["chemist_approval_status"]),
            "route_template_count": _route_template_count(root_path),
            "scoring_profile_count": _profile_count(root_path),
        }
        previous_snapshot = _latest_data_foundation_snapshot(conn)
    finally:
        conn.close()

    quality_report = _read_json(root_path / "data/substituents/data_quality_hardening_report.json") or _read_json(root_path / "data/substituents/data_quality_report.json")
    ci_report = _read_json(root_path / "data/releases/ci_release_report.json")
    ring_import_state = _read_json(root_path / "data/substituents/ring_import_state.json")
    chunk_report = _read_json(root_path / "data/substituents/ertl_ring_chunk_import_report.json")
    assay_event_triage = _read_json(root_path / "data/projects/demo/assay_event_triage_report.json")
    rgroup_pair_owner_packet = _read_json(root_path / "data/substituents/rgroup_pair_conflict_owner_review_packet.json")
    rgroup_pair_owner_ledger = _read_json(root_path / "data/substituents/rgroup_pair_conflict_owner_decision_ledger.json")
    rgroup_feed_onboarding = _read_json(root_path / "data/substituents/rgroup_feed_onboarding_gate.json")
    rgroup_feed_staging = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_staging.json")
    rgroup_feed_staging_gate = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_staging_gate.json")
    feed_absorption_audit = _read_json(root_path / "data/substituents/feed_absorption_audit.json")
    feed_absorption_diff = _read_json(root_path / "data/substituents/feed_absorption_diff_navigator.json")
    source_expansion_governance = _read_json(root_path / "data/substituents/source_expansion_governance.json")
    feed_promotion_simulator = _read_json(root_path / "data/substituents/feed_promotion_simulator.json")
    staging_quality_budget = _read_json(root_path / "data/substituents/rgroup_staging_quality_budget.json")
    rgroup_staging_fill = _read_json(root_path / "data/substituents/rgroup_staging_fill_report.json")
    governed_ingestion_batches = _read_json(root_path / "data/substituents/governed_ingestion_batches.json")
    staged_feed_sandbox_scoring = _read_json(root_path / "data/projects/demo/staged_feed_sandbox_scoring.json")
    sandbox_score_delta_review = _read_json(root_path / "data/projects/demo/sandbox_score_delta_review_packet.json")
    sandbox_score_delta_signoff = _read_json(root_path / "data/projects/demo/sandbox_score_delta_signoff_ledger.json")
    rgroup_feed_digestion = _read_json(root_path / "data/substituents/rgroup_feed_digestion_ledger.json")
    rgroup_selective_approval = _read_json(root_path / "data/substituents/rgroup_selective_approval_batch.json")
    rgroup_promotion_approval = _read_json(root_path / "data/substituents/rgroup_promotion_approval_ledger.json")
    rgroup_digestion_quality_metrics = _read_json(root_path / "data/substituents/rgroup_digestion_quality_metrics.json")
    rgroup_digestion_quality_closure = _read_json(root_path / "data/substituents/rgroup_digestion_quality_closure_queue.json")
    feed_promotion_rollback = _read_json(root_path / "data/substituents/feed_promotion_rollback_audit.json")
    rgroup_approval_workbench = _read_json(root_path / "data/substituents/rgroup_approval_workbench.json")
    rgroup_ring_context_alignment = _read_json(root_path / "data/substituents/rgroup_ring_context_alignment.json")
    staging_sandbox_filter_views = _read_json(root_path / "data/projects/demo/staging_sandbox_filter_views.json")
    local_db_maintenance_release_gate = _read_json(root_path / "data/releases/local_db_maintenance_release_gate.json")
    native_drilldown_actions = _read_json(root_path / "data/projects/demo/native_drilldown_actions.json")
    ring_outcome_readiness = _read_json(root_path / "data/projects/demo/ring_outcome_production_readiness.json")
    ring_outcome_result_package = _read_json(root_path / "data/projects/demo/ring_outcome_result_package.json")
    ring_outcome_holdout = _read_json(root_path / "data/projects/demo/ring_outcome_holdout_report.json")
    ring_import_status = build_ring_import_status(db_path=db_file)
    rgroup_feed_governance = _build_rgroup_feed_governance(root_path, previous_snapshot)
    if rgroup_feed_governance.get("available"):
        coverage["rgroup_feed_review"] = {
            "status": rgroup_feed_governance.get("status"),
            "coverage_cell_count": rgroup_feed_governance.get("coverage_cell_count"),
            "covered_count": rgroup_feed_governance.get("covered_count"),
            "no_review_count": rgroup_feed_governance.get("no_review_count"),
            "low_coverage_count": rgroup_feed_governance.get("low_coverage_count"),
            "coverage_status_counts": rgroup_feed_governance.get("coverage_status_counts"),
        }
    if rgroup_feed_onboarding:
        coverage["rgroup_feed_onboarding"] = {
            "status": rgroup_feed_onboarding.get("status"),
            "feed_file_count": rgroup_feed_onboarding.get("feed_file_count"),
            "unmanifested_file_count": rgroup_feed_onboarding.get("unmanifested_file_count"),
            "deferred_source_owner_review_count": rgroup_feed_onboarding.get("deferred_source_owner_review_count"),
            "pending_source_owner_review_count": rgroup_feed_onboarding.get("pending_source_owner_review_count"),
            "recorded_source_owner_review_count": rgroup_feed_onboarding.get("recorded_source_owner_review_count"),
        }
    if rgroup_feed_staging:
        coverage["rgroup_feed_drop_staging"] = {
            "status": rgroup_feed_staging.get("status"),
            "drop_label": rgroup_feed_staging.get("drop_label"),
            "template_file_count": rgroup_feed_staging.get("template_file_count"),
            "source_dataset_count": rgroup_feed_staging.get("source_dataset_count"),
            "manifest_path": rgroup_feed_staging.get("manifest_path"),
        }
    if rgroup_feed_staging_gate:
        coverage["rgroup_feed_drop_staging_gate"] = {
            "status": rgroup_feed_staging_gate.get("status"),
            "staged_file_count": rgroup_feed_staging_gate.get("staged_file_count"),
            "filled_file_count": rgroup_feed_staging_gate.get("filled_file_count"),
            "staged_row_count": rgroup_feed_staging_gate.get("staged_row_count"),
            "blocker_count": rgroup_feed_staging_gate.get("blocker_count"),
            "warning_count": rgroup_feed_staging_gate.get("warning_count"),
        }
    if feed_absorption_audit:
        coverage["feed_absorption_audit"] = {
            "status": feed_absorption_audit.get("status"),
            "row_count": feed_absorption_audit.get("row_count"),
            "blocker_count": feed_absorption_audit.get("blocker_count"),
            "warning_count": feed_absorption_audit.get("warning_count"),
            "feed_row_count": feed_absorption_audit.get("feed_row_count"),
            "normalized_count": feed_absorption_audit.get("normalized_count"),
        }
    if feed_absorption_diff:
        coverage["feed_absorption_diff_navigator"] = {
            "status": feed_absorption_diff.get("status"),
            "row_count": feed_absorption_diff.get("row_count"),
            "blocker_count": feed_absorption_diff.get("blocker_count"),
            "warning_count": feed_absorption_diff.get("warning_count"),
            "feed_delta_count": feed_absorption_diff.get("feed_delta_count"),
            "duplicate_group_count": feed_absorption_diff.get("duplicate_group_count"),
        }
    if source_expansion_governance:
        coverage["source_expansion_governance"] = {
            "status": source_expansion_governance.get("status"),
            "row_count": source_expansion_governance.get("row_count"),
            "blocked_gate_count": source_expansion_governance.get("blocked_gate_count"),
            "ungated_expansion_allowed": source_expansion_governance.get("ungated_expansion_allowed"),
            "allowed_expansion_scopes": source_expansion_governance.get("allowed_expansion_scopes"),
        }
    if feed_promotion_simulator:
        coverage["feed_promotion_simulator"] = {
            "status": feed_promotion_simulator.get("status"),
            "row_count": feed_promotion_simulator.get("row_count"),
            "staged_row_count": feed_promotion_simulator.get("staged_row_count"),
            "blocker_count": feed_promotion_simulator.get("blocker_count"),
            "warning_count": feed_promotion_simulator.get("warning_count"),
            "promotion_allowed_count": feed_promotion_simulator.get("promotion_allowed_count"),
        }
    if staging_quality_budget:
        coverage["rgroup_staging_quality_budget"] = {
            "status": staging_quality_budget.get("status"),
            "source_count": staging_quality_budget.get("source_count"),
            "staged_row_count": staging_quality_budget.get("staged_row_count"),
            "blocker_count": staging_quality_budget.get("blocker_count"),
            "operator_signoff_required": staging_quality_budget.get("operator_signoff_required"),
            "promotion_allowed_without_sandbox_review": staging_quality_budget.get("promotion_allowed_without_sandbox_review"),
        }
    if rgroup_staging_fill:
        coverage["rgroup_staging_fill_report"] = {
            "status": rgroup_staging_fill.get("status"),
            "filled_file_count": rgroup_staging_fill.get("filled_file_count"),
            "staged_row_count": rgroup_staging_fill.get("staged_row_count"),
            "skipped_row_count": rgroup_staging_fill.get("skipped_row_count"),
            "source_limits": rgroup_staging_fill.get("source_limits"),
        }
    if governed_ingestion_batches:
        coverage["governed_ingestion_batches"] = {
            "status": governed_ingestion_batches.get("status"),
            "row_count": governed_ingestion_batches.get("row_count"),
            "blocked_batch_count": governed_ingestion_batches.get("blocked_batch_count"),
            "allowed_ingestion_batch_count": governed_ingestion_batches.get("allowed_ingestion_batch_count"),
            "data_foundation_delta_required": governed_ingestion_batches.get("data_foundation_delta_required"),
            "sandbox_scoring_status": governed_ingestion_batches.get("sandbox_scoring_status"),
            "sandbox_scored_candidate_count": governed_ingestion_batches.get("sandbox_scored_candidate_count"),
            "rgroup_promotion_approval_status": governed_ingestion_batches.get("rgroup_promotion_approval_status"),
            "rgroup_promotion_approval_allowed": governed_ingestion_batches.get("rgroup_promotion_approval_allowed"),
        }
    if staged_feed_sandbox_scoring:
        coverage["staged_feed_sandbox_scoring"] = {
            "status": staged_feed_sandbox_scoring.get("status"),
            "row_count": staged_feed_sandbox_scoring.get("row_count"),
            "staged_row_count": staged_feed_sandbox_scoring.get("staged_row_count"),
            "candidate_with_staged_match_count": staged_feed_sandbox_scoring.get("candidate_with_staged_match_count"),
            "production_scoring_affected": staged_feed_sandbox_scoring.get("production_scoring_affected"),
        }
    if sandbox_score_delta_review:
        coverage["sandbox_score_delta_review_packet"] = {
            "status": sandbox_score_delta_review.get("status"),
            "row_count": sandbox_score_delta_review.get("row_count"),
            "operator_signoff_required_count": sandbox_score_delta_review.get("operator_signoff_required_count"),
            "approved_signoff_count": sandbox_score_delta_review.get("approved_signoff_count"),
            "production_scoring_approved": sandbox_score_delta_review.get("production_scoring_approved"),
            "production_scoring_affected": sandbox_score_delta_review.get("production_scoring_affected"),
        }
    if sandbox_score_delta_signoff:
        coverage["sandbox_score_delta_signoff_ledger"] = {
            "status": sandbox_score_delta_signoff.get("status"),
            "required_signoff_count": sandbox_score_delta_signoff.get("required_signoff_count"),
            "completed_signoff_count": sandbox_score_delta_signoff.get("completed_signoff_count"),
            "pending_signoff_count": sandbox_score_delta_signoff.get("pending_signoff_count"),
            "approved_count": sandbox_score_delta_signoff.get("approved_count"),
            "deferred_count": sandbox_score_delta_signoff.get("deferred_count"),
            "rejected_count": sandbox_score_delta_signoff.get("rejected_count"),
            "production_scoring_approved": sandbox_score_delta_signoff.get("production_scoring_approved"),
        }
    if rgroup_feed_digestion:
        coverage["rgroup_feed_digestion_ledger"] = {
            "status": rgroup_feed_digestion.get("status"),
            "row_count": rgroup_feed_digestion.get("row_count"),
            "accepted_count": rgroup_feed_digestion.get("accepted_count"),
            "deferred_count": rgroup_feed_digestion.get("deferred_count"),
            "rejected_count": rgroup_feed_digestion.get("rejected_count"),
            "held_out_count": rgroup_feed_digestion.get("held_out_count"),
            "production_scoring_affected": rgroup_feed_digestion.get("production_scoring_affected"),
        }
    if rgroup_promotion_approval:
        coverage["rgroup_promotion_approval_ledger"] = {
            "status": rgroup_promotion_approval.get("status"),
            "row_count": rgroup_promotion_approval.get("row_count"),
            "approval_required_count": rgroup_promotion_approval.get("approval_required_count"),
            "pending_approval_count": rgroup_promotion_approval.get("pending_approval_count"),
            "approved_count": rgroup_promotion_approval.get("approved_count"),
            "deferred_count": rgroup_promotion_approval.get("deferred_count"),
            "promotion_allowed": rgroup_promotion_approval.get("promotion_allowed"),
            "binding_blocker_count": rgroup_promotion_approval.get("binding_blocker_count"),
        }
    if rgroup_selective_approval:
        coverage["rgroup_selective_approval_batch"] = {
            "status": rgroup_selective_approval.get("status"),
            "candidate_count": rgroup_selective_approval.get("candidate_count"),
            "positive_control_approved_count": rgroup_selective_approval.get("positive_control_approved_count"),
            "holdout_count": rgroup_selective_approval.get("holdout_count"),
            "production_promotion_allowed": rgroup_selective_approval.get("production_promotion_allowed"),
        }
    if rgroup_digestion_quality_metrics:
        coverage["rgroup_digestion_quality_metrics"] = {
            "status": rgroup_digestion_quality_metrics.get("status"),
            "row_count": rgroup_digestion_quality_metrics.get("row_count"),
            "digestion_row_count": rgroup_digestion_quality_metrics.get("digestion_row_count"),
            "quality_status_counts": rgroup_digestion_quality_metrics.get("quality_status_counts"),
            "low_confidence_row_count": rgroup_digestion_quality_metrics.get("low_confidence_row_count"),
            "deferred_candidate_impact_row_count": rgroup_digestion_quality_metrics.get("deferred_candidate_impact_row_count"),
        }
    if rgroup_digestion_quality_closure:
        coverage["rgroup_digestion_quality_closure_queue"] = {
            "status": rgroup_digestion_quality_closure.get("status"),
            "row_count": rgroup_digestion_quality_closure.get("row_count"),
            "open_count": rgroup_digestion_quality_closure.get("open_count"),
            "high_count": rgroup_digestion_quality_closure.get("high_count"),
            "issue_type_counts": rgroup_digestion_quality_closure.get("issue_type_counts"),
        }
    if feed_promotion_rollback:
        coverage["feed_promotion_rollback_audit"] = {
            "status": feed_promotion_rollback.get("status"),
            "row_count": feed_promotion_rollback.get("row_count"),
            "ready_count": feed_promotion_rollback.get("ready_count"),
            "blocked_count": feed_promotion_rollback.get("blocked_count"),
            "promotion_allowed": feed_promotion_rollback.get("promotion_allowed"),
        }
    if rgroup_approval_workbench:
        coverage["rgroup_approval_workbench"] = {
            "status": rgroup_approval_workbench.get("status"),
            "row_count": rgroup_approval_workbench.get("row_count"),
            "approved_count": rgroup_approval_workbench.get("approved_count"),
            "quality_open_count": rgroup_approval_workbench.get("quality_open_count"),
            "action_bucket_counts": rgroup_approval_workbench.get("action_bucket_counts"),
        }
    if rgroup_ring_context_alignment:
        coverage["rgroup_ring_context_alignment"] = {
            "status": rgroup_ring_context_alignment.get("status"),
            "row_count": rgroup_ring_context_alignment.get("row_count"),
            "ring_replacement_count": rgroup_ring_context_alignment.get("ring_replacement_count"),
            "rgroup_replacement_count": rgroup_ring_context_alignment.get("rgroup_replacement_count"),
            "combined_review_count": rgroup_ring_context_alignment.get("combined_review_count"),
        }
    if staging_sandbox_filter_views:
        coverage["staging_sandbox_filter_views"] = {
            "status": staging_sandbox_filter_views.get("status"),
            "row_count": staging_sandbox_filter_views.get("row_count"),
            "filtered_row_total": staging_sandbox_filter_views.get("filtered_row_total"),
            "available_filters": staging_sandbox_filter_views.get("available_filters"),
        }
    if local_db_maintenance_release_gate:
        coverage["local_db_maintenance_release_gate"] = {
            "status": local_db_maintenance_release_gate.get("status"),
            "release_stop_count": local_db_maintenance_release_gate.get("release_stop_count"),
            "watch_count": local_db_maintenance_release_gate.get("watch_count"),
            "daily_alert_level": local_db_maintenance_release_gate.get("daily_alert_level"),
        }
    if native_drilldown_actions:
        coverage["native_drilldown_actions"] = {
            "status": native_drilldown_actions.get("status"),
            "row_count": native_drilldown_actions.get("row_count"),
            "route_supported_count": native_drilldown_actions.get("route_supported_count"),
            "direct_action_supported_count": native_drilldown_actions.get("direct_action_supported_count"),
            "action_type_counts": native_drilldown_actions.get("action_type_counts"),
        }
    if rgroup_pair_owner_packet:
        coverage["rgroup_pair_owner_review"] = {
            "status": rgroup_pair_owner_packet.get("status"),
            "deferred_conflict_count": rgroup_pair_owner_packet.get("deferred_conflict_count"),
            "pending_owner_review_count": rgroup_pair_owner_packet.get("pending_owner_review_count"),
            "owner_decision_recorded_count": rgroup_pair_owner_packet.get("owner_decision_recorded_count"),
            "owner_count": rgroup_pair_owner_packet.get("owner_count"),
        }
    if rgroup_pair_owner_ledger:
        coverage["rgroup_pair_owner_decision_ledger"] = {
            "status": rgroup_pair_owner_ledger.get("status"),
            "row_count": rgroup_pair_owner_ledger.get("row_count"),
            "pending_owner_review_count": rgroup_pair_owner_ledger.get("pending_owner_review_count"),
            "applied_to_pair_review_count": rgroup_pair_owner_ledger.get("applied_to_pair_review_count"),
            "decision_counts": rgroup_pair_owner_ledger.get("decision_counts"),
        }
    if ring_outcome_readiness:
        coverage["ring_outcome_production_readiness"] = {
            "status": ring_outcome_readiness.get("status"),
            "importable_result_count": ring_outcome_readiness.get("importable_result_count"),
            "pending_result_count": ring_outcome_readiness.get("pending_result_count"),
            "validation_error_count": ring_outcome_readiness.get("validation_error_count"),
        }
    if ring_outcome_result_package:
        coverage["ring_outcome_result_package"] = {
            "status": ring_outcome_result_package.get("status"),
            "result_row_count": ring_outcome_result_package.get("result_row_count"),
            "pending_result_count": ring_outcome_result_package.get("pending_result_count"),
            "importable_result_count": ring_outcome_result_package.get("importable_result_count"),
            "validation_error_count": ring_outcome_result_package.get("validation_error_count"),
        }
    if ring_outcome_holdout:
        coverage["ring_outcome_holdout"] = {
            "status": ring_outcome_holdout.get("status"),
            "endpoint_count": ring_outcome_holdout.get("endpoint_count"),
            "holdout_ready_endpoint_count": ring_outcome_holdout.get("holdout_ready_endpoint_count"),
            "active_nonzero_context_count": ring_outcome_holdout.get("active_nonzero_context_count"),
            "replay_status": ring_outcome_holdout.get("replay_status"),
        }

    warnings = []
    for asset in assets:
        if not asset["exists"]:
            warnings.append({"severity": "warning", "check": "asset_exists", "asset_id": asset["asset_id"], "message": "Asset path is missing."})
    if table_counts.get("substituent", 0) < 50:
        warnings.append({"severity": "warning", "check": "substituent_count", "message": "Governed substituent library is thin."})
    if table_counts.get("mmp_transform_evidence", 0) == 0:
        warnings.append({"severity": "warning", "check": "mmp_evidence", "message": "No public MMP evidence is loaded."})
    if table_counts.get("rgroup_replacement", 0) == 0 and table_counts.get("ring_replacement", 0) == 0:
        warnings.append({"severity": "warning", "check": "replacement_network", "message": "No replacement-network data is loaded."})
    if quality_report and not quality_report.get("ok", True):
        warnings.append({"severity": "error", "check": "quality_report", "message": "Latest data quality report is not green."})
    checkpoint = ring_import_status.get("checkpoint_integrity") or {}
    if checkpoint.get("status") == "error":
        warnings.append({"severity": "error", "check": "ring_import_checkpoint", "message": "Ring import checkpoint has integrity errors."})
    elif checkpoint.get("status") == "warning":
        warnings.append({"severity": "warning", "check": "ring_import_checkpoint", "message": "Ring import checkpoint has warnings."})
    if rgroup_feed_governance.get("status") == "error":
        warnings.append({"severity": "error", "check": "rgroup_feed_governance", "message": "R-group feed governance has allowlist errors."})
    elif rgroup_feed_governance.get("status") == "warning":
        warnings.append({"severity": "warning", "check": "rgroup_feed_governance", "message": "R-group feed governance has freshness or sample-review coverage warnings."})
    if rgroup_feed_onboarding.get("status") == "blocked":
        warnings.append({"severity": "error", "check": "rgroup_feed_onboarding", "message": "R-group feed onboarding gate is blocked."})
    if rgroup_pair_owner_ledger.get("pending_owner_review_count"):
        warnings.append({"severity": "warning", "check": "rgroup_pair_owner_decision_ledger", "message": "Deferred R-group pair conflicts still have pending source-owner decisions."})
    if rgroup_feed_staging and rgroup_feed_staging.get("status") != "staged":
        warnings.append({"severity": "warning", "check": "rgroup_feed_drop_staging", "message": "Next R-group feed-drop staging is not ready."})
    if rgroup_feed_staging_gate.get("status") == "blocked":
        warnings.append({"severity": "error", "check": "rgroup_feed_drop_staging_gate", "message": "Next R-group feed-drop staging gate is blocked."})
    if feed_absorption_audit.get("status") == "blocked" or feed_absorption_audit.get("blocker_count"):
        warnings.append({"severity": "error", "check": "feed_absorption_audit", "message": "Feed absorption audit has blocking governance issues."})
    if feed_absorption_diff.get("status") == "blocked" or feed_absorption_diff.get("blocker_count"):
        warnings.append({"severity": "error", "check": "feed_absorption_diff_navigator", "message": "Feed absorption diff navigator has blocking staged-row issues."})
    if source_expansion_governance.get("status") == "blocked" or source_expansion_governance.get("blocked_gate_count"):
        warnings.append({"severity": "error", "check": "source_expansion_governance", "message": "Source expansion governance guard has blocked gates."})
    if feed_promotion_simulator.get("status") == "blocked" or feed_promotion_simulator.get("blocker_count"):
        warnings.append({"severity": "error", "check": "feed_promotion_simulator", "message": "Feed promotion simulator has blocking staged-row issues."})
    if staging_quality_budget.get("status") == "blocked" or staging_quality_budget.get("blocker_count"):
        warnings.append({"severity": "error", "check": "rgroup_staging_quality_budget", "message": "Staging quality budget has blocking row quality or provenance issues."})
    if staging_quality_budget.get("promotion_allowed_without_sandbox_review") is True:
        warnings.append({"severity": "error", "check": "rgroup_staging_quality_budget", "message": "Staging quality budget allowed promotion without sandbox review."})
    if governed_ingestion_batches.get("status") == "blocked" or governed_ingestion_batches.get("blocked_batch_count"):
        warnings.append({"severity": "error", "check": "governed_ingestion_batches", "message": "Governed ingestion batches have blocked intake scopes."})
    if staged_feed_sandbox_scoring.get("status") == "blocked" or staged_feed_sandbox_scoring.get("production_scoring_affected") is True:
        warnings.append({"severity": "error", "check": "staged_feed_sandbox_scoring", "message": "Staged feed sandbox is blocked or affected production scoring."})
    if sandbox_score_delta_review.get("status") == "blocked" or sandbox_score_delta_review.get("production_scoring_affected") is True:
        warnings.append({"severity": "error", "check": "sandbox_score_delta_review_packet", "message": "Sandbox score-delta review is blocked or affected production scoring."})
    if sandbox_score_delta_signoff.get("status") == "blocked" or sandbox_score_delta_signoff.get("invalid_row_count") or sandbox_score_delta_signoff.get("missing_packet_row_count"):
        warnings.append({"severity": "error", "check": "sandbox_score_delta_signoff_ledger", "message": "Sandbox score-delta signoff ledger has invalid decisions or stale review IDs."})
    if sandbox_score_delta_signoff.get("pending_signoff_count"):
        warnings.append({"severity": "warning", "check": "sandbox_score_delta_signoff_ledger", "message": "Sandbox score-delta signoff ledger still has pending operator decisions."})
    if rgroup_feed_digestion.get("status") == "blocked" or rgroup_feed_digestion.get("production_scoring_affected") is True:
        warnings.append({"severity": "error", "check": "rgroup_feed_digestion_ledger", "message": "R-group feed digestion ledger is blocked or affected production scoring."})
    if rgroup_promotion_approval.get("status") == "blocked" or rgroup_promotion_approval.get("binding_blocker_count"):
        warnings.append({"severity": "error", "check": "rgroup_promotion_approval_ledger", "message": "R-group promotion approval ledger has stale bindings or blocked approval rows."})
    if rgroup_promotion_approval.get("pending_approval_count"):
        warnings.append({"severity": "warning", "check": "rgroup_promotion_approval_ledger", "message": "R-group promotion approval ledger still has pending row decisions."})
    if rgroup_selective_approval.get("status") == "blocked" or rgroup_selective_approval.get("production_promotion_allowed") is True:
        warnings.append({"severity": "error", "check": "rgroup_selective_approval_batch", "message": "Selective approval batch is blocked or unexpectedly allowed production promotion."})
    if rgroup_digestion_quality_metrics.get("status") == "blocked":
        warnings.append({"severity": "error", "check": "rgroup_digestion_quality_metrics", "message": "R-group digestion quality metrics have release-blocking completeness gaps."})
    if rgroup_digestion_quality_closure and rgroup_digestion_quality_closure.get("status") not in {"ready", "awaiting_metrics"}:
        warnings.append({"severity": "warning", "check": "rgroup_digestion_quality_closure_queue", "message": "R-group digestion quality closure queue is not ready."})
    if feed_promotion_rollback.get("status") == "blocked" or feed_promotion_rollback.get("blocked_count"):
        warnings.append({"severity": "error", "check": "feed_promotion_rollback_audit", "message": "Feed promotion rollback audit has missing replay checkpoints."})
    if rgroup_approval_workbench and rgroup_approval_workbench.get("status") not in {"ready", "awaiting_rows"}:
        warnings.append({"severity": "warning", "check": "rgroup_approval_workbench", "message": "R-group approval workbench is not ready."})
    if rgroup_ring_context_alignment and rgroup_ring_context_alignment.get("status") not in {"ready", "awaiting_rows"}:
        warnings.append({"severity": "warning", "check": "rgroup_ring_context_alignment", "message": "R-group ring-context alignment is not ready."})
    if staging_sandbox_filter_views and staging_sandbox_filter_views.get("status") not in {"ready", "empty"}:
        warnings.append({"severity": "warning", "check": "staging_sandbox_filter_views", "message": "Staging/sandbox filter views are not ready."})
    if local_db_maintenance_release_gate.get("release_stop_count"):
        warnings.append({"severity": "error", "check": "local_db_maintenance_release_gate", "message": "Local DB maintenance has release-stop rows."})
    if ring_outcome_readiness.get("validation_error_count"):
        warnings.append({"severity": "error", "check": "ring_outcome_production_readiness", "message": "Ring outcome result intake has validation errors."})
    if ring_outcome_result_package.get("status") == "blocked_by_validation":
        warnings.append({"severity": "error", "check": "ring_outcome_result_package", "message": "Ring outcome production result package has validation errors."})
    if ring_outcome_holdout.get("status") == "holdout_review_required":
        warnings.append({"severity": "warning", "check": "ring_outcome_holdout", "message": "Ring outcome holdout requires endpoint review before nonzero activation."})

    record_count = sum(table_counts.get(table, 0) for table in CORE_RECORD_TABLES)
    drift_thresholds = _load_drift_thresholds(root_path)
    source_acceptance_manifest = _load_source_acceptance_manifest(root_path)
    active_acceptances = [
        item
        for item in source_acceptance_manifest.get("accepted_changes", []) or source_acceptance_manifest.get("acceptances", []) or []
        if _parse_manifest_datetime(item.get("expires_at")) is None or _parse_manifest_datetime(item.get("expires_at")) >= datetime.now(timezone.utc)
    ]
    report = {
        "snapshot_id": f"DF-{created_at.replace(':', '').replace('-', '').replace('.', '')}",
        "created_at": created_at,
        "root": str(root_path),
        "db_path": str(db_file.resolve()),
        "assets": assets,
        "table_counts": table_counts,
        "source_breakdown": source_breakdown,
        "review_status_counts": review_status_counts,
        "coverage": coverage,
        "rgroup_feed_governance": rgroup_feed_governance,
        "assay_event_triage": assay_event_triage,
        "release_drift": _release_manifest_drift(root_path),
        "quality_gate": {
            "quality_report_ok": quality_report.get("ok"),
            "quality_error_count": quality_report.get("error_count"),
            "quality_warning_count": quality_report.get("warning_count"),
            "ci_report_ok": ci_report.get("ok"),
            "ci_bundle_path": (ci_report.get("bundle") or {}).get("bundle_path") if ci_report else None,
        },
        "import_state": {
            "ring_import_state": ring_import_state,
            "latest_ertl_chunk_import": chunk_report,
            "ring_import_status": ring_import_status,
        },
        "totals": {
            "record_count": record_count,
            "asset_count": len(assets),
            "missing_asset_count": sum(1 for asset in assets if not asset["exists"]),
            "warning_count": len(warnings),
        },
        "warnings": warnings,
        "recommended_next_actions": _recommendations(table_counts, review_status_counts, warnings),
        "source_acceptance_manifest": {
            "version": source_acceptance_manifest.get("version"),
            "accepted_change_count": len(source_acceptance_manifest.get("accepted_changes", []) or source_acceptance_manifest.get("acceptances", []) or []),
            "active_acceptance_count": len(active_acceptances),
        },
    }
    report["data_drift"] = evaluate_data_drift(report, previous_snapshot, drift_thresholds, source_acceptance_manifest)
    report["ci_gate"] = evaluate_data_foundation_gate(report)
    report["data_currency"] = data_currency_badge(report)
    return report


def render_data_foundation_markdown(report: dict) -> str:
    def pct(value: object) -> str:
        if value in {None, ""}:
            return ""
        try:
            return f"{float(value) * 100:.1f}%"
        except (TypeError, ValueError):
            return str(value)

    lines = [
        "# Data Foundation Snapshot",
        "",
        f"- Snapshot: `{report.get('snapshot_id')}`",
        f"- Created at: `{report.get('created_at')}`",
        f"- Core record count: `{report.get('totals', {}).get('record_count')}`",
        f"- Missing assets: `{report.get('totals', {}).get('missing_asset_count')}`",
        "",
        "## Core Tables",
        "",
        "| Table | Count |",
        "| --- | ---: |",
    ]
    for table, count in sorted((report.get("table_counts") or {}).items()):
        lines.append(f"| `{table}` | {count} |")
    lines.extend(["", "## Assets", "", "| Asset | Category | Exists | Records |", "| --- | --- | ---: | ---: |"])
    table_counts = report.get("table_counts") or {}
    for asset in report.get("assets") or []:
        records = table_counts.get(asset.get("db_table"), "")
        lines.append(f"| `{asset.get('asset_id')}` | {asset.get('category')} | {asset.get('exists')} | {records} |")
    lines.extend(["", "## Coverage Highlights", ""])
    coverage = report.get("coverage") or {}
    for key in ["site_compatibility", "experiment_plan_status", "experiment_result_status", "route_batch_status"]:
        rows = coverage.get(key) or []
        if rows:
            values = ", ".join(":".join(str(value) for value in row.values()) for row in rows[:8])
            lines.append(f"- `{key}`: {values}")
    feed_governance = report.get("rgroup_feed_governance") or {}
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
                "| Feed | Rows | Delta | Provenance | Allowlist | Freshness |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in feed_governance.get("per_feed") or []:
            lines.append(
                "| "
                f"`{row.get('feed_name')}` | "
                f"{row.get('row_count')} | "
                f"{row.get('row_count_delta')} | "
                f"{pct(row.get('provenance_complete_fraction'))} | "
                f"{row.get('allowlist_issue_count')} | "
                f"{row.get('freshness_issue_count')} |"
            )
    drift = report.get("release_drift") or {}
    if drift.get("available"):
        lines.extend(
            [
                "",
                "## Release Drift",
                "",
                f"- Added: `{drift.get('added_count')}`",
                f"- Changed: `{drift.get('changed_count')}`",
                f"- Removed: `{drift.get('removed_count')}`",
                f"- Risk level: `{drift.get('risk_level')}`",
            ]
        )
    ci_gate = report.get("ci_gate") or {}
    if ci_gate:
        lines.extend(
            [
                "",
                "## CI Gate",
                "",
                f"- Status: `{ci_gate.get('status')}`",
                f"- Passed: `{ci_gate.get('passed')}`",
                f"- Errors: `{ci_gate.get('error_count')}`",
                f"- Warnings: `{ci_gate.get('warning_count')}`",
            ]
        )
    data_drift = report.get("data_drift") or {}
    if data_drift:
        lines.extend(
            [
                "",
                "## Data Drift",
                "",
                f"- Status: `{data_drift.get('status')}`",
                f"- Errors: `{data_drift.get('error_count')}`",
                f"- Warnings: `{data_drift.get('warning_count')}`",
                f"- Accepted issues: `{data_drift.get('accepted_issue_count', 0)}`",
                f"- Acceptance manifest: `{data_drift.get('acceptance_manifest_version')}`",
                f"- Previous snapshot: `{data_drift.get('previous_snapshot_id')}`",
            ]
        )
    ring_status = ((report.get("import_state") or {}).get("ring_import_status") or {})
    if ring_status:
        checkpoint = ring_status.get("checkpoint_integrity") or {}
        lines.extend(
            [
                "",
                "## Ring Import Observability",
                "",
                f"- Status: `{ring_status.get('status')}`",
                f"- Progress: `{ring_status.get('progress_percent')}`%",
                f"- Next offset: `{ring_status.get('next_offset')}`",
                f"- Throughput: `{ring_status.get('last_throughput_rings_per_second')}` rings/s",
                f"- Checkpoint integrity: `{checkpoint.get('status')}`",
            ]
        )
    lines.extend(["", "## Recommended Next Actions", ""])
    for item in report.get("recommended_next_actions") or []:
        lines.append(f"- {item}")
    if report.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        for warning in report["warnings"]:
            lines.append(f"- `{warning.get('check')}`: {warning.get('message')}")
    lines.append("")
    return "\n".join(lines)


def save_data_foundation_report(
    report: dict,
    *,
    json_path: str | Path,
    markdown_path: str | Path | None = None,
    db_path: str | Path | None = None,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if markdown_path is not None:
        md_file = Path(markdown_path)
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(render_data_foundation_markdown(report), encoding="utf-8")
    if db_path is not None:
        conn = initialize_database(db_path)
        try:
            insert_data_foundation_snapshot(conn, report)
        finally:
            conn.close()
