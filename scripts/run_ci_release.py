from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.request
from tempfile import TemporaryDirectory
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.release_bundle import create_release_bundle, verify_release_bundle, write_latest_release_checksum_report, write_release_bundle_report  # noqa: E402


def _run_step(name: str, command: list[str], *, timeout: int = 300, cwd: Path | None = None) -> dict:
    started = time.time()
    proc = subprocess.run(command, cwd=cwd or ROOT, capture_output=True, text=True, timeout=timeout)
    elapsed = round(time.time() - started, 2)
    result = {
        "name": name,
        "command": command,
        "cwd": str((cwd or ROOT).resolve()),
        "returncode": proc.returncode,
        "elapsed_seconds": elapsed,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }
    if proc.returncode != 0:
        raise RuntimeError(json.dumps(result, indent=2, sort_keys=True))
    return result


def _find_free_port(start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free localhost port found from {start}.")


def _wait_for_http(url: str, timeout: int = 60) -> None:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status < 500:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(1.0)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def _browser_smoke(port: int, *, timeout: int = 120, root: Path = ROOT, name: str = "browser_smoke") -> dict:
    url = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(root / "app" / "streamlit_app.py"),
            "--server.port",
            str(port),
            "--server.headless",
            "true",
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    try:
        _wait_for_http(url, timeout=60)
        return _run_step(
            name,
            [
                sys.executable,
                str(root / "scripts" / "browser_smoke_edge.py"),
                "--url",
                url,
                "--out",
                str(root / "data" / "projects" / "demo" / f"{name}.png"),
                "--wait-seconds",
                "90",
                "--settle-seconds",
                "20",
                "--attempts",
                "8",
            ],
            timeout=timeout,
            cwd=root,
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _bundle_smoke(bundle_path: str, port: int, *, include_browser: bool = True) -> list[dict]:
    steps = []
    with TemporaryDirectory(prefix="localmedchem-bundle-") as temp_dir:
        verify = verify_release_bundle(bundle_path, Path(temp_dir) / "bundle")
        if not verify["ok"]:
            raise RuntimeError(json.dumps(verify, indent=2, sort_keys=True))
        bundle_root = Path(verify["extract_dir"])
        steps.append({"name": "verify_release_bundle", "returncode": 0, "elapsed_seconds": 0.0, "bundle_verify": verify})
        steps.append(
            _run_step(
                "bundle_sample_enumeration",
                [
                    sys.executable,
                    str(bundle_root / "scripts" / "run_mvp.py"),
                    "--smiles",
                    "COc1ccc(Cl)cc1",
                    "--direction",
                    "increase_polarity",
                    "--max-candidates",
                    "10",
                    "--disable-replacement-network",
                    "--output-dir",
                    str(bundle_root / "data" / "projects" / "bundle_smoke"),
                ],
                timeout=180,
                cwd=bundle_root,
            )
        )
        if include_browser:
            steps.append(_browser_smoke(_find_free_port(port), timeout=160, root=bundle_root, name="bundle_browser_smoke"))
    return steps


def main() -> None:
    parser = argparse.ArgumentParser(description="Run build, QA, tests, sample enumeration, UI smoke, and release bundling.")
    parser.add_argument("--skip-browser", action="store_true")
    parser.add_argument("--port", type=int, default=8522)
    parser.add_argument("--bundle-out", default=None)
    parser.add_argument("--report-out", default=str(ROOT / "data" / "releases" / "ci_release_report.json"))
    args = parser.parse_args()

    created_at = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    bundle_out = args.bundle_out or str(ROOT / "data" / "releases" / f"localmedchem_release_{created_at}.zip")
    steps = []
    failed = None
    try:
        steps.append(
            _run_step(
                "expand_rgroup_replacement_sources",
                [sys.executable, str(ROOT / "scripts" / "expand_rgroup_replacement_sources.py")],
                timeout=120,
            )
        )
        steps.append(
            _run_step(
                "build_library",
                [sys.executable, str(ROOT / "scripts" / "build_library.py"), "--preserve-db-ring-tables"],
                timeout=600,
            )
        )
        steps.append(_run_step("validate_transform_rules", [sys.executable, str(ROOT / "scripts" / "validate_transform_rules.py")], timeout=120))
        steps.append(_run_step("validate_data_quality", [sys.executable, str(ROOT / "scripts" / "validate_data_quality.py"), "--strict"], timeout=180))
        steps.append(
            _run_step(
                "rgroup_normalization_report",
                [sys.executable, str(ROOT / "scripts" / "build_rgroup_normalization_report.py"), "--write-db"],
                timeout=120,
            )
        )
        steps.append(_run_step("scaffold_rule_calibration", [sys.executable, str(ROOT / "scripts" / "calibrate_scaffold_rules.py")], timeout=120))
        steps.append(_run_step("pytest", [sys.executable, "-m", "pytest", "-q"], timeout=600))
        steps.append(
            _run_step(
                "sample_enumeration_default",
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run_mvp.py"),
                    "--smiles",
                    "COc1ccc(Cl)cc1",
                    "--direction",
                    "increase_polarity",
                    "--output-dir",
                    str(ROOT / "data" / "projects" / "demo" / "ci_default"),
                ],
                timeout=180,
            )
        )
        steps.append(
            _run_step(
                "sample_enumeration_basic_amine",
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run_mvp.py"),
                    "--smiles",
                    "CCNC",
                    "--direction",
                    "reduce_basicity",
                    "--site-index",
                    "1",
                    "--output-dir",
                    str(ROOT / "data" / "projects" / "demo" / "ci_basic_amine"),
                    "--diverse-top-n",
                    "5",
                ],
                timeout=180,
            )
        )
        steps.append(
            _run_step(
                "route_batches_default",
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_route_batches.py"),
                    "--candidates-csv",
                    str(ROOT / "data" / "projects" / "demo" / "ci_default" / "candidates.csv"),
                    "--out-dir",
                    str(ROOT / "data" / "projects" / "demo" / "ci_default" / "route_batches"),
                ],
                timeout=120,
            )
        )
        steps.append(
            _run_step(
                "decision_packet_default",
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_decision_packet.py"),
                    "--candidates-csv",
                    str(ROOT / "data" / "projects" / "demo" / "ci_default" / "candidates.csv"),
                    "--project-name",
                    "demo",
                    "--output-prefix",
                    str(ROOT / "data" / "projects" / "demo" / "medchem_decision_packet"),
                ],
                timeout=120,
            )
        )
        steps.append(
            _run_step(
                "decision_strategy_learning",
                [sys.executable, str(ROOT / "scripts" / "build_decision_strategy_learning_report.py")],
                timeout=120,
            )
        )
        steps.append(
            _run_step(
                "transform_evidence_report",
                [sys.executable, str(ROOT / "scripts" / "build_transform_evidence_report.py")],
                timeout=120,
            )
        )
        steps.append(
            _run_step(
                "transform_activity_report",
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_transform_activity_report.py"),
                    "--include-auto-mmp",
                    "--write-db",
                ],
                timeout=180,
            )
        )
        steps.append(
            _run_step(
                "public_strategy_signal_report",
                [sys.executable, str(ROOT / "scripts" / "build_public_strategy_signal_report.py")],
                timeout=120,
            )
        )
        steps.append(
            _run_step(
                "project_calibration",
                [
                    sys.executable,
                    str(ROOT / "scripts" / "calibrate_project_models.py"),
                    "--json-out",
                    str(ROOT / "data" / "projects" / "demo" / "model_calibration_report.json"),
                ],
                timeout=120,
            )
        )
        steps.append(
            _run_step(
                "evidence_confidence_report",
                [sys.executable, str(ROOT / "scripts" / "build_evidence_confidence_report.py")],
                timeout=120,
            )
        )
        steps.append(
            _run_step(
                "evidence_residual_tasks",
                [sys.executable, str(ROOT / "scripts" / "build_evidence_residual_tasks.py")],
                timeout=120,
            )
        )
        steps.append(
            _run_step(
                "residual_experiment_plan",
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_residual_experiment_plan.py"),
                    "--upsert-db",
                    "--mark-planned",
                ],
                timeout=120,
            )
        )
        steps.append(
            _run_step(
                "multi_objective_calibration",
                [sys.executable, str(ROOT / "scripts" / "calibrate_multi_objective_profiles.py")],
                timeout=120,
            )
        )
        steps.append(
            _run_step(
                "feedback_control_report",
                [sys.executable, str(ROOT / "scripts" / "build_feedback_control_report.py")],
                timeout=120,
            )
        )
        steps.append(
            _run_step(
                "scaffold_review_workspace",
                [sys.executable, str(ROOT / "scripts" / "build_scaffold_review_workspace_report.py")],
                timeout=120,
            )
        )
        steps.append(
            _run_step(
                "scaffold_calibration_audit",
                [sys.executable, str(ROOT / "scripts" / "calibrate_scaffold_rules.py")],
                timeout=120,
            )
        )
        steps.append(
            _run_step(
                "analog_series_report",
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_analog_series_report.py"),
                    "--candidates-csv",
                    str(ROOT / "data" / "projects" / "demo" / "ci_default" / "candidates.csv"),
                    "--project-name",
                    "demo_learning",
                ],
                timeout=120,
            )
        )
        steps.append(
            _run_step(
                "experiment_plan",
                [sys.executable, str(ROOT / "scripts" / "build_experiment_plan.py"), "--batch-size", "24"],
                timeout=120,
            )
        )
        steps.append(
            _run_step(
                "closed_loop_drill",
                [sys.executable, str(ROOT / "scripts" / "run_closed_loop_drill.py")],
                timeout=180,
            )
        )
        steps.append(
            _run_step(
                "closed_loop_acceptance",
                [sys.executable, str(ROOT / "scripts" / "check_closed_loop_drill_acceptance.py")],
                timeout=120,
            )
        )
        steps.append(_run_step("site_detection_regression", [sys.executable, str(ROOT / "scripts" / "build_site_detection_regression_report.py")], timeout=120))
        steps.append(_run_step("site_detection_confidence", [sys.executable, str(ROOT / "scripts" / "build_site_detection_confidence.py")], timeout=120))
        steps.append(_run_step("source_expansion_governance", [sys.executable, str(ROOT / "scripts" / "build_source_expansion_governance.py")], timeout=120))
        steps.append(_run_step("feed_promotion_simulator", [sys.executable, str(ROOT / "scripts" / "build_feed_promotion_simulator.py")], timeout=120))
        steps.append(_run_step("rgroup_staging_quality_budget", [sys.executable, str(ROOT / "scripts" / "build_rgroup_staging_quality_budget.py")], timeout=120))
        steps.append(_run_step("staged_feed_sandbox_scoring", [sys.executable, str(ROOT / "scripts" / "build_staged_feed_sandbox_scoring.py")], timeout=120))
        steps.append(
            _run_step(
                "sandbox_score_delta_review_packet",
                [sys.executable, str(ROOT / "scripts" / "build_sandbox_score_delta_review_packet.py"), "--project-name", "demo"],
                timeout=120,
            )
        )
        steps.append(_run_step("governed_ingestion_batches", [sys.executable, str(ROOT / "scripts" / "build_governed_ingestion_batches.py")], timeout=120))
        steps.append(
            _run_step(
                "data_foundation_report",
                [sys.executable, str(ROOT / "scripts" / "build_data_foundation_report.py")],
                timeout=180,
            )
        )
        steps.append(
            _run_step(
                "data_foundation_gate",
                [sys.executable, str(ROOT / "scripts" / "check_data_foundation_gate.py")],
                timeout=120,
            )
        )
        steps.append(_run_step("native_ui_smoke", [sys.executable, str(ROOT / "run_native_ui.py"), "--smoke"], timeout=120))
        steps.append(_run_step("candidate_visual_compare", [sys.executable, str(ROOT / "scripts" / "build_candidate_visual_compare.py")], timeout=120))
        steps.append(_run_step("candidate_review_packet", [sys.executable, str(ROOT / "scripts" / "build_candidate_review_packet.py")], timeout=120))
        steps.append(_run_step("candidate_review_board", [sys.executable, str(ROOT / "scripts" / "build_candidate_review_board.py")], timeout=120))
        steps.append(_run_step("candidate_review_analytics", [sys.executable, str(ROOT / "scripts" / "build_candidate_review_analytics.py")], timeout=120))
        steps.append(_run_step("candidate_drilldown_packet", [sys.executable, str(ROOT / "scripts" / "build_candidate_drilldown_packet.py")], timeout=120))
        steps.append(_run_step("local_db_health", [sys.executable, str(ROOT / "scripts" / "build_local_db_health_report.py")], timeout=120))
        steps.append(_run_step("local_db_maintenance", [sys.executable, str(ROOT / "scripts" / "build_local_db_maintenance_report.py")], timeout=180))
        steps.append(
            _run_step(
                "named_governance_baseline",
                [sys.executable, str(ROOT / "scripts" / "build_local_governance_diff.py"), "--create-baseline", "--baseline-name", "default_current"],
                timeout=120,
            )
        )
        steps.append(_run_step("local_governance_diff", [sys.executable, str(ROOT / "scripts" / "build_local_governance_diff.py")], timeout=120))
        steps.append(
            _run_step(
                "candidate_baseline_compare",
                [sys.executable, str(ROOT / "scripts" / "compare_candidate_baseline.py"), "--baseline-id", "local_release_baseline", "--create-if-missing"],
                timeout=120,
            )
        )
        steps.append(_run_step("candidate_decision_packet", [sys.executable, str(ROOT / "scripts" / "build_candidate_decision_packet.py")], timeout=120))
        steps.append(_run_step("candidate_evidence_drawer", [sys.executable, str(ROOT / "scripts" / "build_candidate_evidence_drawer.py")], timeout=120))
        steps.append(_run_step("candidate_decision_qa", [sys.executable, str(ROOT / "scripts" / "build_candidate_decision_qa.py")], timeout=120))
        steps.append(_run_step("evidence_quality_scorecard", [sys.executable, str(ROOT / "scripts" / "build_evidence_quality_scorecard.py")], timeout=120))
        steps.append(_run_step("candidate_evidence_quality", [sys.executable, str(ROOT / "scripts" / "build_candidate_evidence_quality.py")], timeout=120))
        steps.append(_run_step("candidate_baseline_manager", [sys.executable, str(ROOT / "scripts" / "manage_candidate_baselines.py")], timeout=120))
        steps.append(_run_step("reviewer_operations", [sys.executable, str(ROOT / "scripts" / "build_reviewer_operations.py")], timeout=120))
        steps.append(_run_step("baseline_lineage_compare", [sys.executable, str(ROOT / "scripts" / "build_baseline_lineage_compare.py")], timeout=120))
        steps.append(_run_step("candidate_baseline_lineage", [sys.executable, str(ROOT / "scripts" / "build_candidate_baseline_lineage.py")], timeout=120))
        steps.append(_run_step("baseline_history_explorer", [sys.executable, str(ROOT / "scripts" / "build_baseline_history_explorer.py")], timeout=120))
        steps.append(_run_step("baseline_scenario_board", [sys.executable, str(ROOT / "scripts" / "build_baseline_scenario_board.py")], timeout=120))
        steps.append(_run_step("baseline_whatif_board", [sys.executable, str(ROOT / "scripts" / "build_baseline_whatif_board.py")], timeout=120))
        steps.append(_run_step("review_command_center", [sys.executable, str(ROOT / "scripts" / "build_review_command_center.py")], timeout=120))
        steps.append(_run_step("candidate_remediation_queue", [sys.executable, str(ROOT / "scripts" / "build_candidate_remediation_queue.py")], timeout=120))
        steps.append(_run_step("candidate_review_ops_console", [sys.executable, str(ROOT / "scripts" / "build_candidate_review_ops_console.py")], timeout=120))
        steps.append(_run_step("candidate_explanation_panel", [sys.executable, str(ROOT / "scripts" / "build_candidate_explanation_panel.py")], timeout=120))
        steps.append(_run_step("candidate_explanation_compare", [sys.executable, str(ROOT / "scripts" / "build_candidate_explanation_compare.py")], timeout=120))
        steps.append(_run_step("candidate_explanation_drilldown", [sys.executable, str(ROOT / "scripts" / "build_candidate_explanation_drilldown.py")], timeout=120))
        steps.append(_run_step("candidate_explanation_matrix", [sys.executable, str(ROOT / "scripts" / "build_candidate_explanation_matrix.py")], timeout=120))
        steps.append(_run_step("substituent_version_diff_browser", [sys.executable, str(ROOT / "scripts" / "build_substituent_version_diff_browser.py")], timeout=120))
        steps.append(_run_step("operator_trend_summary", [sys.executable, str(ROOT / "scripts" / "build_operator_trend_summary.py")], timeout=120))
        steps.append(_run_step("operator_trend_charts", [sys.executable, str(ROOT / "scripts" / "build_operator_trend_charts.py")], timeout=120))
        steps.append(_run_step("medchem_discussion_handoff", [sys.executable, str(ROOT / "scripts" / "build_medchem_discussion_handoff.py")], timeout=120))
        steps.append(
            _run_step(
                "native_ui_regression_snapshot",
                [sys.executable, str(ROOT / "scripts" / "build_native_ui_regression_snapshot.py")],
                timeout=120,
            )
        )
        steps.append(
            _run_step(
                "release_smoke_checklist",
                [sys.executable, str(ROOT / "scripts" / "build_release_smoke_checklist.py")],
                timeout=120,
            )
        )
        steps.append(
            _run_step(
                "weekly_release_diff_summary",
                [sys.executable, str(ROOT / "scripts" / "build_weekly_release_diff_summary.py")],
                timeout=120,
            )
        )
        steps.append(_run_step("write_launchers", [sys.executable, str(ROOT / "scripts" / "write_launcher.py")], timeout=60))
        steps.append(
            _run_step(
                "write_data_automation_templates",
                [sys.executable, str(ROOT / "scripts" / "write_data_automation_templates.py")],
                timeout=60,
            )
        )
        if not args.skip_browser:
            steps.append(_browser_smoke(_find_free_port(args.port)))
        bundle = create_release_bundle(
            ROOT,
            bundle_out,
            extra_metadata={"ci_step_count": len(steps), "browser_smoke": not args.skip_browser},
        )
        bundle["checksum"] = write_latest_release_checksum_report(bundle["bundle_path"], ROOT / "data" / "releases" / "latest_release_checksum.json")
        steps.extend(_bundle_smoke(bundle["bundle_path"], args.port + 20, include_browser=not args.skip_browser))
    except Exception as exc:
        failed = str(exc)
        bundle = None

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ok": failed is None,
        "failed": failed,
        "steps": steps,
        "bundle": bundle,
    }
    write_release_bundle_report(report, args.report_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if failed is not None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
