from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .library import ensure_list


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS substituent (
    substituent_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    short_name TEXT,
    smiles TEXT NOT NULL,
    canonical_smiles TEXT,
    connection_type TEXT,
    attachment_count INTEGER,
    is_active INTEGER DEFAULT 1,
    is_mvp INTEGER DEFAULT 0,
    common_medchem INTEGER DEFAULT 0,
    default_rank INTEGER DEFAULT 999,
    source_type TEXT,
    source_reference TEXT,
    version TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS substituent_descriptor (
    substituent_id TEXT PRIMARY KEY,
    fragment_mw REAL,
    exact_mw REAL,
    clogp REAL,
    tpsa REAL,
    hbd INTEGER,
    hba INTEGER,
    rotatable_bonds INTEGER,
    heavy_atom_count INTEGER,
    ring_count INTEGER,
    aromatic_ring_count INTEGER,
    formal_charge INTEGER,
    fsp3 REAL,
    qed REAL,
    FOREIGN KEY(substituent_id) REFERENCES substituent(substituent_id)
);

CREATE TABLE IF NOT EXISTS substituent_tag (
    substituent_id TEXT,
    tag_type TEXT,
    tag_value TEXT,
    FOREIGN KEY(substituent_id) REFERENCES substituent(substituent_id)
);

CREATE TABLE IF NOT EXISTS substituent_site_compatibility (
    substituent_id TEXT,
    site_type TEXT,
    compatibility_level TEXT,
    note TEXT,
    FOREIGN KEY(substituent_id) REFERENCES substituent(substituent_id)
);

CREATE TABLE IF NOT EXISTS substituent_warning (
    substituent_id TEXT,
    warning_type TEXT,
    warning_text TEXT,
    severity TEXT,
    FOREIGN KEY(substituent_id) REFERENCES substituent(substituent_id)
);

CREATE TABLE IF NOT EXISTS source_metadata (
    substituent_id TEXT PRIMARY KEY,
    source_name TEXT,
    query TEXT,
    payload_json TEXT,
    fetched_at TEXT,
    FOREIGN KEY(substituent_id) REFERENCES substituent(substituent_id)
);

CREATE TABLE IF NOT EXISTS substituent_review (
    substituent_id TEXT PRIMARY KEY,
    review_status TEXT,
    reviewed_by TEXT,
    reviewed_at TEXT,
    review_notes TEXT,
    use_cases TEXT,
    avoid_contexts TEXT,
    FOREIGN KEY(substituent_id) REFERENCES substituent(substituent_id)
);

CREATE TABLE IF NOT EXISTS substituent_version_log (
    substituent_id TEXT,
    version TEXT,
    change_date TEXT,
    change_type TEXT,
    summary TEXT,
    FOREIGN KEY(substituent_id) REFERENCES substituent(substituent_id)
);

CREATE TABLE IF NOT EXISTS substituent_quality_issue (
    substituent_id TEXT,
    name TEXT,
    severity TEXT,
    category TEXT,
    field TEXT,
    value TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS raw_source_record (
    raw_record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT,
    source_record_id TEXT,
    source_url TEXT,
    fetched_at TEXT,
    status_code INTEGER,
    payload_sha256 TEXT,
    payload_json TEXT,
    ingest_batch TEXT
);

CREATE TABLE IF NOT EXISTS candidate_substituent (
    candidate_id TEXT PRIMARY KEY,
    source_name TEXT,
    source_record_id TEXT,
    name TEXT,
    smiles TEXT,
    canonical_smiles TEXT,
    proposed_substituent_smiles TEXT,
    candidate_status TEXT,
    review_tier TEXT,
    payload_json TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS candidate_promotion (
    candidate_id TEXT,
    substituent_id TEXT,
    promotion_status TEXT,
    promoted_at TEXT,
    notes TEXT,
    PRIMARY KEY(candidate_id, substituent_id),
    FOREIGN KEY(substituent_id) REFERENCES substituent(substituent_id)
);

CREATE TABLE IF NOT EXISTS substituent_vendor_overlay (
    substituent_id TEXT PRIMARY KEY,
    availability_tier TEXT,
    price_tier TEXT,
    lead_time_days INTEGER,
    route_confidence REAL,
    source TEXT,
    updated_at TEXT,
    notes TEXT,
    payload_json TEXT,
    FOREIGN KEY(substituent_id) REFERENCES substituent(substituent_id)
);

CREATE TABLE IF NOT EXISTS mmp_transform_evidence (
    transform_id TEXT PRIMARY KEY,
    variable_from_smiles TEXT,
    variable_to_smiles TEXT,
    pair_count INTEGER,
    core_count INTEGER,
    example_count INTEGER,
    mean_delta_fragment_mw REAL,
    mean_delta_clogp REAL,
    mean_delta_tpsa REAL,
    source_name TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS transform_mmp_mapping (
    mapping_id TEXT PRIMARY KEY,
    rule_id TEXT,
    transform_id TEXT,
    replacement_label TEXT,
    match_type TEXT,
    pair_count INTEGER,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS chembl_activity_evidence (
    evidence_id TEXT PRIMARY KEY,
    molecule_chembl_id TEXT,
    target_chembl_id TEXT,
    target_pref_name TEXT,
    target_type TEXT,
    target_organism TEXT,
    target_family TEXT,
    target_family_normalized TEXT,
    target_family_label TEXT,
    target_family_weight REAL,
    standard_type TEXT,
    standard_relation TEXT,
    standard_value REAL,
    standard_units TEXT,
    pchembl_value REAL,
    assay_chembl_id TEXT,
    document_chembl_id TEXT,
    source_name TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS transform_activity_summary (
    summary_id TEXT PRIMARY KEY,
    mapping_id TEXT,
    rule_id TEXT,
    transform_id TEXT,
    replacement_label TEXT,
    orientation TEXT,
    from_molecule_count INTEGER,
    to_molecule_count INTEGER,
    target_summary_count INTEGER,
    target_family_summary_count INTEGER,
    activity_cliff_count INTEGER,
    mean_delta_pchembl REAL,
    mean_family_delta_pchembl REAL,
    max_abs_delta_pchembl REAL,
    activity_cliff_risk TEXT,
    rule_activity_judgment TEXT,
    rule_activity_judgment_note TEXT,
    replicate_count INTEGER,
    assay_confidence TEXT,
    assay_confidence_score REAL,
    uncertainty_score REAL,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS ring_system (
    ring_id TEXT PRIMARY KEY,
    smiles TEXT NOT NULL,
    canonical_smiles TEXT NOT NULL,
    source_name TEXT,
    source_dataset TEXT,
    source_rank INTEGER,
    ring_class TEXT,
    ring_count INTEGER,
    hetero_atom_count INTEGER,
    aromatic_ring_count INTEGER,
    heavy_atom_count INTEGER,
    fsp3 REAL,
    source_reference TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS literature_substituent (
    literature_substituent_id TEXT PRIMARY KEY,
    smiles TEXT NOT NULL,
    canonical_smiles TEXT NOT NULL,
    source_name TEXT,
    source_dataset TEXT,
    source_rank INTEGER,
    substituent_class TEXT,
    fragment_mw REAL,
    clogp REAL,
    tpsa REAL,
    hbd INTEGER,
    hba INTEGER,
    heavy_atom_count INTEGER,
    source_reference TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS ring_replacement (
    replacement_id TEXT PRIMARY KEY,
    query_smiles TEXT,
    replacement_smiles TEXT,
    query_canonical_smiles TEXT,
    replacement_canonical_smiles TEXT,
    activity_delta REAL,
    evidence_count INTEGER,
    source_name TEXT,
    source_reference TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS rgroup_replacement (
    replacement_id TEXT PRIMARY KEY,
    source_smiles TEXT,
    target_smiles TEXT,
    source_canonical_smiles TEXT,
    target_canonical_smiles TEXT,
    normalized_source_smiles TEXT,
    normalized_target_smiles TEXT,
    normalized_pair_key TEXT,
    edge_weight INTEGER,
    source_record_count INTEGER DEFAULT 1,
    aggregate_edge_weight INTEGER,
    source_replacement_ids TEXT,
    layer TEXT,
    center_smiles TEXT,
    source_name TEXT,
    source_reference TEXT,
    source_confidence_tier TEXT,
    source_confidence_score REAL,
    source_confidence_basis TEXT,
    row_sha256 TEXT,
    source_owner TEXT,
    source_license TEXT,
    provenance_level TEXT,
    provenance_review_status TEXT,
    provenance_note TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS rgroup_replacement_normalized (
    normalized_pair_key TEXT PRIMARY KEY,
    normalized_source_smiles TEXT,
    normalized_target_smiles TEXT,
    representative_replacement_id TEXT,
    source_record_count INTEGER,
    aggregate_edge_weight INTEGER,
    max_edge_weight INTEGER,
    layers TEXT,
    source_names TEXT,
    source_references TEXT,
    source_confidence_tiers TEXT,
    max_source_confidence_score REAL,
    source_replacement_ids TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS scaffold_replacement (
    scaffold_rule_id TEXT PRIMARY KEY,
    name TEXT,
    from_smarts TEXT,
    to_smiles TEXT,
    attachment_count INTEGER,
    replacement_class TEXT,
    source_name TEXT,
    source_reference TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS scaffold_rule_review_event (
    event_id TEXT PRIMARY KEY,
    scaffold_rule_id TEXT,
    status TEXT,
    reviewer TEXT,
    score_adjustment REAL,
    note TEXT,
    created_at TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS transform_rule_quality_issue (
    rule_id TEXT,
    name TEXT,
    severity TEXT,
    category TEXT,
    field TEXT,
    value TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS build_manifest (
    manifest_id TEXT PRIMARY KEY,
    created_at TEXT,
    payload_sha256 TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS data_foundation_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    created_at TEXT,
    asset_count INTEGER,
    total_record_count INTEGER,
    warning_count INTEGER,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS api_health_check (
    check_id TEXT PRIMARY KEY,
    source_name TEXT,
    endpoint_url TEXT,
    checked_at TEXT,
    ok INTEGER,
    status_code INTEGER,
    latency_ms REAL,
    error TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS project_run (
    run_id TEXT PRIMARY KEY,
    project_name TEXT,
    parent_smiles TEXT,
    direction TEXT,
    site_id TEXT,
    site_type TEXT,
    filters_json TEXT,
    score_weights_json TEXT,
    scoring_profile_id TEXT,
    scoring_profile_path TEXT,
    calibration_id TEXT,
    calibration_endpoint_group TEXT,
    calibration_created_at TEXT,
    model_context_json TEXT,
    analysis_json TEXT,
    note TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS project_candidate (
    run_id TEXT,
    candidate_id TEXT,
    smiles TEXT,
    rank INTEGER,
    score REAL,
    cluster_id TEXT,
    cluster_representative INTEGER DEFAULT 0,
    enumeration_type TEXT,
    replacement_label TEXT,
    decision_status TEXT DEFAULT 'unreviewed',
    note TEXT,
    payload_json TEXT,
    PRIMARY KEY(run_id, candidate_id),
    FOREIGN KEY(run_id) REFERENCES project_run(run_id)
);

CREATE TABLE IF NOT EXISTS project_feedback (
    feedback_id TEXT PRIMARY KEY,
    run_id TEXT,
    candidate_id TEXT,
    project_name TEXT,
    assay_name TEXT,
    assay_type TEXT,
    endpoint TEXT,
    value REAL,
    unit TEXT,
    relation TEXT,
    higher_is_better INTEGER DEFAULT 0,
    normalized_score REAL,
    classification TEXT,
    source_path TEXT,
    note TEXT,
    recorded_at TEXT,
    payload_json TEXT,
    FOREIGN KEY(run_id, candidate_id) REFERENCES project_candidate(run_id, candidate_id)
);

CREATE TABLE IF NOT EXISTS project_model_calibration (
    calibration_id TEXT,
    project_name TEXT,
    endpoint_group TEXT,
    feedback_count INTEGER,
    candidate_count INTEGER,
    score_weights_json TEXT,
    property_windows_json TEXT,
    metrics_json TEXT,
    payload_json TEXT,
    created_at TEXT,
    PRIMARY KEY(calibration_id, endpoint_group)
);

CREATE TABLE IF NOT EXISTS project_route_batch (
    run_id TEXT,
    route_batch_id TEXT,
    batch_type TEXT,
    procurement_bucket TEXT,
    reaction_family TEXT,
    suggested_building_block TEXT,
    route_template_id TEXT,
    candidate_count INTEGER,
    top_score REAL,
    mean_lead_time_days REAL,
    mean_route_confidence REAL,
    route_risk_flags TEXT,
    chemist_approval_status TEXT DEFAULT 'needs_chemist_review',
    approval_note TEXT,
    approval_updated_at TEXT,
    reagent_overlap_score REAL,
    protecting_group_risk TEXT,
    regioselectivity_risk TEXT,
    purification_risk TEXT,
    route_execution_risk_score REAL,
    execution_json TEXT,
    payload_json TEXT,
    PRIMARY KEY(run_id, route_batch_id),
    FOREIGN KEY(run_id) REFERENCES project_run(run_id)
);

CREATE TABLE IF NOT EXISTS route_batch_status_event (
    event_id TEXT PRIMARY KEY,
    run_id TEXT,
    route_batch_id TEXT,
    status TEXT,
    note TEXT,
    created_at TEXT,
    payload_json TEXT,
    FOREIGN KEY(run_id, route_batch_id) REFERENCES project_route_batch(run_id, route_batch_id)
);

CREATE TABLE IF NOT EXISTS route_quote_request (
    quote_request_id TEXT PRIMARY KEY,
    run_id TEXT,
    route_batch_id TEXT,
    vendor_name TEXT,
    request_status TEXT,
    catalog_urls TEXT,
    reagent_overlap_score REAL,
    protecting_group_risk TEXT,
    regioselectivity_risk TEXT,
    purification_risk TEXT,
    route_execution_risk_score REAL,
    created_at TEXT,
    updated_at TEXT,
    payload_json TEXT,
    FOREIGN KEY(run_id, route_batch_id) REFERENCES project_route_batch(run_id, route_batch_id)
);

CREATE TABLE IF NOT EXISTS project_feedback_control (
    control_id TEXT PRIMARY KEY,
    project_name TEXT,
    created_at TEXT,
    endpoint_count INTEGER,
    uncertainty_flag_count INTEGER,
    drift_flag_count INTEGER,
    recommendation_count INTEGER,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS project_experiment_plan (
    plan_id TEXT PRIMARY KEY,
    project_name TEXT,
    run_id TEXT,
    candidate_id TEXT,
    plan_rank INTEGER,
    plan_role TEXT,
    endpoint_group TEXT,
    site_type TEXT,
    direction TEXT,
    enumeration_type TEXT,
    replacement_label TEXT,
    candidate_score REAL,
    priority_score REAL,
    rationale TEXT,
    owner TEXT,
    planned_assay TEXT,
    status TEXT DEFAULT 'planned',
    last_stop_go_decision TEXT,
    last_assay_confidence TEXT,
    last_assay_confidence_score REAL,
    last_retest_reason TEXT,
    source_path TEXT,
    created_at TEXT,
    updated_at TEXT,
    notes TEXT,
    payload_json TEXT,
    FOREIGN KEY(run_id, candidate_id) REFERENCES project_candidate(run_id, candidate_id)
);

CREATE TABLE IF NOT EXISTS project_experiment_event (
    event_id TEXT PRIMARY KEY,
    plan_id TEXT,
    run_id TEXT,
    candidate_id TEXT,
    status TEXT,
    endpoint_group TEXT,
    assay_name TEXT,
    assay_type TEXT,
    value REAL,
    unit TEXT,
    relation TEXT,
    higher_is_better INTEGER DEFAULT 0,
    normalized_score REAL,
    classification TEXT,
    replicate_count INTEGER,
    replicate_cv REAL,
    assay_confidence TEXT,
    assay_confidence_score REAL,
    stop_go_decision TEXT,
    retest_reason TEXT,
    source_path TEXT,
    note TEXT,
    recorded_at TEXT,
    payload_json TEXT,
    FOREIGN KEY(plan_id) REFERENCES project_experiment_plan(plan_id)
);

CREATE TABLE IF NOT EXISTS project_decision_packet (
    packet_id TEXT PRIMARY KEY,
    project_name TEXT,
    source_run_id TEXT,
    parent_smiles TEXT,
    direction TEXT,
    site_type TEXT,
    status TEXT DEFAULT 'needs_review',
    reviewer TEXT,
    review_note TEXT,
    candidate_count INTEGER,
    decision_counts_json TEXT,
    payload_json TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS project_decision_packet_event (
    event_id TEXT PRIMARY KEY,
    packet_id TEXT,
    status TEXT,
    reviewer TEXT,
    note TEXT,
    created_at TEXT,
    payload_json TEXT,
    FOREIGN KEY(packet_id) REFERENCES project_decision_packet(packet_id)
);

CREATE TABLE IF NOT EXISTS next_design_queue_decision_event (
    event_id TEXT PRIMARY KEY,
    queue_decision_key TEXT,
    queue_id TEXT,
    project_name TEXT,
    run_id TEXT,
    candidate_id TEXT,
    endpoint_group TEXT,
    queue_decision TEXT,
    owner TEXT,
    review_note TEXT,
    reviewed_at TEXT,
    source_path TEXT,
    created_at TEXT,
    payload_json TEXT
);

""" 


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for column, definition in columns.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _run_light_migrations(conn: sqlite3.Connection) -> None:
    _ensure_columns(
        conn,
        "chembl_activity_evidence",
        {
            "target_pref_name": "TEXT",
            "target_type": "TEXT",
            "target_organism": "TEXT",
            "target_family": "TEXT",
            "target_family_normalized": "TEXT",
            "target_family_label": "TEXT",
            "target_family_weight": "REAL",
            "assay_chembl_id": "TEXT",
            "document_chembl_id": "TEXT",
        },
    )
    _ensure_columns(
        conn,
        "transform_activity_summary",
        {
            "target_family_summary_count": "INTEGER",
            "mean_family_delta_pchembl": "REAL",
            "rule_activity_judgment": "TEXT",
            "rule_activity_judgment_note": "TEXT",
            "replicate_count": "INTEGER",
            "assay_confidence": "TEXT",
            "assay_confidence_score": "REAL",
            "uncertainty_score": "REAL",
        },
    )
    _ensure_columns(
        conn,
        "project_run",
        {
            "scoring_profile_id": "TEXT",
            "scoring_profile_path": "TEXT",
            "calibration_id": "TEXT",
            "calibration_endpoint_group": "TEXT",
            "calibration_created_at": "TEXT",
            "model_context_json": "TEXT",
        },
    )
    _ensure_columns(
        conn,
        "project_route_batch",
        {
            "reagent_overlap_score": "REAL",
            "protecting_group_risk": "TEXT",
            "regioselectivity_risk": "TEXT",
            "purification_risk": "TEXT",
            "route_execution_risk_score": "REAL",
        },
    )
    _ensure_columns(
        conn,
        "project_experiment_plan",
        {
            "last_stop_go_decision": "TEXT",
            "last_assay_confidence": "TEXT",
            "last_assay_confidence_score": "REAL",
            "last_retest_reason": "TEXT",
        },
    )
    _ensure_columns(
        conn,
        "project_experiment_event",
        {
            "replicate_count": "INTEGER",
            "replicate_cv": "REAL",
            "assay_confidence": "TEXT",
            "assay_confidence_score": "REAL",
            "stop_go_decision": "TEXT",
            "retest_reason": "TEXT",
        },
    )
    _ensure_columns(
        conn,
        "rgroup_replacement",
        {
            "normalized_source_smiles": "TEXT",
            "normalized_target_smiles": "TEXT",
            "normalized_pair_key": "TEXT",
            "source_record_count": "INTEGER DEFAULT 1",
            "aggregate_edge_weight": "INTEGER",
            "source_replacement_ids": "TEXT",
            "source_confidence_tier": "TEXT",
            "source_confidence_score": "REAL",
            "source_confidence_basis": "TEXT",
            "row_sha256": "TEXT",
            "source_owner": "TEXT",
            "source_license": "TEXT",
            "provenance_level": "TEXT",
            "provenance_review_status": "TEXT",
            "provenance_note": "TEXT",
        },
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rgroup_replacement_normalized (
            normalized_pair_key TEXT PRIMARY KEY,
            normalized_source_smiles TEXT,
            normalized_target_smiles TEXT,
            representative_replacement_id TEXT,
            source_record_count INTEGER,
            aggregate_edge_weight INTEGER,
            max_edge_weight INTEGER,
            layers TEXT,
            source_names TEXT,
            source_references TEXT,
            source_confidence_tiers TEXT,
            max_source_confidence_score REAL,
            source_replacement_ids TEXT,
            payload_json TEXT
        )
        """
    )
    _ensure_columns(
        conn,
        "rgroup_replacement_normalized",
        {
            "source_confidence_tiers": "TEXT",
            "max_source_confidence_score": "REAL",
        },
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scaffold_rule_review_event (
            event_id TEXT PRIMARY KEY,
            scaffold_rule_id TEXT,
            status TEXT,
            reviewer TEXT,
            score_adjustment REAL,
            note TEXT,
            created_at TEXT,
            payload_json TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ring_system_canonical ON ring_system(canonical_smiles)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ring_system_class ON ring_system(ring_class)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ring_system_dataset ON ring_system(source_dataset)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ring_system_dataset_rank ON ring_system(source_dataset, source_rank)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ring_system_dataset_class_heavy ON ring_system(source_dataset, ring_class, heavy_atom_count)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ring_system_dataset_class_rank ON ring_system(source_dataset, ring_class, source_rank)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ring_system_heavy_atoms ON ring_system(heavy_atom_count)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rgroup_normalized_pair ON rgroup_replacement(normalized_pair_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rgroup_normalized_source ON rgroup_replacement_normalized(normalized_source_smiles)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rgroup_normalized_target ON rgroup_replacement_normalized(normalized_target_smiles)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scaffold_rule_review_event_rule ON scaffold_rule_review_event(scaffold_rule_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_target_family ON chembl_activity_evidence(target_family)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_transform_activity_rule ON transform_activity_summary(rule_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_experiment_plan_run ON project_experiment_plan(run_id, candidate_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_experiment_plan_status ON project_experiment_plan(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_experiment_event_plan ON project_experiment_event(plan_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_experiment_event_decision ON project_experiment_event(stop_go_decision)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_decision_packet_project ON project_decision_packet(project_name, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_decision_packet_status ON project_decision_packet(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_next_queue_decision_candidate ON next_design_queue_decision_event(project_name, run_id, candidate_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_next_queue_decision_status ON next_design_queue_decision_event(queue_decision, created_at)")
    conn.commit()


def initialize_database(path: str | Path | sqlite3.Connection) -> sqlite3.Connection:
    if isinstance(path, sqlite3.Connection):
        conn = path
        conn.execute("PRAGMA busy_timeout=60000")
        conn.executescript(SCHEMA)
        _run_light_migrations(conn)
        return conn
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")
    conn.executescript(SCHEMA)
    _run_light_migrations(conn)
    return conn


def reset_library_tables(conn: sqlite3.Connection, preserve_tables: set[str] | None = None) -> None:
    preserve_tables = preserve_tables or set()
    tables = [
        "build_manifest",
        "transform_rule_quality_issue",
        "transform_activity_summary",
        "rgroup_replacement_normalized",
        "rgroup_replacement",
        "ring_replacement",
        "scaffold_replacement",
        "literature_substituent",
        "ring_system",
        "chembl_activity_evidence",
        "transform_mmp_mapping",
        "mmp_transform_evidence",
        "substituent_vendor_overlay",
        "candidate_promotion",
        "candidate_substituent",
        "substituent_quality_issue",
        "substituent_version_log",
        "substituent_review",
        "source_metadata",
        "substituent_warning",
        "substituent_site_compatibility",
        "substituent_tag",
        "substituent_descriptor",
        "substituent",
    ]
    for table in tables:
        if table in preserve_tables:
            continue
        conn.execute(f"DELETE FROM {table}")
    conn.commit()


def update_candidate_status(
    conn: sqlite3.Connection,
    candidate_id: str,
    candidate_status: str,
    review_tier: str | None = None,
) -> None:
    if review_tier is None:
        conn.execute(
            "UPDATE candidate_substituent SET candidate_status = ? WHERE candidate_id = ?",
            (candidate_status, candidate_id),
        )
    else:
        conn.execute(
            "UPDATE candidate_substituent SET candidate_status = ?, review_tier = ? WHERE candidate_id = ?",
            (candidate_status, review_tier, candidate_id),
        )
    conn.commit()


def record_candidate_promotion(
    conn: sqlite3.Connection,
    candidate_id: str,
    substituent_id: str,
    promotion_status: str = "promoted",
    notes: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT OR REPLACE INTO candidate_promotion (
            candidate_id, substituent_id, promotion_status, promoted_at, notes
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            candidate_id,
            substituent_id,
            promotion_status,
            now,
            notes or "Candidate reviewed through promotion workflow.",
        ),
    )
    conn.commit()


def insert_quality_issues(conn: sqlite3.Connection, issues: list[dict]) -> None:
    for item in issues:
        conn.execute(
            """
            INSERT INTO substituent_quality_issue (
                substituent_id, name, severity, category, field, value, message
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.get("substituent_id"),
                item.get("name"),
                item.get("severity"),
                item.get("category"),
                item.get("field"),
                item.get("value"),
                item.get("message"),
            ),
        )
    conn.commit()


def insert_raw_source_records(conn: sqlite3.Connection, records: list[dict]) -> None:
    for item in records:
        conn.execute(
            """
            INSERT INTO raw_source_record (
                source_name, source_record_id, source_url, fetched_at, status_code,
                payload_sha256, payload_json, ingest_batch
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.get("source_name"),
                item.get("source_record_id"),
                item.get("source_url"),
                item.get("fetched_at"),
                item.get("status_code"),
                item.get("payload_sha256"),
                json.dumps(item.get("payload"), sort_keys=True),
                item.get("ingest_batch"),
            ),
        )
    conn.commit()


def insert_candidate_substituents(conn: sqlite3.Connection, candidates: list[dict]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for item in candidates:
        conn.execute(
            """
            INSERT OR REPLACE INTO candidate_substituent (
                candidate_id, source_name, source_record_id, name, smiles,
                canonical_smiles, proposed_substituent_smiles, candidate_status,
                review_tier, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.get("candidate_id"),
                item.get("source_name"),
                item.get("source_record_id"),
                item.get("name"),
                item.get("smiles"),
                item.get("canonical_smiles"),
                item.get("proposed_substituent_smiles") or item.get("smiles"),
                item.get("candidate_status", "staged"),
                item.get("review_tier", "needs_medchem_review"),
                json.dumps(item, sort_keys=True),
                item.get("created_at") or now,
            ),
        )
    conn.commit()


def insert_candidate_promotions(conn: sqlite3.Connection, records: list[dict]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for record in records:
        source = record.get("source") or {}
        candidate_id = source.get("candidate_id")
        if not candidate_id:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO candidate_promotion (
                candidate_id, substituent_id, promotion_status, promoted_at, notes
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                candidate_id,
                record.get("substituent_id"),
                "promoted",
                now,
                source.get("promotion_note") or "Promoted by governed library build.",
            ),
        )
    conn.commit()


def insert_transform_quality_issues(conn: sqlite3.Connection, issues: list[dict]) -> None:
    for item in issues:
        conn.execute(
            """
            INSERT INTO transform_rule_quality_issue (
                rule_id, name, severity, category, field, value, message
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.get("rule_id"),
                item.get("name"),
                item.get("severity"),
                item.get("category"),
                item.get("field"),
                item.get("value"),
                item.get("message"),
            ),
        )
    conn.commit()


def insert_vendor_overlays(conn: sqlite3.Connection, records: list[dict]) -> None:
    for record in records:
        vendor = record.get("vendor") or {}
        if not vendor:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO substituent_vendor_overlay (
                substituent_id, availability_tier, price_tier, lead_time_days,
                route_confidence, source, updated_at, notes, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.get("substituent_id"),
                vendor.get("availability_tier"),
                vendor.get("price_tier"),
                vendor.get("lead_time_days"),
                vendor.get("route_confidence"),
                vendor.get("source"),
                vendor.get("updated_at"),
                vendor.get("notes"),
                json.dumps(vendor, sort_keys=True),
            ),
        )
    conn.commit()


def insert_mmp_transform_evidence(conn: sqlite3.Connection, evidence_rows: list[dict]) -> None:
    for item in evidence_rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO mmp_transform_evidence (
                transform_id, variable_from_smiles, variable_to_smiles, pair_count,
                core_count, example_count, mean_delta_fragment_mw, mean_delta_clogp,
                mean_delta_tpsa, source_name, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.get("transform_id"),
                item.get("variable_from_smiles"),
                item.get("variable_to_smiles"),
                item.get("pair_count"),
                item.get("core_count"),
                item.get("example_count"),
                item.get("mean_delta_fragment_mw"),
                item.get("mean_delta_clogp"),
                item.get("mean_delta_tpsa"),
                item.get("source_name"),
                json.dumps(item, sort_keys=True),
            ),
        )
    conn.commit()


def insert_transform_mmp_mappings(conn: sqlite3.Connection, mappings: list[dict]) -> None:
    for item in mappings:
        conn.execute(
            """
            INSERT OR REPLACE INTO transform_mmp_mapping (
                mapping_id, rule_id, transform_id, replacement_label, match_type,
                pair_count, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.get("mapping_id"),
                item.get("rule_id"),
                item.get("transform_id"),
                item.get("replacement_label"),
                item.get("match_type"),
                item.get("pair_count"),
                json.dumps(item, sort_keys=True),
            ),
        )
    conn.commit()


def insert_chembl_activity_evidence(conn: sqlite3.Connection, rows: list[dict]) -> None:
    for item in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO chembl_activity_evidence (
                evidence_id, molecule_chembl_id, target_chembl_id, target_pref_name,
                target_type, target_organism, target_family, standard_type,
                standard_relation, standard_value, standard_units, pchembl_value,
                assay_chembl_id, document_chembl_id, source_name, target_family_normalized,
                target_family_label, target_family_weight, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.get("evidence_id"),
                item.get("molecule_chembl_id"),
                item.get("target_chembl_id"),
                item.get("target_pref_name"),
                item.get("target_type"),
                item.get("target_organism"),
                item.get("target_family"),
                item.get("standard_type"),
                item.get("standard_relation"),
                item.get("standard_value"),
                item.get("standard_units"),
                item.get("pchembl_value"),
                item.get("assay_chembl_id"),
                item.get("document_chembl_id"),
                item.get("source_name"),
                item.get("target_family_normalized"),
                item.get("target_family_label"),
                item.get("target_family_weight"),
                json.dumps(item, sort_keys=True),
            ),
        )
    conn.commit()


def insert_transform_activity_summaries(conn: sqlite3.Connection, rows: list[dict]) -> None:
    for item in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO transform_activity_summary (
                summary_id, mapping_id, rule_id, transform_id, replacement_label,
                orientation, from_molecule_count, to_molecule_count,
                target_summary_count, target_family_summary_count, activity_cliff_count,
                mean_delta_pchembl, mean_family_delta_pchembl, max_abs_delta_pchembl,
                activity_cliff_risk, rule_activity_judgment, rule_activity_judgment_note,
                replicate_count, assay_confidence, assay_confidence_score, uncertainty_score,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.get("summary_id"),
                item.get("mapping_id"),
                item.get("rule_id"),
                item.get("transform_id"),
                item.get("replacement_label"),
                item.get("orientation"),
                item.get("from_molecule_count"),
                item.get("to_molecule_count"),
                item.get("target_summary_count"),
                item.get("target_family_summary_count"),
                item.get("activity_cliff_count"),
                item.get("mean_delta_pchembl"),
                item.get("mean_family_delta_pchembl"),
                item.get("max_abs_delta_pchembl"),
                item.get("activity_cliff_risk"),
                item.get("rule_activity_judgment"),
                item.get("rule_activity_judgment_note"),
                item.get("replicate_count"),
                item.get("assay_confidence"),
                item.get("assay_confidence_score"),
                item.get("uncertainty_score"),
                json.dumps(item, sort_keys=True),
            ),
        )
    conn.commit()


def insert_ring_systems(conn: sqlite3.Connection, rows: list[dict], *, commit: bool = True) -> None:
    values = [
        (
            item.get("ring_id"),
            item.get("smiles"),
            item.get("canonical_smiles"),
            item.get("source_name"),
            item.get("source_dataset"),
            item.get("source_rank"),
            item.get("ring_class"),
            item.get("ring_count"),
            item.get("hetero_atom_count"),
            item.get("aromatic_ring_count"),
            item.get("heavy_atom_count"),
            item.get("fsp3"),
            item.get("source_reference"),
            json.dumps(item, sort_keys=True),
        )
        for item in rows
    ]
    if values:
        conn.executemany(
            """
            INSERT OR REPLACE INTO ring_system (
                ring_id, smiles, canonical_smiles, source_name, source_dataset,
                source_rank, ring_class, ring_count, hetero_atom_count,
                aromatic_ring_count, heavy_atom_count, fsp3, source_reference,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
    if commit:
        conn.commit()


def query_ring_systems(
    conn: sqlite3.Connection,
    *,
    search: str | None = None,
    ring_class: str | None = None,
    source_dataset: str | None = None,
    min_heavy_atom_count: int | None = None,
    max_heavy_atom_count: int | None = None,
    novelty_bucket: str | None = None,
    diversity_bucket: str | None = None,
    page: int = 1,
    page_size: int = 100,
    order_by: str = "source_rank",
) -> dict:
    page = max(int(page or 1), 1)
    page_size = max(1, min(int(page_size or 100), 500))
    where = []
    params: list[object] = []
    if search:
        like = f"%{search.strip()}%"
        where.append("(ring_id LIKE ? OR canonical_smiles LIKE ? OR source_name LIKE ? OR source_dataset LIKE ?)")
        params.extend([like, like, like, like])
    if ring_class:
        where.append("ring_class = ?")
        params.append(ring_class)
    if source_dataset:
        where.append("source_dataset = ?")
        params.append(source_dataset)
    if min_heavy_atom_count is not None:
        where.append("heavy_atom_count >= ?")
        params.append(int(min_heavy_atom_count))
    if max_heavy_atom_count is not None:
        where.append("heavy_atom_count <= ?")
        params.append(int(max_heavy_atom_count))

    novelty_sql = """
        CASE
            WHEN source_dataset='approved_drug_ring_systems' THEN 'approved_drug_precedented'
            WHEN source_dataset='clinical_trial_ring_systems' THEN 'clinical_trial_precedented'
            WHEN source_dataset='ertl_4m_ring_systems' AND COALESCE(source_rank, 999999999) <= 5000 THEN 'ertl_common'
            WHEN source_dataset='ertl_4m_ring_systems' AND COALESCE(source_rank, 999999999) <= 50000 THEN 'ertl_precedented'
            WHEN source_dataset='ertl_4m_ring_systems' AND COALESCE(source_rank, 999999999) <= 250000 THEN 'ertl_expansion'
            ELSE 'long_tail_or_unranked'
        END
    """
    diversity_sql = """
        COALESCE(ring_class, 'unclassified') || ':' ||
        CASE
            WHEN COALESCE(heavy_atom_count, 0) <= 6 THEN 'small'
            WHEN COALESCE(heavy_atom_count, 0) <= 10 THEN 'medium'
            ELSE 'large'
        END || ':' ||
        CASE
            WHEN COALESCE(hetero_atom_count, 0)=0 THEN 'carbocycle'
            WHEN COALESCE(hetero_atom_count, 0)<=2 THEN 'hetero_low'
            ELSE 'hetero_rich'
        END || ':' ||
        CASE
            WHEN COALESCE(aromatic_ring_count, 0)>0 THEN 'aromatic'
            ELSE 'aliphatic'
        END
    """
    if novelty_bucket:
        where.append(f"({novelty_sql}) = ?")
        params.append(novelty_bucket)
    if diversity_bucket:
        where.append(f"({diversity_sql}) = ?")
        params.append(diversity_bucket)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    allowed_order = {
        "source_rank": "COALESCE(source_rank, 999999999), canonical_smiles",
        "heavy_atom_count": "COALESCE(heavy_atom_count, 999999999), canonical_smiles",
        "canonical_smiles": "canonical_smiles",
        "ring_class": "ring_class, canonical_smiles",
    }
    order_sql = allowed_order.get(order_by, allowed_order["source_rank"])
    total = conn.execute(f"SELECT COUNT(*) FROM ring_system {where_sql}", params).fetchone()[0]
    offset = (page - 1) * page_size
    conn.row_factory = sqlite3.Row
    table_sql = "ring_system"
    if source_dataset and ring_class and order_by == "source_rank" and not search and not novelty_bucket and not diversity_bucket:
        table_sql = "ring_system INDEXED BY idx_ring_system_dataset_class_rank"
    rows = conn.execute(
        f"""
        SELECT
            ring_id, canonical_smiles, smiles, source_dataset, source_rank,
            ring_class, ring_count, hetero_atom_count, aromatic_ring_count,
            heavy_atom_count, fsp3, source_reference,
            {novelty_sql} AS ring_novelty_bucket,
            {diversity_sql} AS ring_diversity_bucket
        FROM {table_sql}
        {where_sql}
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    ).fetchall()
    return {
        "page": page,
        "page_size": page_size,
        "total": int(total),
        "page_count": int((total + page_size - 1) // page_size) if total else 0,
        "rows": [dict(row) for row in rows],
    }


def insert_literature_substituents(conn: sqlite3.Connection, rows: list[dict]) -> None:
    for item in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO literature_substituent (
                literature_substituent_id, smiles, canonical_smiles, source_name,
                source_dataset, source_rank, substituent_class, fragment_mw,
                clogp, tpsa, hbd, hba, heavy_atom_count, source_reference,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.get("literature_substituent_id"),
                item.get("smiles"),
                item.get("canonical_smiles"),
                item.get("source_name"),
                item.get("source_dataset"),
                item.get("source_rank"),
                item.get("substituent_class"),
                item.get("fragment_mw"),
                item.get("clogp"),
                item.get("tpsa"),
                item.get("hbd"),
                item.get("hba"),
                item.get("heavy_atom_count"),
                item.get("source_reference"),
                json.dumps(item, sort_keys=True),
            ),
        )
    conn.commit()


def insert_ring_replacements(conn: sqlite3.Connection, rows: list[dict]) -> None:
    for item in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO ring_replacement (
                replacement_id, query_smiles, replacement_smiles,
                query_canonical_smiles, replacement_canonical_smiles,
                activity_delta, evidence_count, source_name, source_reference,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.get("replacement_id"),
                item.get("query_smiles"),
                item.get("replacement_smiles"),
                item.get("query_canonical_smiles"),
                item.get("replacement_canonical_smiles"),
                item.get("activity_delta"),
                item.get("evidence_count"),
                item.get("source_name"),
                item.get("source_reference"),
                json.dumps(item, sort_keys=True),
            ),
        )
    conn.commit()


def rebuild_normalized_rgroup_replacements(conn: sqlite3.Connection) -> dict:
    from .rgroup_normalization import deduplicate_rgroup_replacements, normalize_rgroup_replacement, normalized_payload

    old_row_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        raw_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT replacement_id, source_smiles, target_smiles,
                       source_canonical_smiles, target_canonical_smiles,
                       edge_weight, layer, center_smiles, source_name, source_reference,
                       source_confidence_tier, source_confidence_score, source_confidence_basis,
                       row_sha256, source_owner, source_license, provenance_level,
                       provenance_review_status, provenance_note
                FROM rgroup_replacement
                """
            ).fetchall()
        ]
    finally:
        conn.row_factory = old_row_factory
    normalized_rows = [normalize_rgroup_replacement(row) for row in raw_rows]
    for row in normalized_rows:
        conn.execute(
            """
            UPDATE rgroup_replacement
            SET normalized_source_smiles=?,
                normalized_target_smiles=?,
                normalized_pair_key=?,
                source_record_count=?,
                aggregate_edge_weight=?,
                source_replacement_ids=?,
                source_confidence_tier=?,
                source_confidence_score=?,
                source_confidence_basis=?,
                row_sha256=?,
                source_owner=?,
                source_license=?,
                provenance_level=?,
                provenance_review_status=?,
                provenance_note=?,
                payload_json=?
            WHERE replacement_id=?
            """,
            (
                row.get("normalized_source_smiles"),
                row.get("normalized_target_smiles"),
                row.get("normalized_pair_key"),
                1,
                row.get("edge_weight") or 0,
                row.get("replacement_id"),
                row.get("source_confidence_tier"),
                row.get("source_confidence_score"),
                row.get("source_confidence_basis"),
                row.get("row_sha256"),
                row.get("source_owner"),
                row.get("source_license"),
                row.get("provenance_level"),
                row.get("provenance_review_status"),
                row.get("provenance_note"),
                json.dumps(row, sort_keys=True),
                row.get("replacement_id"),
            ),
        )

    conn.execute("DELETE FROM rgroup_replacement_normalized")
    deduped = deduplicate_rgroup_replacements(raw_rows)
    for row in deduped:
        conn.execute(
            """
            INSERT OR REPLACE INTO rgroup_replacement_normalized (
                normalized_pair_key, normalized_source_smiles, normalized_target_smiles,
                representative_replacement_id, source_record_count, aggregate_edge_weight,
                max_edge_weight, layers, source_names, source_references,
                source_confidence_tiers, max_source_confidence_score,
                source_replacement_ids, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("normalized_pair_key"),
                row.get("normalized_source_smiles"),
                row.get("normalized_target_smiles"),
                row.get("representative_replacement_id"),
                row.get("source_record_count"),
                row.get("aggregate_edge_weight"),
                row.get("max_edge_weight"),
                row.get("layers"),
                row.get("source_names"),
                row.get("source_references"),
                row.get("source_confidence_tiers"),
                row.get("max_source_confidence_score"),
                row.get("source_replacement_ids"),
                normalized_payload(row),
            ),
        )
    conn.commit()
    return {
        "raw_count": len(raw_rows),
        "normalized_pair_count": len(deduped),
        "duplicate_group_count": sum(1 for row in deduped if int(row.get("source_record_count") or 0) > 1),
    }


def insert_rgroup_replacements(conn: sqlite3.Connection, rows: list[dict]) -> None:
    from .rgroup_normalization import normalize_rgroup_replacement

    seen_ids: dict[str, int] = {}
    for item in rows:
        item = dict(item)
        base_replacement_id = str(item.get("replacement_id") or "")
        if base_replacement_id:
            seen_ids[base_replacement_id] = seen_ids.get(base_replacement_id, 0) + 1
            if seen_ids[base_replacement_id] > 1:
                item["original_replacement_id"] = base_replacement_id
                item["replacement_id"] = f"{base_replacement_id}-D{seen_ids[base_replacement_id]:04d}"
        item = normalize_rgroup_replacement(item)
        conn.execute(
            """
            INSERT OR REPLACE INTO rgroup_replacement (
                replacement_id, source_smiles, target_smiles,
                source_canonical_smiles, target_canonical_smiles,
                normalized_source_smiles, normalized_target_smiles,
                normalized_pair_key, edge_weight, source_record_count,
                aggregate_edge_weight, source_replacement_ids, layer,
                center_smiles, source_name, source_reference,
                source_confidence_tier, source_confidence_score, source_confidence_basis,
                row_sha256, source_owner, source_license, provenance_level,
                provenance_review_status, provenance_note,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.get("replacement_id"),
                item.get("source_smiles"),
                item.get("target_smiles"),
                item.get("source_canonical_smiles"),
                item.get("target_canonical_smiles"),
                item.get("normalized_source_smiles"),
                item.get("normalized_target_smiles"),
                item.get("normalized_pair_key"),
                item.get("edge_weight"),
                item.get("source_record_count") or 1,
                item.get("aggregate_edge_weight") if item.get("aggregate_edge_weight") is not None else item.get("edge_weight"),
                item.get("source_replacement_ids") or item.get("replacement_id"),
                item.get("layer"),
                item.get("center_smiles"),
                item.get("source_name"),
                item.get("source_reference"),
                item.get("source_confidence_tier"),
                item.get("source_confidence_score"),
                item.get("source_confidence_basis"),
                item.get("row_sha256"),
                item.get("source_owner"),
                item.get("source_license"),
                item.get("provenance_level"),
                item.get("provenance_review_status"),
                item.get("provenance_note"),
                json.dumps(item, sort_keys=True),
            ),
        )
    conn.commit()
    rebuild_normalized_rgroup_replacements(conn)


def insert_scaffold_replacements(conn: sqlite3.Connection, rows: list[dict]) -> None:
    for item in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO scaffold_replacement (
                scaffold_rule_id, name, from_smarts, to_smiles, attachment_count,
                replacement_class, source_name, source_reference, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.get("scaffold_rule_id"),
                item.get("name"),
                item.get("from_smarts"),
                item.get("to_smiles"),
                item.get("attachment_count"),
                item.get("replacement_class"),
                item.get("source_name"),
                item.get("source_reference"),
                json.dumps(item, sort_keys=True),
            ),
        )
    conn.commit()


def insert_scaffold_rule_review_event(conn: sqlite3.Connection, event: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO scaffold_rule_review_event (
            event_id, scaffold_rule_id, status, reviewer, score_adjustment,
            note, created_at, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.get("event_id"),
            event.get("scaffold_rule_id"),
            event.get("status"),
            event.get("reviewed_by") or event.get("reviewer"),
            event.get("score_adjustment"),
            event.get("note"),
            event.get("reviewed_at") or event.get("created_at"),
            json.dumps(event, sort_keys=True),
        ),
    )
    conn.commit()


def insert_api_health_checks(conn: sqlite3.Connection, checks: list[dict]) -> None:
    for item in checks:
        conn.execute(
            """
            INSERT OR REPLACE INTO api_health_check (
                check_id, source_name, endpoint_url, checked_at, ok, status_code,
                latency_ms, error, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.get("check_id"),
                item.get("source_name"),
                item.get("endpoint_url"),
                item.get("checked_at"),
                1 if item.get("ok") else 0,
                item.get("status_code"),
                item.get("latency_ms"),
                item.get("error"),
                json.dumps(item, sort_keys=True),
            ),
        )
    conn.commit()


def upsert_project_route_batches(
    conn: sqlite3.Connection,
    run_id: str,
    batches: list[dict],
    *,
    default_status: str = "needs_chemist_review",
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for batch in batches:
        route_batch_id = batch.get("route_batch_id")
        if not route_batch_id:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO project_route_batch (
                run_id, route_batch_id, batch_type, procurement_bucket,
                reaction_family, suggested_building_block, route_template_id,
                candidate_count, top_score, mean_lead_time_days,
                mean_route_confidence, route_risk_flags, chemist_approval_status,
                approval_note, approval_updated_at, reagent_overlap_score,
                protecting_group_risk, regioselectivity_risk, purification_risk,
                route_execution_risk_score, execution_json, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(
                (SELECT chemist_approval_status FROM project_route_batch WHERE run_id=? AND route_batch_id=?),
                ?
            ), COALESCE(
                (SELECT approval_note FROM project_route_batch WHERE run_id=? AND route_batch_id=?),
                ''
            ), COALESCE(
                (SELECT approval_updated_at FROM project_route_batch WHERE run_id=? AND route_batch_id=?),
                ?
            ), ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                route_batch_id,
                batch.get("batch_type"),
                batch.get("procurement_bucket"),
                batch.get("reaction_family"),
                batch.get("suggested_building_block"),
                batch.get("route_template_id"),
                batch.get("candidate_count"),
                batch.get("top_score"),
                batch.get("mean_lead_time_days"),
                batch.get("mean_route_confidence"),
                batch.get("route_risk_flags"),
                run_id,
                route_batch_id,
                default_status,
                run_id,
                route_batch_id,
                run_id,
                route_batch_id,
                now,
                batch.get("reagent_overlap_score"),
                batch.get("protecting_group_risk"),
                batch.get("regioselectivity_risk"),
                batch.get("purification_risk"),
                batch.get("route_execution_risk_score"),
                json.dumps(batch.get("execution") or {}, sort_keys=True),
                json.dumps(batch, sort_keys=True),
            ),
        )
    conn.commit()


def update_project_route_batch_status(
    conn: sqlite3.Connection,
    run_id: str,
    route_batch_id: str,
    *,
    status: str,
    note: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE project_route_batch
        SET chemist_approval_status=?, approval_note=?, approval_updated_at=?
        WHERE run_id=? AND route_batch_id=?
        """,
        (
            status,
            note or "",
            now,
            run_id,
            route_batch_id,
        ),
    )
    event_id = f"RBE-{run_id}-{route_batch_id}-{now}".replace(":", "").replace(".", "")
    conn.execute(
        """
        INSERT OR REPLACE INTO route_batch_status_event (
            event_id, run_id, route_batch_id, status, note, created_at, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            run_id,
            route_batch_id,
            status,
            note or "",
            now,
            json.dumps({"run_id": run_id, "route_batch_id": route_batch_id, "status": status, "note": note or ""}, sort_keys=True),
        ),
    )
    conn.commit()


def insert_route_quote_requests(conn: sqlite3.Connection, rows: list[dict]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for item in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO route_quote_request (
                quote_request_id, run_id, route_batch_id, vendor_name, request_status,
                catalog_urls, reagent_overlap_score, protecting_group_risk,
                regioselectivity_risk, purification_risk, route_execution_risk_score,
                created_at, updated_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(
                (SELECT created_at FROM route_quote_request WHERE quote_request_id=?),
                ?
            ), ?, ?)
            """,
            (
                item.get("quote_request_id"),
                item.get("run_id"),
                item.get("route_batch_id"),
                item.get("vendor_name"),
                item.get("request_status"),
                ";".join(item.get("catalog_urls") or []) if isinstance(item.get("catalog_urls"), list) else item.get("catalog_urls"),
                item.get("reagent_overlap_score"),
                item.get("protecting_group_risk"),
                item.get("regioselectivity_risk"),
                item.get("purification_risk"),
                item.get("route_execution_risk_score"),
                item.get("quote_request_id"),
                now,
                now,
                json.dumps(item, sort_keys=True),
            ),
        )
    conn.commit()


def insert_project_feedback_control(conn: sqlite3.Connection, report: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO project_feedback_control (
            control_id, project_name, created_at, endpoint_count,
            uncertainty_flag_count, drift_flag_count, recommendation_count, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            report.get("control_id"),
            report.get("project_name"),
            report.get("created_at"),
            len(report.get("endpoint_controls") or []),
            len(report.get("uncertainty_flags") or []),
            len(report.get("drift_flags") or []),
            len(report.get("recommended_next_experiments") or []),
            json.dumps(report, sort_keys=True),
        ),
    )
    conn.commit()


def insert_build_manifest(conn: sqlite3.Connection, manifest: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO build_manifest VALUES (?, ?, ?, ?)",
        (
            manifest.get("manifest_id"),
            manifest.get("created_at"),
            manifest.get("payload_sha256"),
            json.dumps(manifest, sort_keys=True),
        ),
    )
    conn.commit()


def insert_data_foundation_snapshot(conn: sqlite3.Connection, report: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO data_foundation_snapshot (
            snapshot_id, created_at, asset_count, total_record_count,
            warning_count, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            report.get("snapshot_id"),
            report.get("created_at"),
            len(report.get("assets") or []),
            int(report.get("totals", {}).get("record_count") or 0),
            len(report.get("warnings") or []),
            json.dumps(report, sort_keys=True),
        ),
    )
    conn.commit()


def insert_substituent_records(conn: sqlite3.Connection, records: list[dict]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for record in records:
        priority = record.get("priority", {})
        source = record.get("source", {})
        pubchem = source.get("pubchem", {})
        conn.execute(
            """
            INSERT OR REPLACE INTO substituent (
                substituent_id, name, short_name, smiles, canonical_smiles,
                connection_type, attachment_count, is_active, is_mvp,
                common_medchem, default_rank, source_type, source_reference,
                version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["substituent_id"],
                record["name"],
                record.get("short_name"),
                record["smiles"],
                record.get("canonical_smiles"),
                record.get("connection_type"),
                record.get("attachment_count"),
                1 if record.get("risk", {}).get("default_enabled", True) else 0,
                1 if priority.get("mvp", True) else 0,
                1 if priority.get("common_medchem", False) else 0,
                priority.get("default_rank", 999),
                source.get("type"),
                pubchem.get("query") or source.get("reference"),
                source.get("version"),
                now,
                now,
            ),
        )

        desc = record.get("calculated_descriptors", {})
        conn.execute(
            """
            INSERT OR REPLACE INTO substituent_descriptor (
                substituent_id, fragment_mw, exact_mw, clogp, tpsa, hbd, hba,
                rotatable_bonds, heavy_atom_count, ring_count,
                aromatic_ring_count, formal_charge, fsp3, qed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["substituent_id"],
                desc.get("fragment_mw"),
                desc.get("exact_mw"),
                desc.get("clogp"),
                desc.get("tpsa"),
                desc.get("hbd"),
                desc.get("hba"),
                desc.get("rotatable_bonds"),
                desc.get("heavy_atom_count"),
                desc.get("ring_count"),
                desc.get("aromatic_ring_count"),
                desc.get("formal_charge"),
                desc.get("fsp3"),
                desc.get("qed"),
            ),
        )

        for tag in ensure_list(record.get("class")):
            conn.execute("INSERT INTO substituent_tag VALUES (?, ?, ?)", (record["substituent_id"], "class", tag))
        for tag in ensure_list(record.get("direction_tags")):
            conn.execute("INSERT INTO substituent_tag VALUES (?, ?, ?)", (record["substituent_id"], "direction", tag))
        for key, value in (record.get("property_tags") or {}).items():
            conn.execute("INSERT INTO substituent_tag VALUES (?, ?, ?)", (record["substituent_id"], f"property:{key}", str(value)))
        for tag in ensure_list(record.get("risk", {}).get("risk_tags")):
            conn.execute("INSERT INTO substituent_tag VALUES (?, ?, ?)", (record["substituent_id"], "risk", tag))
        for site_type in ensure_list(record.get("allowed_site_types")):
            conn.execute(
                "INSERT INTO substituent_site_compatibility VALUES (?, ?, ?, ?)",
                (record["substituent_id"], site_type, "allowed", None),
            )
        for caution in ensure_list(record.get("risk", {}).get("cautions")):
            conn.execute(
                "INSERT INTO substituent_warning VALUES (?, ?, ?, ?)",
                (record["substituent_id"], "caution", caution, "medium"),
            )
        review = record.get("review", {})
        conn.execute(
            "INSERT OR REPLACE INTO substituent_review VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                record["substituent_id"],
                review.get("status"),
                review.get("reviewed_by"),
                review.get("reviewed_at"),
                ";".join(ensure_list(review.get("review_notes"))),
                ";".join(ensure_list(review.get("use_cases"))),
                ";".join(ensure_list(review.get("avoid_contexts"))),
            ),
        )
        for entry in ensure_list(record.get("version_history")):
            if not isinstance(entry, dict):
                continue
            conn.execute(
                "INSERT INTO substituent_version_log VALUES (?, ?, ?, ?, ?)",
                (
                    record["substituent_id"],
                    entry.get("version"),
                    entry.get("date"),
                    entry.get("change_type"),
                    entry.get("summary"),
                ),
            )
        if pubchem:
            conn.execute(
                "INSERT OR REPLACE INTO source_metadata VALUES (?, ?, ?, ?, ?)",
                (
                    record["substituent_id"],
                    "PubChem PUG-REST",
                    pubchem.get("query"),
                    json.dumps(pubchem, sort_keys=True),
                    pubchem.get("fetched_at"),
                ),
            )
    conn.commit()
