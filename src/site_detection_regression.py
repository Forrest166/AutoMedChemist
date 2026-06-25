from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .chemistry import standardize_molecule
from .sites import detect_modification_sites


DEFAULT_SITE_DETECTION_REGRESSION_JSON = Path("data/projects/demo/site_detection_regression_report.json")
DEFAULT_SITE_DETECTION_REGRESSION_CSV = Path("data/projects/demo/site_detection_regression_report.csv")
DEFAULT_SITE_DETECTION_REGRESSION_MD = Path("docs/site_detection_regression_report.md")
DEFAULT_SITE_DETECTION_COVERAGE_CSV = Path("data/projects/demo/site_detection_regression_coverage.csv")
DEFAULT_SITE_DETECTION_PROJECT_SAMPLE_CSV = Path("data/projects/demo/site_detection_project_sample_pack.csv")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]
REQUIRED_SITE_CLASSES = [
    "methoxy_position",
    "ester_region",
    "basic_amine",
    "alkyl_terminal",
    "amide_region",
    "sulfonamide_region",
    "heteroaryl_nitrogen",
    "charged_group",
]
REQUIRED_CASE_TYPES = ["positive", "negative", "boundary"]


REGRESSION_CASES = [
    {
        "case_id": "methoxy_aryl_soft_spot",
        "target_site_class": "methoxy_position",
        "tier": "project_core_positive",
        "smiles": "COc1ccc(Cl)cc1",
        "expected_site_types": ["methoxy_position", "aromatic_halide"],
        "forbidden_site_types": [],
        "case_type": "positive",
        "rationale": "Aryl methoxy plus aryl chloride should route to methoxy soft-spot and aromatic-halide review.",
    },
    {
        "case_id": "ester_hydrolysis_region",
        "target_site_class": "ester_region",
        "tier": "project_core_positive",
        "smiles": "CCOC(=O)c1ccccc1",
        "expected_site_types": ["ester_region"],
        "forbidden_site_types": ["methoxy_position"],
        "case_type": "positive",
        "rationale": "Ethyl benzoate should detect ester replacement without confusing the ethoxy group for aryl methoxy.",
    },
    {
        "case_id": "basic_amine_tail",
        "target_site_class": "basic_amine",
        "tier": "project_core_positive",
        "smiles": "CCN(CC)Cc1ccccc1",
        "expected_site_types": ["basic_amine", "alkyl_terminal"],
        "forbidden_site_types": ["amide_region"],
        "case_type": "positive",
        "rationale": "Aliphatic tertiary amine and terminal ethyl tails should be locally reviewable.",
    },
    {
        "case_id": "terminal_tail_without_ring",
        "target_site_class": "alkyl_terminal",
        "tier": "boundary_guard",
        "smiles": "CCCCN",
        "expected_site_types": ["alkyl_terminal", "basic_amine"],
        "forbidden_site_types": ["aromatic_CH"],
        "case_type": "boundary",
        "rationale": "Simple aliphatic tail should not require aromatic context to be detected.",
    },
    {
        "case_id": "linear_terminal_tail",
        "target_site_class": "alkyl_terminal",
        "tier": "project_core_positive",
        "smiles": "CCCCO",
        "expected_site_types": ["alkyl_terminal"],
        "forbidden_site_types": ["ring_system"],
        "case_type": "positive",
        "rationale": "Linear terminal alkyl tail should be detected outside ring context.",
    },
    {
        "case_id": "aliphatic_ether_not_aryl_methoxy",
        "target_site_class": "methoxy_position",
        "tier": "boundary_guard",
        "smiles": "COCC",
        "expected_site_types": ["alkyl_terminal", "linker_region"],
        "forbidden_site_types": ["methoxy_position"],
        "case_type": "boundary",
        "rationale": "Aliphatic methyl ether is a boundary case for aryl-methoxy soft-spot routing.",
    },
    {
        "case_id": "amide_boundary_not_ester",
        "target_site_class": "ester_region",
        "tier": "boundary_guard",
        "smiles": "CC(=O)N(C)c1ccccc1",
        "expected_site_types": ["amide_region"],
        "forbidden_site_types": ["ester_region"],
        "case_type": "boundary",
        "rationale": "A carbonyl attached to nitrogen must stay out of ester hydrolysis routing.",
    },
    {
        "case_id": "amide_boundary_not_basic_amine",
        "target_site_class": "basic_amine",
        "tier": "boundary_guard",
        "smiles": "CCN(C=O)C",
        "expected_site_types": ["amide_region"],
        "forbidden_site_types": ["basic_amine"],
        "case_type": "boundary",
        "rationale": "Formamide-like nitrogen is not a basic amine even when aliphatic substituents exist.",
    },
    {
        "case_id": "branched_tail_boundary",
        "target_site_class": "alkyl_terminal",
        "tier": "boundary_guard",
        "smiles": "CC(C)(C)c1ccccc1",
        "expected_site_types": ["alkyl_terminal", "ring_system"],
        "forbidden_site_types": [],
        "case_type": "boundary",
        "rationale": "Branched terminal tails should still be visible while retaining aryl-ring context.",
    },
    {
        "case_id": "phenol_not_methoxy",
        "target_site_class": "methoxy_position",
        "tier": "false_positive_tier_1",
        "smiles": "Oc1ccccc1",
        "expected_site_types": ["aromatic_CH"],
        "forbidden_site_types": ["methoxy_position"],
        "case_type": "negative",
        "rationale": "Phenol is not an aryl methoxy metabolic soft spot.",
    },
    {
        "case_id": "amide_not_basic_amine",
        "target_site_class": "basic_amine",
        "tier": "false_positive_tier_1",
        "smiles": "CC(=O)N(C)c1ccccc1",
        "expected_site_types": ["amide_region"],
        "forbidden_site_types": ["basic_amine"],
        "case_type": "negative",
        "rationale": "Amide nitrogen should not be routed as a basic amine.",
    },
    {
        "case_id": "acid_not_ester",
        "target_site_class": "ester_region",
        "tier": "false_positive_tier_1",
        "smiles": "CC(=O)O",
        "expected_site_types": ["acid_region"],
        "forbidden_site_types": ["ester_region"],
        "case_type": "negative",
        "rationale": "Carboxylic acid should stay in acid bioisostere review, not ester hydrolysis review.",
    },
    {
        "case_id": "cyclohexane_no_terminal_tail",
        "target_site_class": "alkyl_terminal",
        "tier": "false_positive_tier_1",
        "smiles": "C1CCCCC1",
        "expected_site_types": ["ring_system"],
        "forbidden_site_types": ["alkyl_terminal"],
        "case_type": "negative",
        "rationale": "Ring carbons are not terminal tails.",
    },
    {
        "case_id": "dimethoxy_aryl_soft_spot",
        "target_site_class": "methoxy_position",
        "tier": "expanded_positive",
        "smiles": "COc1ccc(OC)cc1",
        "expected_site_types": ["methoxy_position", "aromatic_CH"],
        "forbidden_site_types": [],
        "case_type": "positive",
        "rationale": "Multiple aryl methoxy groups should remain visible as soft spots without losing aromatic C-H context.",
    },
    {
        "case_id": "benzyl_methyl_ether_not_aryl_methoxy",
        "target_site_class": "methoxy_position",
        "tier": "expanded_false_positive",
        "smiles": "COCc1ccccc1",
        "expected_site_types": ["aromatic_CH", "ring_system"],
        "forbidden_site_types": ["methoxy_position"],
        "case_type": "negative",
        "rationale": "A benzyl methyl ether is not an aryl methoxy soft spot.",
    },
    {
        "case_id": "methoxy_aniline_boundary",
        "target_site_class": "methoxy_position",
        "tier": "expanded_boundary",
        "smiles": "COc1ccc(N)cc1",
        "expected_site_types": ["methoxy_position", "basic_amine"],
        "forbidden_site_types": [],
        "case_type": "boundary",
        "rationale": "Aryl methoxy and an aniline-like amine can coexist and should both route to local review.",
    },
    {
        "case_id": "aliphatic_ester_positive",
        "target_site_class": "ester_region",
        "tier": "expanded_positive",
        "smiles": "CCOC(=O)C",
        "expected_site_types": ["ester_region", "alkyl_terminal"],
        "forbidden_site_types": ["methoxy_position"],
        "case_type": "positive",
        "rationale": "Aliphatic ester hydrolysis review should not require aryl context.",
    },
    {
        "case_id": "lactone_ester_boundary",
        "target_site_class": "ester_region",
        "tier": "expanded_boundary",
        "smiles": "O=C1OCCC1",
        "expected_site_types": ["ester_region", "ring_system"],
        "forbidden_site_types": [],
        "case_type": "boundary",
        "rationale": "A cyclic ester should be detected as an ester while preserving ring-system context.",
    },
    {
        "case_id": "carboxylate_not_ester",
        "target_site_class": "ester_region",
        "tier": "expanded_false_positive",
        "smiles": "CC(=O)[O-]",
        "expected_site_types": ["acid_region"],
        "forbidden_site_types": ["ester_region"],
        "case_type": "negative",
        "rationale": "Ionized carboxylate should stay out of ester replacement routing.",
    },
    {
        "case_id": "piperidine_basic_amine_positive",
        "target_site_class": "basic_amine",
        "tier": "expanded_positive",
        "smiles": "CN1CCCCC1",
        "expected_site_types": ["basic_amine", "ring_system"],
        "forbidden_site_types": ["amide_region"],
        "case_type": "positive",
        "rationale": "A saturated cyclic tertiary amine should route as a basic amine.",
    },
    {
        "case_id": "quaternary_ammonium_not_basic_amine",
        "target_site_class": "basic_amine",
        "tier": "expanded_false_positive",
        "smiles": "CC[N+](C)(C)C",
        "expected_site_types": ["alkyl_terminal", "charged_group"],
        "forbidden_site_types": ["basic_amine"],
        "case_type": "negative",
        "rationale": "A quaternary ammonium center is not a neutral basic amine replacement target.",
    },
    {
        "case_id": "sulfonamide_not_basic_amine",
        "target_site_class": "basic_amine",
        "tier": "expanded_false_positive",
        "smiles": "CS(=O)(=O)N(C)C",
        "expected_site_types": ["alkyl_terminal", "sulfonamide_region"],
        "forbidden_site_types": ["basic_amine"],
        "case_type": "negative",
        "rationale": "Sulfonamide nitrogen should not be promoted into basic amine routing.",
    },
    {
        "case_id": "isobutane_terminal_tail_positive",
        "target_site_class": "alkyl_terminal",
        "tier": "expanded_positive",
        "smiles": "CC(C)C",
        "expected_site_types": ["alkyl_terminal"],
        "forbidden_site_types": ["ring_system"],
        "case_type": "positive",
        "rationale": "Compact branched aliphatic tails should be visible as terminal-tail opportunities.",
    },
    {
        "case_id": "tert_butyl_amine_tail_boundary",
        "target_site_class": "alkyl_terminal",
        "tier": "expanded_boundary",
        "smiles": "CC(C)(C)N",
        "expected_site_types": ["alkyl_terminal", "basic_amine"],
        "forbidden_site_types": [],
        "case_type": "boundary",
        "rationale": "A tert-butyl amine should expose both tail and amine review contexts.",
    },
    {
        "case_id": "heteroaryl_nitrogen_not_basic_amine",
        "target_site_class": "basic_amine",
        "tier": "expanded_false_positive",
        "smiles": "c1ccncc1",
        "expected_site_types": ["aromatic_CH", "heteroaryl_nitrogen", "ring_system"],
        "forbidden_site_types": ["basic_amine"],
        "case_type": "negative",
        "rationale": "Pyridine-like heteroaryl nitrogen should not be treated as a basic aliphatic amine.",
    },
    {
        "case_id": "acetamide_amide_bioisostere_positive",
        "target_site_class": "amide_region",
        "tier": "expanded_positive",
        "smiles": "CC(=O)N(C)c1ccccc1",
        "expected_site_types": ["amide_region", "aromatic_CH"],
        "forbidden_site_types": ["ester_region", "basic_amine"],
        "case_type": "positive",
        "rationale": "Tertiary amide carbonyl should route to amide bioisostere review, not ester or basic amine routing.",
    },
    {
        "case_id": "ester_not_amide",
        "target_site_class": "amide_region",
        "tier": "expanded_false_positive",
        "smiles": "CCOC(=O)C",
        "expected_site_types": ["ester_region", "alkyl_terminal"],
        "forbidden_site_types": ["amide_region"],
        "case_type": "negative",
        "rationale": "Ester carbonyl should stay out of amide bioisostere review.",
    },
    {
        "case_id": "amino_amide_boundary",
        "target_site_class": "amide_region",
        "tier": "expanded_boundary",
        "smiles": "CC(=O)NCCN",
        "expected_site_types": ["amide_region", "basic_amine", "alkyl_terminal"],
        "forbidden_site_types": ["ester_region"],
        "case_type": "boundary",
        "rationale": "An amino-amide exposes both amide bioisostere and neutral amine review without conflating the two.",
    },
    {
        "case_id": "sulfonamide_region_positive",
        "target_site_class": "sulfonamide_region",
        "tier": "expanded_positive",
        "smiles": "CS(=O)(=O)N(C)C",
        "expected_site_types": ["sulfonamide_region"],
        "forbidden_site_types": ["basic_amine"],
        "case_type": "positive",
        "rationale": "Sulfonamide should receive its own review class while suppressing basic amine routing.",
    },
    {
        "case_id": "amide_not_sulfonamide",
        "target_site_class": "sulfonamide_region",
        "tier": "expanded_false_positive",
        "smiles": "CC(=O)N(C)C",
        "expected_site_types": ["amide_region"],
        "forbidden_site_types": ["sulfonamide_region"],
        "case_type": "negative",
        "rationale": "A carbonyl amide should not be mistaken for sulfonamide.",
    },
    {
        "case_id": "aryl_sulfonamide_boundary",
        "target_site_class": "sulfonamide_region",
        "tier": "expanded_boundary",
        "smiles": "NS(=O)(=O)c1ccccc1",
        "expected_site_types": ["sulfonamide_region", "aromatic_CH", "ring_system"],
        "forbidden_site_types": ["basic_amine"],
        "case_type": "boundary",
        "rationale": "Aryl sulfonamide should preserve aryl context while routing sulfonamide review.",
    },
    {
        "case_id": "pyridine_heteroaryl_liability_positive",
        "target_site_class": "heteroaryl_nitrogen",
        "tier": "expanded_positive",
        "smiles": "c1ccncc1",
        "expected_site_types": ["heteroaryl_nitrogen", "ring_system"],
        "forbidden_site_types": ["basic_amine"],
        "case_type": "positive",
        "rationale": "Pyridine nitrogen should route to heteroaryl liability review instead of basic amine review.",
    },
    {
        "case_id": "benzene_not_heteroaryl_nitrogen",
        "target_site_class": "heteroaryl_nitrogen",
        "tier": "expanded_false_positive",
        "smiles": "c1ccccc1",
        "expected_site_types": ["aromatic_CH", "ring_system"],
        "forbidden_site_types": ["heteroaryl_nitrogen"],
        "case_type": "negative",
        "rationale": "A carbocycle should not emit heteroaryl nitrogen review.",
    },
    {
        "case_id": "diazine_heteroaryl_boundary",
        "target_site_class": "heteroaryl_nitrogen",
        "tier": "expanded_boundary",
        "smiles": "c1nccnc1",
        "expected_site_types": ["heteroaryl_nitrogen", "ring_system"],
        "forbidden_site_types": ["basic_amine"],
        "case_type": "boundary",
        "rationale": "Multiple heteroaryl nitrogens should be detected without falling into aliphatic amine logic.",
    },
    {
        "case_id": "quaternary_charged_group_positive",
        "target_site_class": "charged_group",
        "tier": "expanded_positive",
        "smiles": "CC[N+](C)(C)C",
        "expected_site_types": ["charged_group", "alkyl_terminal"],
        "forbidden_site_types": ["basic_amine"],
        "case_type": "positive",
        "rationale": "Quaternary ammonium should route as a charged-group boundary rather than a neutral amine.",
    },
    {
        "case_id": "neutral_amine_not_charged_group",
        "target_site_class": "charged_group",
        "tier": "expanded_false_positive",
        "smiles": "CCN(CC)CC",
        "expected_site_types": ["basic_amine", "alkyl_terminal"],
        "forbidden_site_types": ["charged_group"],
        "case_type": "negative",
        "rationale": "Neutral tertiary amine is basic amine review, not charged-group review.",
    },
    {
        "case_id": "nitro_aromatic_charged_boundary",
        "target_site_class": "charged_group",
        "tier": "expanded_boundary",
        "smiles": "O=[N+]([O-])c1ccccc1",
        "expected_site_types": ["aromatic_CH", "charged_group", "ring_system"],
        "forbidden_site_types": ["basic_amine"],
        "case_type": "boundary",
        "rationale": "A charged nitro substituent on an aryl ring should surface charge-state review without basic amine routing.",
    },
]


def _site_types(smiles: str) -> list[str]:
    mol = standardize_molecule(smiles)
    return sorted({site.site_type for site in detect_modification_sites(mol)})


def _read_candidate_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _coverage_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    coverage: list[dict[str, Any]] = []
    for site_class in REQUIRED_SITE_CLASSES:
        class_rows = [row for row in rows if row.get("target_site_class") == site_class]
        case_counts = {
            case_type: sum(1 for row in class_rows if row.get("case_type") == case_type and row.get("status") == "pass")
            for case_type in REQUIRED_CASE_TYPES
        }
        missing_case_types = [case_type for case_type, count in case_counts.items() if count <= 0]
        coverage.append(
            {
                "target_site_class": site_class,
                "status": "pass" if not missing_case_types else "fail",
                "positive_count": case_counts["positive"],
                "negative_count": case_counts["negative"],
                "boundary_count": case_counts["boundary"],
                "missing_case_types": ";".join(missing_case_types),
                "next_action": "Add positive, negative, and boundary examples for this site class." if missing_case_types else "Coverage gate satisfied.",
            }
        )
    return coverage


def _project_sample_rows(root_path: Path, project_name: str, *, max_rows: int = 16) -> list[dict[str, Any]]:
    project_dir = root_path / "data" / "projects" / project_name
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(_read_candidate_rows(project_dir / "candidates.csv")[:max_rows], start=1):
        smiles = str(row.get("smiles") or "").strip()
        detected: list[str] = []
        status = "missing_smiles"
        if smiles and len(smiles) <= 120:
            try:
                detected = _site_types(smiles)
                status = "sampled"
            except Exception:
                status = "parse_failed"
        elif smiles:
            status = "skipped_large_smiles"
        declared = str(row.get("site_class") or "").strip()
        alignment = "not_declared"
        if declared:
            alignment = "aligned" if declared in detected or any(part and part in detected for part in declared.split(";")) else "declared_not_detected"
        rows.append(
            {
                "sample_id": f"{project_name}_candidate_{index:03d}",
                "candidate_id": row.get("candidate_id", ""),
                "smiles": smiles,
                "declared_site_class": declared,
                "detected_site_types": ";".join(detected),
                "site_class_alignment": alignment,
                "status": status,
                "tier": "project_sample_observed",
                "source": str(project_dir / "candidates.csv"),
            }
        )
    return rows


def build_site_detection_regression_report(*, root: str | Path = ".", project_name: str = "demo") -> dict[str, Any]:
    root_path = Path(root)
    rows: list[dict[str, Any]] = []
    for case in REGRESSION_CASES:
        detected = _site_types(str(case["smiles"]))
        expected = list(case.get("expected_site_types") or [])
        forbidden = list(case.get("forbidden_site_types") or [])
        missing = [site for site in expected if site not in detected]
        forbidden_hits = [site for site in forbidden if site in detected]
        status = "pass" if not missing and not forbidden_hits else "fail"
        rows.append(
            {
                "case_id": case["case_id"],
                "case_type": case["case_type"],
                "target_site_class": case.get("target_site_class", ""),
                "tier": case.get("tier", ""),
                "smiles": case["smiles"],
                "status": status,
                "detected_site_types": ";".join(detected),
                "expected_site_types": ";".join(expected),
                "missing_site_types": ";".join(missing),
                "forbidden_site_types": ";".join(forbidden),
                "forbidden_hits": ";".join(forbidden_hits),
                "rationale": case["rationale"],
            }
        )
    fail_count = sum(1 for row in rows if row["status"] == "fail")
    coverage = _coverage_rows(rows)
    coverage_fail_count = sum(1 for row in coverage if row["status"] == "fail")
    project_sample_rows = _project_sample_rows(root_path, project_name)
    status = "pass" if fail_count == 0 and coverage_fail_count == 0 else "fail"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "site_detection_regression",
        "project_name": project_name,
        "row_count": len(rows),
        "fail_count": fail_count,
        "coverage_fail_count": coverage_fail_count,
        "case_type_counts": {case_type: sum(1 for row in rows if row["case_type"] == case_type) for case_type in sorted({row["case_type"] for row in rows})},
        "site_classes_under_test": REQUIRED_SITE_CLASSES,
        "coverage_rows": coverage,
        "project_sample_count": len(project_sample_rows),
        "project_sample_rows": project_sample_rows,
        "rows": rows,
        "recommended_next_actions": [
            "Add a regression case whenever a new site class or false-positive guard changes candidate routing.",
            "Keep positive, negative, and boundary coverage non-empty for each required site class.",
            "Use the project sample pack as observed local parser grounding, not as experimental feedback.",
            "Keep this report local and non-experimental; it validates parser behavior only.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_site_detection_regression_markdown(report: dict) -> str:
    lines = [
        "# Site Detection Regression",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows / failures: `{report.get('row_count')}` / `{report.get('fail_count')}`",
        "",
        "## Coverage Gate",
        "",
        "| Site Class | Status | Positive | Negative | Boundary | Missing |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("coverage_rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("target_site_class") or ""),
                    str(row.get("status") or ""),
                    str(row.get("positive_count") or 0),
                    str(row.get("negative_count") or 0),
                    str(row.get("boundary_count") or 0),
                    str(row.get("missing_case_types") or ""),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Regression Cases",
            "",
        "| Case | Type | Status | Detected | Missing | Forbidden Hits | Rationale |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("case_id") or ""),
                    str(row.get("case_type") or ""),
                    str(row.get("status") or ""),
                    str(row.get("detected_site_types") or ""),
                    str(row.get("missing_site_types") or ""),
                    str(row.get("forbidden_hits") or ""),
                    str(row.get("rationale") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_site_detection_regression_report(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_SITE_DETECTION_REGRESSION_JSON,
    csv_path: str | Path | None = DEFAULT_SITE_DETECTION_REGRESSION_CSV,
    markdown_path: str | Path | None = DEFAULT_SITE_DETECTION_REGRESSION_MD,
    coverage_csv_path: str | Path | None = None,
    project_sample_csv_path: str | Path | None = None,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path:
        fields = [
            "case_id",
            "case_type",
            "target_site_class",
            "tier",
            "smiles",
            "status",
            "detected_site_types",
            "expected_site_types",
            "missing_site_types",
            "forbidden_site_types",
            "forbidden_hits",
            "rationale",
        ]
        csv_file = Path(csv_path)
        csv_file.parent.mkdir(parents=True, exist_ok=True)
        with csv_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in report.get("rows") or []:
                writer.writerow({field: row.get(field, "") for field in fields})
    coverage_target = Path(coverage_csv_path) if coverage_csv_path else json_file.parent / DEFAULT_SITE_DETECTION_COVERAGE_CSV.name
    coverage_target.parent.mkdir(parents=True, exist_ok=True)
    with coverage_target.open("w", encoding="utf-8", newline="") as handle:
        fields = ["target_site_class", "status", "positive_count", "negative_count", "boundary_count", "missing_case_types", "next_action"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in report.get("coverage_rows") or []:
            writer.writerow({field: row.get(field, "") for field in fields})
    sample_target = Path(project_sample_csv_path) if project_sample_csv_path else json_file.parent / DEFAULT_SITE_DETECTION_PROJECT_SAMPLE_CSV.name
    sample_target.parent.mkdir(parents=True, exist_ok=True)
    with sample_target.open("w", encoding="utf-8", newline="") as handle:
        fields = [
            "sample_id",
            "candidate_id",
            "smiles",
            "declared_site_class",
            "detected_site_types",
            "site_class_alignment",
            "status",
            "tier",
            "source",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in report.get("project_sample_rows") or []:
            writer.writerow({field: row.get(field, "") for field in fields})
    if markdown_path:
        md_file = Path(markdown_path)
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(render_site_detection_regression_markdown(report), encoding="utf-8")
