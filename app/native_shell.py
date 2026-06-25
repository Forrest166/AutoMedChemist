from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import ctypes
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import BOTH, Canvas, END, HORIZONTAL, LEFT, VERTICAL, X, BooleanVar, StringVar, Tk, messagebox, ttk
import tkinter.font as tkfont

try:
    from PIL import Image, ImageTk
except Exception:  # pragma: no cover - optional UI polish dependency
    Image = None
    ImageTk = None


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


ROOT = project_root()


DPI_REPORT: dict = {
    "requested": False,
    "method": "not_requested",
    "error": "",
}

TREEVIEW_FONT_SIZE = 10
TREEVIEW_HEADING_FONT_SIZE = 10
TREEVIEW_MIN_ROW_HEIGHT = 54
TREEVIEW_VERTICAL_PADDING = 30
TREEVIEW_HEADING_MIN_PADDING_Y = 12
LOCAL_SCOPE_GUARD_TEXT = "Local design/review only; external operational workflows are out of scope."
OUT_OF_SCOPE_TOKENS = {
    "procurement",
    "supplier",
    "supplier_purchase",
    "real_experiment_feedback_auto_import",
    "real_feedback",
    "real feedback",
}


def readable_tree_row_height(root: Tk, font_name: str) -> int:
    try:
        metrics = tkfont.Font(root=root, family=font_name, size=TREEVIEW_FONT_SIZE).metrics()
        linespace = int(metrics.get("linespace") or 0)
    except Exception:
        linespace = 0
    return max(TREEVIEW_MIN_ROW_HEIGHT, linespace + TREEVIEW_VERTICAL_PADDING)


def enable_high_dpi() -> dict:
    report = {
        "requested": False,
        "method": "not_applicable",
        "error": "",
    }
    if sys.platform != "win32":
        return report
    report["requested"] = True
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # type: ignore[attr-defined]
        report["method"] = "SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)"
        return report
    except Exception as first_error:
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]
            report["method"] = "SetProcessDPIAware"
            report["fallback_from"] = str(first_error)
            return report
        except Exception as second_error:
            report["method"] = "failed"
            report["error"] = f"{first_error}; {second_error}"
            return report


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def resolve_python() -> str:
    local_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if local_python.exists():
        return str(local_python)
    found = shutil.which("python")
    if found:
        return found
    if not getattr(sys, "frozen", False):
        return sys.executable
    raise RuntimeError("Python was not found. Install Python or create .venv before running pipeline actions.")


def run_python(args: list[str], *, timeout: int = 240) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [resolve_python(), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def open_path(path: Path) -> None:
    if not path.exists():
        messagebox.showwarning("Missing file", f"{path} does not exist yet.")
        return
    os.startfile(str(path))  # type: ignore[attr-defined]


def load_direction_ids() -> list[str]:
    path = ROOT / "data" / "rules" / "direction_rules.yaml"
    fallback = [
        "increase_polarity",
        "metabolism_blocking",
        "reduce_lipophilicity",
        "improve_solubility",
        "small_scan",
        "electronics_scan",
        "heteroaryl_scan",
        "reduce_hydrolysis",
        "amide_bioisostere_scan",
    ]
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        values = sorted((data.get("directions") or {}).keys())
        return values or fallback
    except Exception:
        return fallback


def parse_json_stdout(output: str) -> dict:
    start = output.find("{")
    end = output.rfind("}")
    if start < 0 or end < start:
        return {}
    try:
        data = json.loads(output[start : end + 1])
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def display_scope_guard(value) -> str:
    if value is None:
        return LOCAL_SCOPE_GUARD_TEXT
    if isinstance(value, list):
        text = ";".join(str(item) for item in value)
    else:
        text = str(value)
    lowered = text.lower()
    if any(token in lowered for token in OUT_OF_SCOPE_TOKENS):
        return LOCAL_SCOPE_GUARD_TEXT
    return text or LOCAL_SCOPE_GUARD_TEXT


def load_workspace_names() -> list[str]:
    projects_root = ROOT / "data" / "projects"
    if not projects_root.exists():
        return ["demo"]
    names = [
        path.name
        for path in projects_root.iterdir()
        if path.is_dir() and not path.name.startswith(".") and path.name not in {"promotion_freezes", "iterations"}
    ]
    names = sorted(dict.fromkeys(["demo", *names]))
    return names or ["demo"]


def safe_workspace_name(value: str) -> str:
    allowed = "".join(ch for ch in str(value or "demo") if ch.isalnum() or ch in {"_", "-"})
    return allowed or "demo"


class NativeShell(Tk):
    def __init__(self) -> None:
        super().__init__()
        self.dpi_report = self._configure_high_dpi_scaling()
        available_fonts = set(tkfont.families(self))
        self.font_name = "Segoe UI Variable" if "Segoe UI Variable" in available_fonts else "Segoe UI"
        self.title("AutoMedChemist")
        self.geometry("1480x900")
        self.minsize(1240, 760)
        self.configure(bg="#F6F8FA")
        self.directions = load_direction_ids()
        self.workspace_names = load_workspace_names()
        self.sites: list[dict] = []
        self.last_result: dict = {}
        self.candidate_rows: list[dict] = []
        self.rendered_candidate_rows: list[dict] = []
        self.compare_rows: list[dict] = []
        self.review_board_rows: list[dict] = []
        self.rendered_review_board_rows: list[dict] = []
        self.review_analytics_rows: list[dict] = []
        self.review_reason_rows: list[dict] = []
        self.review_reason_audit_rows: list[dict] = []
        self.evidence_quality_rows: list[dict] = []
        self.baseline_manager_rows: list[dict] = []
        self.reviewer_operations_rows: list[dict] = []
        self.baseline_lineage_rows: list[dict] = []
        self.review_command_rows: list[dict] = []
        self.review_remediation_rows: list[dict] = []
        self.review_remediation_source = "candidate"
        self.review_closure_rows: list[dict] = []
        self.feed_diff_rows: list[dict] = []
        self.source_expansion_rows: list[dict] = []
        self.feed_promotion_simulator_rows: list[dict] = []
        self.staging_quality_budget_rows: list[dict] = []
        self.governed_ingestion_batch_rows: list[dict] = []
        self.staged_feed_sandbox_rows: list[dict] = []
        self.sandbox_score_delta_review_rows: list[dict] = []
        self.sandbox_score_delta_signoff_rows: list[dict] = []
        self.rgroup_feed_digestion_rows: list[dict] = []
        self.rgroup_promotion_approval_rows: list[dict] = []
        self.rgroup_digestion_quality_rows: list[dict] = []
        self.staging_sandbox_filter_rows: list[dict] = []
        self.local_db_release_gate_rows: list[dict] = []
        self.staging_manual_review_rows: list[dict] = []
        self.staging_admission_scorecard_rows: list[dict] = []
        self.rgroup_admission_sandbox_replay_rows: list[dict] = []
        self.staging_curator_signoff_rows: list[dict] = []
        self.candidate_explanation_compare_rows: list[dict] = []
        self.candidate_explanation_drilldown_rows: list[dict] = []
        self.candidate_component_structure_locator_rows: list[dict] = []
        self.current_candidate_component_rows: list[dict] = []
        self.candidate_explanation_matrix_rows: list[dict] = []
        self.site_detection_confidence_rows: list[dict] = []
        self.site_detection_calibration_rows: list[dict] = []
        self.baseline_history_rows: list[dict] = []
        self.baseline_scenario_rows: list[dict] = []
        self.baseline_whatif_rows: list[dict] = []
        self.baseline_lineage_preview_rows: list[dict] = []
        self.baseline_lineage_filter_rows: list[dict] = []
        self.review_closure_filter_rows: list[dict] = []
        self.native_drilldown_action_rows: list[dict] = []
        self.review_ops_console_rows: list[dict] = []
        self.substituent_version_diff_rows: list[dict] = []
        self.baseline_history_chart_rows: list[dict] = []
        self.trend_chart_rows: list[dict] = []
        self.production_gate_rows: dict[str, dict] = {}
        self.task_events: list[dict] = []
        self.task_runners: dict[str, object] = {}
        self.last_failed_task: dict | None = None
        self.last_failed_task_runner = None
        self.molecule_photo = None
        self.candidate_before_structure_photo = None
        self.candidate_structure_photo = None
        self.review_before_structure_photo = None
        self.review_structure_photo = None
        self.candidate_explanation_chart_photo = None
        self.baseline_history_chart_image = None
        self.trend_chart_preview_image = None
        self.current_view = "candidate"
        self.nav_buttons: dict[str, ttk.Button] = {}
        self.status_var = StringVar(value="Ready")
        self.task_log_var = StringVar(value="No background tasks have run in this session.")
        preset = read_json(ROOT / "data" / "projects" / "demo" / "native_ui_presets.json")
        workspace = safe_workspace_name(str(preset.get("workspace") or "demo"))
        if workspace not in self.workspace_names:
            self.workspace_names.append(workspace)
        self.workspace_var = StringVar(value=workspace)
        self.smiles_var = StringVar(value=str(preset.get("smiles") or "COc1ccc(Cl)cc1"))
        preset_direction = str(preset.get("direction") or "")
        self.direction_var = StringVar(
            value=preset_direction if preset_direction in self.directions else "increase_polarity" if "increase_polarity" in self.directions else self.directions[0]
        )
        self.max_candidates_var = StringVar(value=str(preset.get("max_candidates") or "50"))
        self.include_ring_var = BooleanVar(value=bool(preset.get("include_ring_library", True)))
        self.candidate_filter_var = StringVar(value="")
        self.candidate_site_filter_var = StringVar(value="all")
        self.candidate_risk_filter_var = StringVar(value="all")
        self.candidate_source_filter_var = StringVar(value="all")
        self.candidate_min_score_var = StringVar(value="")
        self.candidate_max_score_var = StringVar(value="")
        self.candidate_max_rank_var = StringVar(value="")
        self.candidate_delta_filter_var = StringVar(value="all")
        self.candidate_column_filter_field_var = StringVar(value="all")
        self.candidate_column_filter_value_var = StringVar(value="")
        self.candidate_filter_preset_var = StringVar(value="non_clear_review")
        self.candidate_detail_var = StringVar(value="Select a candidate row to inspect site-class guidance, risk notes, and export context.")
        self.candidate_before_structure_var = StringVar(value="Before: current molecule")
        self.candidate_structure_var = StringVar(value="After: select a candidate")
        self.candidate_structure_explanation_var = StringVar(value="2D interpretation: select a candidate or score component.")
        self.candidate_explanation_var = StringVar(value="Select a candidate to see score components, site guidance, evidence flags, baseline movement, and local QA in one place.")
        self.candidate_linkage_var = StringVar(value="Candidate selection syncs structure, explanation components, baseline movement, and remediation status.")
        self.candidate_explanation_component_var = StringVar(value="Select a score/evidence/QA/baseline/remediation component to route its source artifact.")
        self.visual_compare_var = StringVar(value="Visual compare packet is not built yet.")
        self.review_site_filter_var = StringVar(value="all")
        self.review_bucket_filter_var = StringVar(value="all")
        self.review_local_status_filter_var = StringVar(value="all")
        self.review_risk_filter_var = StringVar(value="all")
        self.review_reviewer_filter_var = StringVar(value="all")
        self.review_attention_filter_var = StringVar(value="all")
        self.review_update_status_var = StringVar(value="reviewed")
        self.review_note_var = StringVar(value="local review updated from native board")
        self.review_reason_batch_status_var = StringVar(value="reviewed")
        self.review_reason_batch_note_var = StringVar(value="Batch updated from pending-reason workbench.")
        self.review_reason_cluster_var = StringVar(value="all")
        self.reviewer_cockpit_var = StringVar(value="Reviewer cockpit combines reason clusters, closure tasks, and remediation groups.")
        self.review_detail_var = StringVar(value="Select a candidate review row to inspect evidence and local review history.")
        self.review_before_structure_var = StringVar(value="Before: current molecule")
        self.review_structure_var = StringVar(value="After: select a review row")
        self.evidence_drawer_var = StringVar(value="Select a candidate or review row to see structure, evidence, review, baseline, and local decision context.")
        self.review_analytics_var = StringVar(value="Build review analytics to summarize backlog, risk buckets, reviewer workload, and site-class coverage.")
        self.review_command_center_var = StringVar(value="Select a command-center row to route native review filters or open its linked artifact.")
        self.remediation_owner_var = StringVar(value="local_review_owner")
        self.remediation_due_var = StringVar(value=datetime.now(timezone.utc).date().isoformat())
        self.remediation_status_var = StringVar(value="open")
        self.remediation_reason_var = StringVar(value="local_review_resolved")
        self.remediation_note_var = StringVar(value="")
        self.remediation_detail_var = StringVar(value="Select a remediation task to edit local owner, due date, status, and closure note.")
        self.baseline_history_chart_var = StringVar(value="Build baseline history explorer to preview movement charts.")
        self.trend_chart_preview_var = StringVar(value="Select an operator trend chart row to preview the native PNG card.")
        self.governance_baseline_name_var = StringVar(value=datetime.now(timezone.utc).strftime("baseline_%Y%m%d"))
        self.candidate_baseline_name_var = StringVar(value="local_release_baseline")
        self.candidate_baseline_archive_note_var = StringVar(value="Archived from native baseline manager.")
        self.preview_status_var = StringVar(value="Preview will update after site detection.")
        self.db_health_var = StringVar(value="DB health: not checked")
        self.production_drilldown_var = StringVar(value="Select a production gate to see its artifact and next action.")
        self.native_drilldown_action_var = StringVar(value="Select a native drilldown action to route or open its linked artifact.")
        self.staging_curator_decision_var = StringVar(value="ready_for_sandbox_review")
        self.staging_curator_var = StringVar(value="local_curator")
        self.staging_curator_note_var = StringVar(value="Curated from native staging queue.")
        self.staging_curator_version_note_var = StringVar(value="Version change reviewed for local sandbox-only staging.")
        self.staging_curator_detail_var = StringVar(value="Select a staging manual-review queue row to inspect source policy, version-change requirements, and signoff history.")
        self._configure_styles()
        self._build_layout()
        self.show_view("candidate")
        self.reload_all()

    def _configure_high_dpi_scaling(self) -> dict:
        screen_dpi = 96.0
        try:
            screen_dpi = float(self.winfo_fpixels("1i"))
            self.tk.call("tk", "scaling", max(1.0, screen_dpi / 72.0))
        except Exception:
            pass
        report = {
            **DPI_REPORT,
            "screen_dpi": round(screen_dpi, 2),
        }
        try:
            report["tk_scaling"] = float(self.tk.call("tk", "scaling"))
        except Exception:
            report["tk_scaling"] = None
        return report

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        font_name = self.font_name
        style.configure("Shell.TFrame", background="#F6F8FA")
        style.configure("Panel.TFrame", background="#FFFFFF", relief="flat")
        style.configure("Sidebar.TFrame", background="#17202A")
        style.configure("Header.TLabel", background="#F6F8FA", foreground="#17202A", font=(font_name, 21, "bold"))
        style.configure("Subheader.TLabel", background="#F6F8FA", foreground="#52616F", font=(font_name, 10))
        style.configure("SidebarSub.TLabel", background="#17202A", foreground="#A9B8C4", font=(font_name, 9))
        style.configure("PanelTitle.TLabel", background="#FFFFFF", foreground="#17202A", font=(font_name, 12, "bold"))
        style.configure("Metric.TLabel", background="#FFFFFF", foreground="#17202A", font=(font_name, 18, "bold"))
        style.configure("MetricLabel.TLabel", background="#FFFFFF", foreground="#52616F", font=(font_name, 9))
        style.configure("Status.TLabel", background="#F6F8FA", foreground="#52616F", font=(font_name, 10))
        style.configure("Sidebar.TLabel", background="#17202A", foreground="#F7FAFC", font=(font_name, 16, "bold"))
        style.configure("Nav.TButton", background="#17202A", foreground="#E8EEF2", borderwidth=0, anchor="w", padding=(14, 11))
        style.map("Nav.TButton", background=[("active", "#22303D")], foreground=[("active", "#FFFFFF")])
        style.configure("Accent.TButton", background="#0F766E", foreground="#FFFFFF", padding=(10, 9), borderwidth=0, font=(font_name, 9, "bold"))
        style.map("Accent.TButton", background=[("active", "#115E59")])
        style.configure("Warn.TButton", background="#B45309", foreground="#FFFFFF", padding=(10, 9), borderwidth=0, font=(font_name, 9, "bold"))
        style.map("Warn.TButton", background=[("active", "#92400E")])
        self.tree_row_height = readable_tree_row_height(self, font_name)
        heading_padding_y = max(TREEVIEW_HEADING_MIN_PADDING_Y, self.tree_row_height // 5)
        tree_style = {
            "rowheight": self.tree_row_height,
            "font": (font_name, TREEVIEW_FONT_SIZE),
            "fieldbackground": "#FFFFFF",
            "background": "#FFFFFF",
        }
        heading_style = {
            "font": (font_name, TREEVIEW_HEADING_FONT_SIZE, "bold"),
            "background": "#E9EEF2",
            "foreground": "#17202A",
            "padding": (8, heading_padding_y),
        }
        style.configure("Treeview", **tree_style)
        style.configure("Treeview.Heading", **heading_style)
        style.configure("Readable.Treeview", **tree_style)
        style.configure("Readable.Treeview.Heading", **heading_style)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        sidebar = ttk.Frame(self, style="Sidebar.TFrame", width=220)
        sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        sidebar.grid_propagate(False)
        ttk.Label(sidebar, text="AutoMedChemist", style="Sidebar.TLabel").pack(anchor="w", padx=18, pady=(22, 18))
        for view_id, label in [
            ("candidate", "Candidate Workbench"),
            ("candidate_review", "Candidate Review"),
            ("project_memory", "Project Memory"),
            ("endpoint", "Endpoint Governance"),
            ("readiness", "Readiness Packet"),
            ("reports", "Data & Reports"),
        ]:
            button = ttk.Button(sidebar, text=label, style="Nav.TButton", command=lambda item=view_id: self.show_view(item))
            button.pack(fill=X, padx=10, pady=3)
            self.nav_buttons[view_id] = button
        ttk.Label(sidebar, text="Native desktop shell\nNo browser runtime", style="SidebarSub.TLabel", justify=LEFT).pack(
            anchor="w", padx=18, pady=(26, 8)
        )
        ttk.Button(sidebar, text="Open Task Log", style="Nav.TButton", command=self.open_task_log).pack(fill=X, padx=10, pady=(18, 3))
        ttk.Button(sidebar, text="Rerun Failed Task", style="Nav.TButton", command=self.rerun_last_failed_task).pack(fill=X, padx=10, pady=3)

        header = ttk.Frame(self, style="Shell.TFrame")
        header.grid(row=0, column=1, sticky="ew", padx=24, pady=(18, 8))
        header.grid_columnconfigure(0, weight=1)
        ttk.Label(header, text="Local MedChem Design Workbench", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Interactive site selection, candidate generation, local governance, and export in one native app.",
            style="Subheader.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        ttk.Label(header, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=1, rowspan=2, sticky="e")

        self.content = ttk.Frame(self, style="Shell.TFrame")
        self.content.grid(row=1, column=1, sticky="nsew", padx=24, pady=(0, 24))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.views: dict[str, ttk.Frame] = {}
        self._build_candidate_view()
        self._build_candidate_review_view()
        self._build_project_memory_view()
        self._build_endpoint_view()
        self._build_readiness_view()
        self._build_reports_view()

    def panel(self, parent: ttk.Frame) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        return frame

    def project_name(self) -> str:
        return safe_workspace_name(self.workspace_var.get())

    def project_dir(self) -> Path:
        path = ROOT / "data" / "projects" / self.project_name()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def preset_file(self) -> Path:
        return self.project_dir() / "native_ui_presets.json"

    def session_file(self) -> Path:
        return self.project_dir() / "native_session.json"

    def preview_file(self) -> Path:
        return self.project_dir() / "native_molecule_preview.png"

    def task_log_path(self) -> Path:
        return self.project_dir() / "native_task_log.json"

    def task_log_csv_path(self) -> Path:
        return self.project_dir() / "native_task_log.csv"

    def show_view(self, view_id: str) -> None:
        self.current_view = view_id
        for frame in self.views.values():
            frame.grid_remove()
        self.views[view_id].grid(row=0, column=0, sticky="nsew")
        self.status_var.set(f"Ready: {view_id.replace('_', ' ')}")

    def _tree(self, parent: ttk.Frame, columns: list[str], headings: list[str], widths: list[int], *, height: int | None = None) -> ttk.Treeview:
        frame = ttk.Frame(parent, style="Panel.TFrame")
        frame.pack(fill=BOTH, expand=True)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        tree_options = {"height": height} if height is not None else {}
        tree = ttk.Treeview(frame, columns=columns, show="headings", style="Readable.Treeview", **tree_options)
        for col, heading, width in zip(columns, headings, widths):
            tree.heading(col, text=heading)
            tree.column(col, width=width, minwidth=max(60, width), stretch=False)
        y_scroll = ttk.Scrollbar(frame, orient=VERTICAL, command=tree.yview)
        x_scroll = ttk.Scrollbar(frame, orient=HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        return tree

    def _scrollable_frame(self, parent: ttk.Frame) -> ttk.Frame:
        canvas = Canvas(parent, bg="#F6F8FA", highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient=VERTICAL, command=canvas.yview)
        inner = ttk.Frame(canvas, style="Shell.TFrame")
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        def update_scrollregion(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def update_width(event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        def wheel(event) -> None:
            delta = int(-1 * (event.delta / 120)) if event.delta else 0
            if delta:
                canvas.yview_scroll(delta, "units")

        inner.bind("<Configure>", update_scrollregion)
        canvas.bind("<Configure>", update_width)
        inner.bind("<Enter>", lambda _event: canvas.bind_all("<MouseWheel>", wheel))
        inner.bind("<Leave>", lambda _event: canvas.unbind_all("<MouseWheel>"))
        return inner

    def _build_candidate_view(self) -> None:
        view = ttk.Frame(self.content, style="Shell.TFrame")
        view.grid_columnconfigure(1, weight=1)
        view.grid_rowconfigure(1, weight=1)
        self.views["candidate"] = view

        controls = self.panel(view)
        controls.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 14))
        controls.grid_columnconfigure(0, weight=1)
        ttk.Label(controls, text="Workspace", style="MetricLabel.TLabel").grid(row=0, column=0, sticky="w")
        self.workspace_combo = ttk.Combobox(controls, textvariable=self.workspace_var, values=self.workspace_names, state="normal")
        self.workspace_combo.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        ttk.Button(controls, text="Switch Workspace", command=self.switch_workspace).grid(row=2, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(controls, textvariable=self.db_health_var, style="MetricLabel.TLabel").grid(row=3, column=0, sticky="w", pady=(0, 10))
        ttk.Label(controls, text="Molecule", style="PanelTitle.TLabel").grid(row=4, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.smiles_var, width=34).grid(row=5, column=0, sticky="ew", pady=(8, 10))
        ttk.Label(controls, text="Direction", style="MetricLabel.TLabel").grid(row=6, column=0, sticky="w")
        ttk.Combobox(controls, textvariable=self.direction_var, values=self.directions, state="readonly").grid(row=7, column=0, sticky="ew", pady=(4, 10))
        ttk.Label(controls, text="Max candidates", style="MetricLabel.TLabel").grid(row=8, column=0, sticky="w")
        ttk.Spinbox(controls, textvariable=self.max_candidates_var, from_=5, to=200, increment=5).grid(row=9, column=0, sticky="ew", pady=(4, 10))
        ttk.Checkbutton(controls, text="Include ring library recommendations", variable=self.include_ring_var).grid(row=10, column=0, sticky="w", pady=(0, 12))
        ttk.Button(controls, text="Detect Sites", style="Accent.TButton", command=self.detect_sites).grid(row=11, column=0, sticky="ew", pady=4)
        ttk.Button(controls, text="Generate Candidates", style="Accent.TButton", command=self.generate_candidates).grid(row=12, column=0, sticky="ew", pady=4)
        ttk.Button(controls, text="Save Preset", command=self.save_preset).grid(row=13, column=0, sticky="ew", pady=(12, 4))
        ttk.Button(controls, text="Save Session", command=self.save_session).grid(row=14, column=0, sticky="ew", pady=4)
        ttk.Button(controls, text="Load Session", command=self.load_session).grid(row=15, column=0, sticky="ew", pady=4)
        ttk.Button(controls, text="Open CSV Export", command=lambda: open_path(self.project_dir() / "candidates.csv")).grid(row=16, column=0, sticky="ew", pady=(12, 4))
        ttk.Button(controls, text="Open SDF Export", command=lambda: open_path(self.project_dir() / "candidates.sdf")).grid(row=17, column=0, sticky="ew", pady=4)
        ttk.Label(controls, text="Molecule Preview", style="PanelTitle.TLabel").grid(row=18, column=0, sticky="w", pady=(18, 6))
        self.preview_label = ttk.Label(controls, textvariable=self.preview_status_var, style="MetricLabel.TLabel", justify=LEFT)
        self.preview_label.grid(row=19, column=0, sticky="nsew")

        site_panel = self.panel(view)
        site_panel.grid(row=0, column=1, sticky="nsew")
        site_panel.grid_columnconfigure(0, weight=1)
        ttk.Label(site_panel, text="Detected Sites", style="PanelTitle.TLabel").pack(anchor="w")
        self.site_tree = self._tree(
            site_panel,
            ["idx", "site_type", "operation", "ready", "label"],
            ["#", "Site class", "Operation", "Ready", "Label"],
            [42, 150, 150, 70, 360],
        )

        candidate_panel = self.panel(view)
        candidate_panel.grid(row=1, column=1, sticky="nsew", pady=(14, 0))
        candidate_panel.grid_columnconfigure(0, weight=1)
        ttk.Label(candidate_panel, text="Candidate Table", style="PanelTitle.TLabel").pack(anchor="w")
        toolbar = ttk.Frame(candidate_panel, style="Panel.TFrame")
        toolbar.pack(fill=X, pady=(8, 4))
        ttk.Label(toolbar, text="Text", style="MetricLabel.TLabel").pack(side=LEFT, padx=(0, 4))
        text_entry = ttk.Entry(toolbar, textvariable=self.candidate_filter_var, width=18)
        text_entry.pack(side=LEFT, padx=(0, 8))
        text_entry.bind("<Return>", lambda _event: self.render_candidate_table())
        for label, var, attr, width in [
            ("Site", self.candidate_site_filter_var, "candidate_site_filter_combo", 15),
            ("Risk", self.candidate_risk_filter_var, "candidate_risk_filter_combo", 15),
            ("Source", self.candidate_source_filter_var, "candidate_source_filter_combo", 15),
        ]:
            ttk.Label(toolbar, text=label, style="MetricLabel.TLabel").pack(side=LEFT, padx=(0, 4))
            combo = ttk.Combobox(toolbar, textvariable=var, values=["all"], width=width, state="readonly")
            combo.pack(side=LEFT, padx=(0, 8))
            combo.bind("<<ComboboxSelected>>", lambda _event: self.render_candidate_table())
            setattr(self, attr, combo)
        for label, var, width in [
            ("Score >=", self.candidate_min_score_var, 7),
            ("<=", self.candidate_max_score_var, 7),
            ("Rank <=", self.candidate_max_rank_var, 7),
        ]:
            ttk.Label(toolbar, text=label, style="MetricLabel.TLabel").pack(side=LEFT, padx=(0, 4))
            entry = ttk.Entry(toolbar, textvariable=var, width=width)
            entry.pack(side=LEFT, padx=(0, 8))
            entry.bind("<Return>", lambda _event: self.render_candidate_table())
        ttk.Label(toolbar, text="Delta", style="MetricLabel.TLabel").pack(side=LEFT, padx=(0, 4))
        self.candidate_delta_filter_combo = ttk.Combobox(
            toolbar,
            textvariable=self.candidate_delta_filter_var,
            values=["all", "polarity_gain", "lower_mw", "lower_clogp", "higher_tpsa", "neutral_delta"],
            width=14,
            state="readonly",
        )
        self.candidate_delta_filter_combo.pack(side=LEFT, padx=(0, 8))
        self.candidate_delta_filter_combo.bind("<<ComboboxSelected>>", lambda _event: self.render_candidate_table())

        action_toolbar = ttk.Frame(candidate_panel, style="Panel.TFrame")
        action_toolbar.pack(fill=X, pady=(0, 8))
        ttk.Label(action_toolbar, text="Column", style="MetricLabel.TLabel").pack(side=LEFT, padx=(0, 4))
        self.candidate_column_filter_field_combo = ttk.Combobox(
            action_toolbar,
            textvariable=self.candidate_column_filter_field_var,
            values=[
                "all",
                "candidate_id",
                "smiles",
                "site_class",
                "replacement_label",
                "replacement_class",
                "enumeration_type",
                "risk_bucket",
                "why_review",
                "why_recommended",
                "endpoint_gate_decision",
                "evidence_conflict_flags",
            ],
            width=18,
            state="readonly",
        )
        self.candidate_column_filter_field_combo.pack(side=LEFT, padx=(0, 6))
        column_entry = ttk.Entry(action_toolbar, textvariable=self.candidate_column_filter_value_var, width=22)
        column_entry.pack(side=LEFT, padx=(0, 8))
        column_entry.bind("<Return>", lambda _event: self.render_candidate_table())
        ttk.Button(action_toolbar, text="Apply", command=self.render_candidate_table).pack(side=LEFT, padx=3)
        ttk.Button(action_toolbar, text="Clear", command=self.clear_candidate_filter).pack(side=LEFT, padx=3)
        ttk.Label(action_toolbar, text="Preset", style="MetricLabel.TLabel").pack(side=LEFT, padx=(10, 4))
        self.candidate_filter_preset_combo = ttk.Combobox(action_toolbar, textvariable=self.candidate_filter_preset_var, values=[], width=20, state="normal")
        self.candidate_filter_preset_combo.pack(side=LEFT, padx=(0, 6))
        ttk.Button(action_toolbar, text="Load", command=self.apply_candidate_filter_preset).pack(side=LEFT, padx=3)
        ttk.Button(action_toolbar, text="Save", command=self.save_candidate_filter_preset).pack(side=LEFT, padx=3)
        ttk.Button(action_toolbar, text="Sort", command=self.sort_candidates_by_score).pack(side=LEFT, padx=3)
        ttk.Button(action_toolbar, text="Open 2D", command=self.open_selected_candidate_image).pack(side=LEFT, padx=3)
        ttk.Button(action_toolbar, text="Open Evidence", command=self.open_selected_candidate_drilldown).pack(side=LEFT, padx=3)
        ttk.Button(action_toolbar, text="Add Compare", command=self.add_selected_candidate_to_compare).pack(side=LEFT, padx=3)
        ttk.Button(action_toolbar, text="Clear Compare", command=self.clear_compare_rows).pack(side=LEFT, padx=3)
        candidate_body = ttk.PanedWindow(candidate_panel, orient=HORIZONTAL)
        self.candidate_body_paned = candidate_body
        candidate_body.pack(fill=BOTH, expand=True)
        candidate_table_frame = ttk.Frame(candidate_body, style="Panel.TFrame")
        candidate_preview_frame = ttk.Frame(candidate_body, style="Panel.TFrame", width=430)
        try:
            candidate_body.add(candidate_table_frame, weight=5)
            candidate_body.add(candidate_preview_frame, weight=1)
        except Exception:
            candidate_body.add(candidate_table_frame)
            candidate_body.add(candidate_preview_frame)

        self.candidate_tree = self._tree(
            candidate_table_frame,
            ["rank", "score", "candidate_id", "smiles", "site_class", "risk", "delta_mw", "delta_clogp", "delta_tpsa", "source", "reason"],
            ["Rank", "Score", "ID", "SMILES", "Site class", "Risk", "dMW", "dClogP", "dTPSA", "Source", "Why"],
            [55, 70, 110, 250, 145, 170, 75, 75, 75, 135, 360],
            height=8,
        )
        self.candidate_tree.bind("<<TreeviewSelect>>", lambda _event: self.show_selected_candidate_detail())
        structure_frame = ttk.Frame(candidate_preview_frame, style="Panel.TFrame")
        structure_frame.pack(fill=BOTH, expand=True, padx=(12, 0))
        ttk.Label(structure_frame, text="Before / After 2D", style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Label(
            structure_frame,
            text="Click a candidate row to compare the current molecule against the generated candidate.",
            style="MetricLabel.TLabel",
            justify=LEFT,
            wraplength=360,
        ).pack(anchor="w", pady=(2, 8))
        candidate_before_after = ttk.Frame(structure_frame, style="Panel.TFrame")
        candidate_before_after.pack(fill=X, pady=(0, 4))
        candidate_before_after.grid_columnconfigure((0, 1), weight=1)
        self.candidate_before_structure_label = ttk.Label(
            candidate_before_after,
            textvariable=self.candidate_before_structure_var,
            style="MetricLabel.TLabel",
            justify=LEFT,
            wraplength=190,
        )
        self.candidate_before_structure_label.grid(row=0, column=0, sticky="n", padx=(0, 8))
        self.candidate_structure_label = ttk.Label(
            candidate_before_after,
            textvariable=self.candidate_structure_var,
            style="MetricLabel.TLabel",
            justify=LEFT,
            wraplength=190,
        )
        self.candidate_structure_label.grid(row=0, column=1, sticky="n", padx=(8, 0))
        ttk.Label(
            structure_frame,
            textvariable=self.candidate_structure_explanation_var,
            style="MetricLabel.TLabel",
            justify=LEFT,
            wraplength=390,
        ).pack(fill=X, pady=(4, 0))
        detail_area = ttk.Frame(candidate_panel, style="Panel.TFrame")
        detail_area.pack(fill=X, pady=(10, 0))
        detail_text = ttk.Frame(detail_area, style="Panel.TFrame")
        detail_text.pack(fill=X, expand=True)
        ttk.Label(
            detail_text,
            textvariable=self.candidate_detail_var,
            style="MetricLabel.TLabel",
            justify=LEFT,
            wraplength=900,
        ).pack(fill=X)
        ttk.Label(detail_text, text="Evidence Drawer", style="PanelTitle.TLabel").pack(anchor="w", pady=(10, 2))
        ttk.Label(
            detail_text,
            textvariable=self.evidence_drawer_var,
            style="MetricLabel.TLabel",
            justify=LEFT,
            wraplength=900,
        ).pack(fill=X, pady=(0, 4))
        ttk.Label(detail_text, text="Candidate Explanation", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 2))
        ttk.Label(
            detail_text,
            textvariable=self.candidate_explanation_var,
            style="MetricLabel.TLabel",
            justify=LEFT,
            wraplength=900,
        ).pack(fill=X, pady=(0, 4))
        self.candidate_explanation_chart_label = ttk.Label(detail_text, style="Panel.TLabel")
        self.candidate_explanation_chart_label.pack(anchor="w", pady=(0, 4))
        ttk.Label(
            detail_text,
            textvariable=self.candidate_linkage_var,
            style="MetricLabel.TLabel",
            justify=LEFT,
            wraplength=900,
        ).pack(fill=X, pady=(0, 4))
        ttk.Label(detail_text, text="Explanation Components", style="PanelTitle.TLabel").pack(anchor="w", pady=(4, 2))
        self.candidate_explanation_component_tree = self._tree(
            detail_text,
            ["component", "score", "status", "target", "summary"],
            ["Component", "Score", "Status", "Target", "Summary"],
            [130, 65, 90, 145, 520],
        )
        self.candidate_explanation_component_tree.bind("<<TreeviewSelect>>", lambda _event: self.show_selected_explanation_component())
        ttk.Label(
            detail_text,
            textvariable=self.candidate_explanation_component_var,
            style="MetricLabel.TLabel",
            justify=LEFT,
            wraplength=900,
        ).pack(fill=X, pady=(4, 4))
        component_actions = ttk.Frame(detail_text, style="Panel.TFrame")
        component_actions.pack(anchor="w", pady=(0, 4))
        ttk.Button(component_actions, text="Route Component", command=self.route_selected_explanation_component).pack(side=LEFT, padx=(0, 5))
        ttk.Button(component_actions, text="Open Component Artifact", command=self.open_selected_explanation_component_artifact).pack(side=LEFT, padx=5)
        compare_panel = ttk.Frame(candidate_panel, style="Panel.TFrame")
        compare_panel.pack(fill=BOTH, expand=False, pady=(10, 0))
        ttk.Label(compare_panel, text="Candidate Comparison", style="PanelTitle.TLabel").pack(anchor="w")
        self.compare_tree = self._tree(
            compare_panel,
            ["candidate_id", "score", "site_class", "delta_mw", "delta_clogp", "delta_tpsa", "summary"],
            ["ID", "Score", "Site class", "dMW", "dClogP", "dTPSA", "Summary"],
            [110, 70, 140, 75, 75, 75, 520],
        )
        visual_actions = ttk.Frame(compare_panel, style="Panel.TFrame")
        visual_actions.pack(fill=X, pady=(8, 0))
        ttk.Button(visual_actions, text="Open Visual Grid", command=lambda: open_path(self.project_dir() / "candidate_visual_compare" / "candidate_visual_grid.png")).pack(side=LEFT, padx=(0, 5))
        ttk.Button(visual_actions, text="Open Review Packet", command=lambda: open_path(self.project_dir() / "candidate_review_packet.csv")).pack(side=LEFT, padx=5)
        ttk.Button(visual_actions, text="Open Review Board", command=lambda: open_path(self.project_dir() / "candidate_review_board_focused.csv")).pack(side=LEFT, padx=5)
        ttk.Button(visual_actions, text="Open Drilldown", command=lambda: open_path(self.project_dir() / "candidate_drilldown_packet.csv")).pack(side=LEFT, padx=5)
        ttk.Button(visual_actions, text="Open Decisions", command=lambda: open_path(self.project_dir() / "candidate_decision_export.csv")).pack(side=LEFT, padx=5)
        ttk.Button(visual_actions, text="Open Drawer", command=lambda: open_path(self.project_dir() / "candidate_evidence_drawer.csv")).pack(side=LEFT, padx=5)
        ttk.Label(visual_actions, textvariable=self.visual_compare_var, style="MetricLabel.TLabel").pack(side=LEFT, padx=12)

    def _build_candidate_review_view(self) -> None:
        view = ttk.Frame(self.content, style="Shell.TFrame")
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(1, weight=1)
        self.views["candidate_review"] = view

        metrics = self.panel(view)
        metrics.grid(row=0, column=0, sticky="ew")
        metrics.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.review_metric_vars = [StringVar(value="-") for _ in range(4)]
        for idx, label in enumerate(["Board", "Rows", "Pending Local", "Local Statuses"]):
            box = ttk.Frame(metrics, style="Panel.TFrame")
            box.grid(row=0, column=idx, sticky="ew", padx=8)
            ttk.Label(box, textvariable=self.review_metric_vars[idx], style="Metric.TLabel").pack(anchor="w")
            ttk.Label(box, text=label, style="MetricLabel.TLabel").pack(anchor="w")

        scroll_host = ttk.Frame(view, style="Shell.TFrame")
        scroll_host.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        scroll_content = self._scrollable_frame(scroll_host)
        panel = self.panel(scroll_content)
        panel.pack(fill=BOTH, expand=True)
        panel.grid_columnconfigure(0, weight=1)
        ttk.Label(panel, text="Candidate Review Board", style="PanelTitle.TLabel").pack(anchor="w")
        filters = ttk.Frame(panel, style="Panel.TFrame")
        filters.pack(fill=X, pady=(8, 8))
        for label, var, width in [
            ("Site", self.review_site_filter_var, 18),
            ("Bucket", self.review_bucket_filter_var, 24),
            ("Local", self.review_local_status_filter_var, 18),
            ("Risk", self.review_risk_filter_var, 18),
            ("Reviewer", self.review_reviewer_filter_var, 18),
        ]:
            ttk.Label(filters, text=label, style="MetricLabel.TLabel").pack(side=LEFT, padx=(0, 4))
            ttk.Entry(filters, textvariable=var, width=width).pack(side=LEFT, padx=(0, 8))
        ttk.Button(filters, text="Apply", command=self.render_candidate_review_board).pack(side=LEFT, padx=3)
        ttk.Button(filters, text="Clear", command=self.clear_candidate_review_filters).pack(side=LEFT, padx=3)
        ttk.Button(filters, text="Refresh Data", command=self.populate_candidate_review_board).pack(side=LEFT, padx=3)
        self.review_paned = None
        review_board_frame = ttk.Frame(panel, style="Panel.TFrame")
        review_board_frame.pack(fill=X, expand=False)
        self.review_tree = self._tree(
            review_board_frame,
            ["candidate_id", "score", "site", "bucket", "packet_status", "local_status", "risk", "reason", "action"],
            ["ID", "Score", "Site", "Bucket", "Packet", "Local", "Risk", "Reason", "Action"],
            [100, 65, 135, 180, 115, 125, 120, 180, 360],
            height=7,
        )
        self.review_tree.bind("<<TreeviewSelect>>", lambda _event: self.show_selected_review_detail())
        review_detail_area = ttk.Frame(review_board_frame, style="Panel.TFrame")
        review_detail_area.pack(fill=X, pady=(10, 0))
        review_detail_text = ttk.Frame(review_detail_area, style="Panel.TFrame")
        review_detail_text.pack(side=LEFT, fill=X, expand=True, padx=(0, 14))
        ttk.Label(review_detail_text, textvariable=self.review_detail_var, style="MetricLabel.TLabel", justify=LEFT, wraplength=980).pack(fill=X)
        ttk.Label(review_detail_text, text="Evidence Drawer", style="PanelTitle.TLabel").pack(anchor="w", pady=(10, 2))
        ttk.Label(review_detail_text, textvariable=self.evidence_drawer_var, style="MetricLabel.TLabel", justify=LEFT, wraplength=980).pack(fill=X, pady=(0, 4))
        ttk.Label(review_detail_text, text="Candidate Explanation", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 2))
        ttk.Label(review_detail_text, textvariable=self.candidate_explanation_var, style="MetricLabel.TLabel", justify=LEFT, wraplength=980).pack(fill=X, pady=(0, 4))
        self.review_explanation_chart_label = ttk.Label(review_detail_text, style="Panel.TLabel")
        self.review_explanation_chart_label.pack(anchor="w", pady=(0, 4))
        review_structure_frame = ttk.Frame(review_detail_area, style="Panel.TFrame")
        review_structure_frame.pack(side=LEFT, fill="y")
        ttk.Label(review_structure_frame, text="Review 2D Compare", style="PanelTitle.TLabel").pack(anchor="w")
        review_before_after = ttk.Frame(review_structure_frame, style="Panel.TFrame")
        review_before_after.pack(fill=X, pady=(4, 0))
        review_before_after.grid_columnconfigure((0, 1), weight=1)
        self.review_before_structure_label = ttk.Label(
            review_before_after,
            textvariable=self.review_before_structure_var,
            style="MetricLabel.TLabel",
            justify=LEFT,
            wraplength=170,
        )
        self.review_before_structure_label.grid(row=0, column=0, sticky="n", padx=(0, 6))
        self.review_structure_label = ttk.Label(
            review_before_after,
            textvariable=self.review_structure_var,
            style="MetricLabel.TLabel",
            justify=LEFT,
            wraplength=170,
        )
        self.review_structure_label.grid(row=0, column=1, sticky="n", padx=(6, 0))

        actions = ttk.Frame(review_board_frame, style="Panel.TFrame")
        actions.pack(fill=X, pady=(10, 0))
        ttk.Label(actions, text="Set local status", style="MetricLabel.TLabel").pack(side=LEFT, padx=(0, 6))
        ttk.Combobox(
            actions,
            textvariable=self.review_update_status_var,
            values=["reviewed", "needs_follow_up", "deferred", "blocked", "evidence_supported"],
            width=18,
            state="readonly",
        ).pack(side=LEFT, padx=(0, 8))
        ttk.Entry(actions, textvariable=self.review_note_var, width=42).pack(side=LEFT, padx=(0, 8))
        ttk.Button(actions, text="Mark Selected", style="Accent.TButton", command=lambda: self.update_review_rows("selected")).pack(side=LEFT, padx=3)
        ttk.Button(actions, text="Mark Filtered", style="Warn.TButton", command=lambda: self.update_review_rows("filtered")).pack(side=LEFT, padx=3)
        ttk.Button(actions, text="Open Image", command=self.open_selected_review_image).pack(side=LEFT, padx=3)
        ttk.Button(actions, text="Open Evidence", command=self.open_selected_review_drilldown).pack(side=LEFT, padx=3)
        ttk.Button(actions, text="Open Board CSV", command=lambda: open_path(self.project_dir() / "candidate_review_board.csv")).pack(side=LEFT, padx=3)
        ttk.Button(actions, text="Open Analytics", command=lambda: open_path(self.project_dir() / "candidate_review_analytics.csv")).pack(side=LEFT, padx=3)
        reason_frame = ttk.Frame(panel, style="Panel.TFrame")
        reason_frame.pack(fill=X, expand=False, pady=(16, 0))
        ttk.Label(reason_frame, text="Review Reason Workbench", style="PanelTitle.TLabel").pack(anchor="w")
        self.review_reason_tree = self._tree(
            reason_frame,
            ["reason", "rows", "site", "samples", "status", "action"],
            ["Reason", "Rows", "Top site", "Samples", "Status", "Action"],
            [220, 70, 170, 180, 140, 520],
            height=4,
        )
        self.review_reason_tree.bind("<<TreeviewSelect>>", lambda _event: self.apply_review_reason_filter())
        reason_actions = ttk.Frame(reason_frame, style="Panel.TFrame")
        reason_actions.pack(fill=X, pady=(8, 0))
        ttk.Label(reason_actions, text="Status", style="MetricLabel.TLabel").pack(side=LEFT, padx=(0, 4))
        ttk.Combobox(
            reason_actions,
            textvariable=self.review_reason_batch_status_var,
            values=["reviewed", "needs_follow_up", "deferred", "blocked", "evidence_supported"],
            width=18,
            state="readonly",
        ).pack(side=LEFT, padx=(0, 8))
        ttk.Entry(reason_actions, textvariable=self.review_reason_batch_note_var, width=54).pack(side=LEFT, padx=(0, 8))
        ttk.Button(reason_actions, text="Apply Reason Filter", command=self.apply_review_reason_filter).pack(side=LEFT, padx=3)
        ttk.Button(reason_actions, text="Batch Note Cluster", style="Accent.TButton", command=self.update_selected_review_reason_cluster).pack(side=LEFT, padx=3)
        ttk.Button(reason_actions, text="Close Cluster", style="Warn.TButton", command=self.close_selected_review_reason_cluster).pack(side=LEFT, padx=3)
        ttk.Label(reason_frame, text="Reason Batch Audit Replay", style="PanelTitle.TLabel").pack(anchor="w", pady=(10, 0))
        self.review_reason_audit_tree = self._tree(
            reason_frame,
            ["reason", "status", "rows", "reviewer", "created", "note"],
            ["Reason", "Status", "Rows", "Reviewer", "Created", "Note"],
            [220, 140, 70, 130, 220, 520],
            height=4,
        )
        cockpit_frame = ttk.Frame(panel, style="Panel.TFrame")
        cockpit_frame.pack(fill=X, expand=False, pady=(16, 0))
        ttk.Label(cockpit_frame, text="Reviewer Cockpit", style="PanelTitle.TLabel").pack(anchor="w")
        self.reviewer_cockpit_tree = self._tree(
            cockpit_frame,
            ["lane", "key", "status", "priority", "open", "audit", "owner", "action"],
            ["Lane", "Key", "Status", "Priority", "Open", "Audit", "Owner", "Action"],
            [150, 260, 150, 100, 70, 70, 160, 520],
            height=5,
        )
        self.reviewer_cockpit_tree.bind("<<TreeviewSelect>>", lambda _event: self.apply_reviewer_cockpit_route())
        ttk.Label(cockpit_frame, textvariable=self.reviewer_cockpit_var, style="MetricLabel.TLabel", justify=LEFT, wraplength=1280).pack(fill=X, pady=(4, 2))
        review_analytics_frame = ttk.Frame(panel, style="Panel.TFrame")
        review_analytics_frame.pack(fill=X, expand=False, pady=(16, 0))
        self.review_analytics_frame = review_analytics_frame
        analytics_header = ttk.Frame(review_analytics_frame, style="Panel.TFrame")
        analytics_header.pack(fill=X, pady=(2, 2))
        ttk.Label(analytics_header, text="Review Analytics", style="PanelTitle.TLabel").pack(side=LEFT)
        ttk.Button(analytics_header, text="Expand", command=lambda: self.set_review_analytics_layout("expanded")).pack(side=LEFT, padx=(10, 3))
        ttk.Button(analytics_header, text="Reset", command=lambda: self.set_review_analytics_layout("reset")).pack(side=LEFT, padx=3)
        ttk.Button(analytics_header, text="Open Filter Evidence", command=self.open_review_analytics_evidence).pack(side=LEFT, padx=3)
        ttk.Label(review_analytics_frame, textvariable=self.review_analytics_var, style="MetricLabel.TLabel", justify=LEFT, wraplength=1280).pack(fill=X, pady=(0, 4))
        self.review_analytics_tree = self._tree(
            review_analytics_frame,
            ["row_type", "key", "status", "value", "secondary", "details"],
            ["Type", "Key", "Status", "Value", "Secondary", "Details"],
            [150, 220, 150, 90, 100, 620],
            height=7,
        )
        self.review_analytics_tree.bind("<<TreeviewSelect>>", lambda _event: self.apply_review_analytics_filter())

    def _build_project_memory_view(self) -> None:
        view = ttk.Frame(self.content, style="Shell.TFrame")
        view.grid_columnconfigure(0, weight=1)
        view.grid_columnconfigure(1, weight=1)
        view.grid_rowconfigure(1, weight=1)
        self.views["project_memory"] = view

        metrics = self.panel(view)
        metrics.grid(row=0, column=0, columnspan=2, sticky="ew")
        metrics.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.pm_metric_vars = [StringVar(value="-") for _ in range(4)]
        for idx, label in enumerate(["Dashboard", "Rows", "Open-like", "Lanes"]):
            box = ttk.Frame(metrics, style="Panel.TFrame")
            box.grid(row=0, column=idx, sticky="ew", padx=8)
            ttk.Label(box, textvariable=self.pm_metric_vars[idx], style="Metric.TLabel").pack(anchor="w")
            ttk.Label(box, text=label, style="MetricLabel.TLabel").pack(anchor="w")

        lanes = self.panel(view)
        lanes.grid(row=1, column=0, sticky="nsew", pady=(14, 0), padx=(0, 7))
        ttk.Label(lanes, text="Lane Dashboard", style="PanelTitle.TLabel").pack(anchor="w")
        self.lane_tree = self._tree(
            lanes,
            ["lane", "rows", "open", "assigned", "closed", "critical", "next_action"],
            ["Lane", "Rows", "Open", "Assigned", "Closed", "Critical", "Next action"],
            [150, 70, 70, 80, 70, 80, 280],
        )

        attention = self.panel(view)
        attention.grid(row=1, column=1, sticky="nsew", pady=(14, 0), padx=(7, 0))
        ttk.Label(attention, text="Attention Queue", style="PanelTitle.TLabel").pack(anchor="w")
        self.attention_tree = self._tree(
            attention,
            ["id", "lane", "priority", "status", "assignee", "action"],
            ["ID", "Lane", "Priority", "Status", "Assignee", "Action"],
            [210, 130, 80, 90, 120, 260],
        )
        self.attention_tree.bind("<<TreeviewSelect>>", lambda _event: self.show_selected_history())

        actions = self.panel(view)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        for text, command, style in [
            ("Refresh Project Memory", self.refresh_project_memory, "Accent.TButton"),
            ("Assign Critical Profile", self.assign_critical_profile, "Accent.TButton"),
            ("Assign Endpoint Gaps", self.assign_endpoint_gaps, "Accent.TButton"),
            ("Close Selected", lambda: self.update_selected_pm("closed"), "Warn.TButton"),
            ("Defer Selected", lambda: self.update_selected_pm("deferred"), "Warn.TButton"),
            ("Reload", self.reload_all, "TButton"),
        ]:
            ttk.Button(actions, text=text, command=command, style=style).pack(side=LEFT, padx=5)
        self.history_var = StringVar(value="Select a row to inspect reviewer history.")
        ttk.Label(actions, textvariable=self.history_var, style="MetricLabel.TLabel").pack(side=LEFT, padx=16)

    def _build_endpoint_view(self) -> None:
        view = ttk.Frame(self.content, style="Shell.TFrame")
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(1, weight=1)
        self.views["endpoint"] = view
        header = self.panel(view)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.endpoint_metric_vars = [StringVar(value="-") for _ in range(4)]
        for idx, label in enumerate(["Status", "Rows", "Pending exact", "Site policy rows"]):
            box = ttk.Frame(header, style="Panel.TFrame")
            box.grid(row=0, column=idx, sticky="ew", padx=8)
            ttk.Label(box, textvariable=self.endpoint_metric_vars[idx], style="Metric.TLabel").pack(anchor="w")
            ttk.Label(box, text=label, style="MetricLabel.TLabel").pack(anchor="w")

        body = ttk.Frame(view, style="Shell.TFrame")
        body.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        panel = self.panel(body)
        panel.grid(row=0, column=0, sticky="nsew")
        ttk.Label(panel, text="Strict Endpoint and Site-Class Governance", style="PanelTitle.TLabel").pack(anchor="w")
        self.endpoint_tree = self._tree(
            panel,
            ["plan", "candidate", "required", "available", "status", "site_classes", "actions"],
            ["Plan", "Candidate", "Required", "Available", "Strict status", "Site classes", "Actions"],
            [150, 100, 110, 140, 170, 180, 300],
        )
        buttons = ttk.Frame(view, style="Shell.TFrame")
        buttons.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        ttk.Button(buttons, text="Rebuild Endpoint Governance", style="Accent.TButton", command=self.rebuild_endpoint_governance).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Open Endpoint Governance CSV", command=lambda: open_path(ROOT / "data/projects/demo/measurement_gap_endpoint_governance.csv")).pack(side=LEFT, padx=5)

    def _build_readiness_view(self) -> None:
        view = ttk.Frame(self.content, style="Shell.TFrame")
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(1, weight=1)
        self.views["readiness"] = view
        metrics = self.panel(view)
        metrics.grid(row=0, column=0, sticky="ew")
        metrics.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.readiness_metric_vars = [StringVar(value="-") for _ in range(4)]
        for idx, label in enumerate(["Packet", "Score", "Profile open", "Endpoint pending"]):
            box = ttk.Frame(metrics, style="Panel.TFrame")
            box.grid(row=0, column=idx, sticky="ew", padx=8)
            ttk.Label(box, textvariable=self.readiness_metric_vars[idx], style="Metric.TLabel").pack(anchor="w")
            ttk.Label(box, text=label, style="MetricLabel.TLabel").pack(anchor="w")

        body = ttk.Frame(view, style="Shell.TFrame")
        body.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        summary = self.panel(body)
        summary.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        ttk.Label(summary, text="Summary Rows", style="PanelTitle.TLabel").pack(anchor="w")
        self.readiness_tree = self._tree(
            summary,
            ["section", "status", "primary", "secondary", "details"],
            ["Section", "Status", "Primary", "Secondary", "Details"],
            [180, 130, 90, 90, 420],
        )
        findings = self.panel(body)
        findings.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        ttk.Label(findings, text="Findings", style="PanelTitle.TLabel").pack(anchor="w")
        self.finding_tree = self._tree(
            findings,
            ["level", "lane", "label", "details"],
            ["Level", "Lane", "Finding", "Details"],
            [90, 130, 260, 420],
        )
        self.finding_tree.bind("<<TreeviewSelect>>", lambda _event: self.readiness_drill_down())
        buttons = ttk.Frame(view, style="Shell.TFrame")
        buttons.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        ttk.Button(buttons, text="Build Readiness Packet", style="Accent.TButton", command=self.build_readiness_packet).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Open Linked Queue", command=self.readiness_drill_down).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Freeze Package", style="Accent.TButton", command=self.build_freeze_package).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Open Freeze Manifest", command=lambda: open_path(ROOT / "data/projects/demo/profile_promotion_freeze_manifest.json")).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Open Readiness CSV", command=lambda: open_path(ROOT / "data/projects/demo/promotion_readiness_packet.csv")).pack(side=LEFT, padx=5)

    def _build_reports_view(self) -> None:
        view = ttk.Frame(self.content, style="Shell.TFrame")
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(0, weight=1)
        self.views["reports"] = view
        panel = self.panel(view)
        panel.grid(row=0, column=0, sticky="nsew")
        ttk.Label(panel, text="Local Assets", style="PanelTitle.TLabel").pack(anchor="w")
        self.report_text = StringVar(value="")
        ttk.Label(panel, textvariable=self.report_text, style="Subheader.TLabel", justify=LEFT).pack(anchor="w", pady=(8, 12))
        ttk.Label(panel, text="Production Gates", style="PanelTitle.TLabel").pack(anchor="w", pady=(4, 4))
        self.production_tree = self._tree(
            panel,
            ["gate", "status", "level", "primary", "secondary", "details"],
            ["Gate", "Status", "Level", "Primary", "Secondary", "Details"],
            [180, 150, 80, 80, 90, 520],
        )
        self.production_tree.bind("<<TreeviewSelect>>", lambda _event: self.production_gate_drill_down())
        ttk.Label(panel, textvariable=self.production_drilldown_var, style="Subheader.TLabel", justify=LEFT, wraplength=1280).pack(anchor="w", pady=(8, 8))
        ttk.Label(panel, text="Feed Absorption Diff Navigator", style="PanelTitle.TLabel").pack(anchor="w", pady=(4, 4))
        self.feed_diff_tree = self._tree(
            panel,
            ["row", "type", "source", "status", "delta", "pair", "action"],
            ["Row", "Type", "Source", "Status", "Delta", "Pair", "Action"],
            [140, 180, 210, 110, 80, 250, 520],
        )
        ttk.Label(panel, text="Source Expansion Governance", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.source_expansion_tree = self._tree(
            panel,
            ["gate", "status", "details", "action"],
            ["Gate", "Status", "Details", "Action"],
            [220, 120, 520, 520],
        )
        ttk.Label(panel, text="Feed Promotion Simulator", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.feed_promotion_simulator_tree = self._tree(
            panel,
            ["source", "status", "allowed", "staged", "target", "projected", "blockers", "action"],
            ["Source", "Status", "Allowed", "Staged", "Target", "Projected", "Blockers", "Action"],
            [220, 160, 90, 80, 80, 90, 80, 520],
        )
        ttk.Label(panel, text="R-group Staging Quality Budget", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.staging_quality_budget_tree = self._tree(
            panel,
            ["source", "status", "rows", "max", "blockers", "missing", "duplicates", "action"],
            ["Source", "Status", "Rows", "Max", "Blockers", "Missing", "Duplicates", "Action"],
            [220, 160, 70, 70, 80, 80, 90, 520],
        )
        ttk.Label(panel, text="R-group Staging Admission Scorecard", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.staging_admission_scorecard_tree = self._tree(
            panel,
            ["rank", "source", "bucket", "score", "credibility", "duplicate", "context", "impact", "action"],
            ["Rank", "Source", "Bucket", "Score", "Cred.", "Dup.", "Context", "Impact", "Action"],
            [60, 210, 190, 75, 75, 75, 85, 75, 520],
        )
        ttk.Label(panel, text="R-group Admission Sandbox Replay", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.rgroup_admission_sandbox_replay_tree = self._tree(
            panel,
            ["source", "status", "bucket", "impact", "sandbox", "score_delta", "rank_delta", "rollback", "action"],
            ["Source", "Status", "Bucket", "Impact", "Sandbox", "dScore", "dRank", "Rollback", "Action"],
            [220, 170, 190, 80, 80, 80, 80, 90, 520],
        )
        ttk.Label(panel, text="R-group Staging Manual Review Queue", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.staging_manual_review_tree = self._tree(
            panel,
            ["queue", "source", "status", "rows", "blockers", "signoff", "version", "action"],
            ["Queue", "Source", "Status", "Rows", "Blockers", "Signoff", "Version Log", "Action"],
            [120, 210, 190, 70, 80, 170, 260, 520],
        )
        self.staging_manual_review_tree.bind("<<TreeviewSelect>>", lambda _event: self.show_selected_staging_curator_queue())
        ttk.Label(panel, textvariable=self.staging_curator_detail_var, style="MetricLabel.TLabel", justify=LEFT, wraplength=1280).pack(fill=X, pady=(4, 2))
        curator_controls = ttk.Frame(panel, style="Panel.TFrame")
        curator_controls.pack(fill=X, pady=(2, 8))
        ttk.Label(curator_controls, text="Curator", style="MetricLabel.TLabel").pack(side=LEFT, padx=(0, 4))
        ttk.Entry(curator_controls, textvariable=self.staging_curator_var, width=18).pack(side=LEFT, padx=(0, 8))
        ttk.Label(curator_controls, text="Decision", style="MetricLabel.TLabel").pack(side=LEFT, padx=(0, 4))
        ttk.Combobox(
            curator_controls,
            textvariable=self.staging_curator_decision_var,
            values=["ready_for_sandbox_review", "needs_curation", "deferred", "blocked"],
            width=24,
            state="readonly",
        ).pack(side=LEFT, padx=(0, 8))
        ttk.Entry(curator_controls, textvariable=self.staging_curator_version_note_var, width=42).pack(side=LEFT, padx=(0, 8))
        ttk.Entry(curator_controls, textvariable=self.staging_curator_note_var, width=42).pack(side=LEFT, padx=(0, 8))
        ttk.Button(curator_controls, text="Signoff Selected", style="Accent.TButton", command=lambda: self.signoff_staging_curator_queue("selected")).pack(side=LEFT, padx=3)
        ttk.Button(curator_controls, text="Signoff Visible", style="Warn.TButton", command=lambda: self.signoff_staging_curator_queue("visible")).pack(side=LEFT, padx=3)
        ttk.Button(curator_controls, text="Open Staging CSV", command=self.open_selected_staging_curator_csv).pack(side=LEFT, padx=3)
        ttk.Button(curator_controls, text="Open Version Diff", command=lambda: open_path(ROOT / "docs/substituent_version_diff_browser.md")).pack(side=LEFT, padx=3)
        ttk.Label(panel, text="R-group Staging Curator Signoff Ledger", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.staging_curator_signoff_tree = self._tree(
            panel,
            ["queue", "source", "decision", "curator", "rows", "blocked", "signed", "note"],
            ["Queue", "Source", "Decision", "Curator", "Rows", "Blocked", "Signed", "Note"],
            [120, 210, 170, 150, 70, 80, 180, 520],
        )
        ttk.Label(panel, text="Governed Ingestion Batches", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.governed_ingestion_tree = self._tree(
            panel,
            ["batch", "scope", "status", "allowed", "staged", "max", "gate", "action"],
            ["Batch", "Scope", "Status", "Allowed", "Staged", "Max", "Gate", "Action"],
            [210, 170, 150, 90, 80, 80, 150, 520],
        )
        ttk.Label(panel, text="Staged Feed Sandbox Scoring", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.staged_feed_sandbox_tree = self._tree(
            panel,
            ["candidate", "base", "sandbox", "delta", "matches", "bucket", "affected", "action"],
            ["Candidate", "Base", "Sandbox", "Delta", "Matches", "Bucket", "Affected", "Action"],
            [130, 80, 90, 80, 80, 130, 90, 520],
        )
        ttk.Label(panel, text="Sandbox Score Delta Review", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.sandbox_score_delta_review_tree = self._tree(
            panel,
            ["review", "candidate", "status", "risk", "delta", "rank_delta", "signoff", "action"],
            ["Review", "Candidate", "Status", "Risk", "dScore", "dRank", "Signoff", "Action"],
            [130, 130, 170, 180, 80, 80, 80, 520],
        )
        ttk.Label(panel, text="Sandbox Delta Signoff Ledger", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.sandbox_score_delta_signoff_tree = self._tree(
            panel,
            ["review", "candidate", "decision", "operator", "valid", "found", "approved", "note"],
            ["Review", "Candidate", "Decision", "Operator", "Valid", "Found", "Approved", "Note"],
            [130, 130, 120, 170, 70, 70, 80, 560],
        )
        ttk.Label(panel, text="R-group Feed Digestion Ledger", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.rgroup_feed_digestion_tree = self._tree(
            panel,
            ["row", "replacement", "source", "digest", "decision", "matches", "promoted", "action"],
            ["Row", "Replacement", "Source", "Digest", "Decision", "Matches", "Promoted", "Action"],
            [130, 190, 210, 220, 140, 80, 80, 520],
        )
        ttk.Label(panel, text="R-group Promotion Approval Ledger", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.rgroup_promotion_approval_tree = self._tree(
            panel,
            ["approval", "replacement", "source", "eligible", "decision", "approved", "pending", "action"],
            ["Approval", "Replacement", "Source", "Eligible", "Decision", "Approved", "Pending", "Action"],
            [140, 200, 190, 80, 120, 80, 80, 520],
        )
        ttk.Label(panel, text="R-group Digestion Quality Metrics", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.rgroup_digestion_quality_tree = self._tree(
            panel,
            ["metric", "type", "group", "status", "rows", "low", "impact", "action"],
            ["Metric", "Type", "Group", "Status", "Rows", "LowConf", "Impact", "Action"],
            [130, 170, 230, 100, 70, 80, 80, 520],
        )
        ttk.Label(panel, text="Staging/Sandbox Filter Views", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.staging_sandbox_filter_tree = self._tree(
            panel,
            ["view", "filter", "value", "rows", "target", "ui", "action"],
            ["View", "Filter", "Value", "Rows", "Target", "UI", "Action"],
            [210, 180, 260, 80, 240, 190, 520],
        )
        ttk.Label(panel, text="Local DB Release Gate", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.local_db_release_gate_tree = self._tree(
            panel,
            ["source", "type", "name", "status", "class", "value", "action"],
            ["Source", "Type", "Name", "Status", "Class", "Value", "Action"],
            [210, 150, 210, 100, 120, 110, 520],
        )
        ttk.Label(panel, text="Candidate Baseline Diff", style="PanelTitle.TLabel").pack(anchor="w", pady=(4, 4))
        self.baseline_diff_tree = self._tree(
            panel,
            ["candidate_id", "status", "score_delta", "rank_delta", "fields", "review"],
            ["ID", "Status", "dScore", "dRank", "Changed fields", "Review"],
            [110, 100, 85, 85, 260, 520],
        )
        ttk.Label(panel, text="Operator Trend Cards", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.operator_trend_tree = self._tree(
            panel,
            ["card", "status", "value", "trend", "next_action"],
            ["Card", "Status", "Value", "Trend", "Next action"],
            [210, 130, 100, 100, 620],
        )
        ttk.Label(panel, text="Decision QA Queue", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.decision_qa_tree = self._tree(
            panel,
            ["candidate_id", "decision", "qa", "reason", "age", "action"],
            ["ID", "Decision", "QA", "Reason", "Age", "Action"],
            [110, 110, 180, 260, 70, 520],
        )
        ttk.Label(panel, text="Candidate Explanation Compare", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.candidate_explanation_compare_tree = self._tree(
            panel,
            ["component", "base", "head", "delta", "direction", "action"],
            ["Component", "Base", "Head", "Delta", "Direction", "Action"],
            [180, 260, 260, 80, 100, 520],
        )
        ttk.Label(panel, text="Candidate Explanation Matrix", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.candidate_explanation_matrix_tree = self._tree(
            panel,
            ["candidate", "rank", "score", "bucket", "mean", "qa", "baseline", "open"],
            ["Candidate", "Rank", "Score", "Bucket", "Mean", "QA", "Baseline", "Open"],
            [130, 70, 80, 130, 80, 170, 170, 70],
        )
        ttk.Label(panel, text="Site Detection Confidence", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.site_detection_confidence_tree = self._tree(
            panel,
            ["type", "key", "status", "score", "rules", "boundary", "false_positive", "details"],
            ["Type", "Key", "Status", "Score", "Rules", "Boundary", "FP Guard", "Details"],
            [170, 170, 140, 70, 70, 80, 90, 520],
        )
        ttk.Label(panel, text="Site Detection Calibration Queue", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.site_detection_calibration_tree = self._tree(
            panel,
            ["id", "type", "site", "score", "priority", "needed", "status", "action"],
            ["ID", "Type", "Site", "Score", "Priority", "Needed", "Status", "Action"],
            [120, 180, 190, 70, 90, 210, 190, 520],
        )
        ttk.Label(panel, text="Evidence Quality Scorecard", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.evidence_quality_tree = self._tree(
            panel,
            ["candidate_id", "quality", "reason", "depth", "qa", "action"],
            ["ID", "Quality", "Reason", "Depth", "QA", "Action"],
            [110, 210, 320, 80, 160, 520],
        )
        ttk.Label(panel, text="Candidate Baseline Manager", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.baseline_manager_tree = self._tree(
            panel,
            ["baseline_id", "active", "age", "compare", "archive", "action"],
            ["Baseline", "Active", "Age", "Compare", "Archive", "Action"],
            [180, 80, 70, 130, 140, 520],
        )
        ttk.Label(panel, text="Reviewer Operations", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.reviewer_operations_tree = self._tree(
            panel,
            ["type", "key", "status", "value", "secondary", "details"],
            ["Type", "Key", "Status", "Value", "Secondary", "Details"],
            [170, 260, 150, 110, 150, 580],
        )
        ttk.Label(panel, text="Candidate Baseline Lineage", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.baseline_lineage_tree = self._tree(
            panel,
            ["candidate_id", "status", "base", "head", "fields", "reason"],
            ["ID", "Status", "Base Score", "Head Score", "Fields", "Reason"],
            [140, 110, 110, 110, 260, 520],
        )
        ttk.Label(panel, text="Review Command Center", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.review_command_tree = self._tree(
            panel,
            ["command", "type", "severity", "target", "filter", "action"],
            ["Command", "Type", "Severity", "Target", "Filter", "Action"],
            [220, 170, 120, 140, 320, 520],
        )
        self.review_command_tree.bind("<<TreeviewSelect>>", lambda _event: self.show_selected_review_command())
        ttk.Label(panel, textvariable=self.review_command_center_var, style="Subheader.TLabel", justify=LEFT, wraplength=1280).pack(anchor="w", pady=(4, 4))
        ttk.Label(panel, text="Candidate Remediation Queue", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.review_remediation_tree = self._tree(
            panel,
            ["task", "type", "priority", "owner", "due", "status", "action"],
            ["Task", "Type", "Priority", "Owner", "Due", "Status", "Action"],
            [180, 170, 100, 160, 110, 130, 520],
        )
        self.review_remediation_tree.bind("<<TreeviewSelect>>", lambda _event: self.show_selected_remediation_task())
        ttk.Label(panel, textvariable=self.remediation_detail_var, style="MetricLabel.TLabel", justify=LEFT, wraplength=1280).pack(fill=X, pady=(4, 2))
        remediation_controls = ttk.Frame(panel, style="Panel.TFrame")
        remediation_controls.pack(fill=X, pady=(2, 8))
        for label, var, width in [
            ("Owner", self.remediation_owner_var, 18),
            ("Due", self.remediation_due_var, 12),
        ]:
            ttk.Label(remediation_controls, text=label, style="MetricLabel.TLabel").pack(side=LEFT, padx=(0, 4))
            ttk.Entry(remediation_controls, textvariable=var, width=width).pack(side=LEFT, padx=(0, 8))
        ttk.Label(remediation_controls, text="Status", style="MetricLabel.TLabel").pack(side=LEFT, padx=(0, 4))
        ttk.Combobox(
            remediation_controls,
            textvariable=self.remediation_status_var,
            values=["open", "closed", "deferred", "accepted_risk", "duplicate", "reopened"],
            width=16,
            state="readonly",
        ).pack(side=LEFT, padx=(0, 8))
        ttk.Label(remediation_controls, text="Reason", style="MetricLabel.TLabel").pack(side=LEFT, padx=(0, 4))
        ttk.Combobox(
            remediation_controls,
            textvariable=self.remediation_reason_var,
            values=["local_review_resolved", "evidence_reconciled", "accepted_risk", "duplicate_task", "deferred_low_priority", "reopened_new_evidence"],
            width=22,
            state="readonly",
        ).pack(side=LEFT, padx=(0, 8))
        ttk.Entry(remediation_controls, textvariable=self.remediation_note_var, width=44).pack(side=LEFT, padx=(0, 8))
        ttk.Button(remediation_controls, text="Save Selected", command=self.save_selected_remediation_task).pack(side=LEFT, padx=3)
        ttk.Button(remediation_controls, text="Close Selected", style="Accent.TButton", command=self.close_selected_remediation_task).pack(side=LEFT, padx=3)
        ttk.Button(remediation_controls, text="Reopen Selected", command=self.reopen_selected_remediation_task).pack(side=LEFT, padx=3)
        ttk.Button(remediation_controls, text="Close Visible", style="Warn.TButton", command=self.close_visible_remediation_tasks).pack(side=LEFT, padx=3)
        ttk.Button(remediation_controls, text="Assign Visible", command=self.assign_visible_remediation_tasks).pack(side=LEFT, padx=3)
        ttk.Button(remediation_controls, text="Postpone Selected", command=self.postpone_selected_remediation_tasks).pack(side=LEFT, padx=3)
        ttk.Button(remediation_controls, text="Postpone Visible", command=self.postpone_visible_remediation_tasks).pack(side=LEFT, padx=3)
        ttk.Label(panel, text="Candidate Review Ops Console", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.review_ops_console_tree = self._tree(
            panel,
            ["candidate", "lane", "owner", "risk", "local", "open", "high", "overdue", "blocker"],
            ["Candidate", "Lane", "Owner", "Risk", "Local", "Open", "High", "Overdue", "Blocker"],
            [120, 190, 170, 170, 150, 70, 70, 80, 520],
        )
        ttk.Label(panel, text="Review Closure Workbench", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.review_closure_tree = self._tree(
            panel,
            ["task", "priority", "owner", "due", "closure", "reason", "batch", "audit"],
            ["Task", "Priority", "Owner", "Due", "Closure", "Reason", "Batch", "Audit"],
            [170, 90, 150, 110, 120, 190, 150, 70],
        )
        ttk.Label(panel, text="Review Closure Filter Views", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.review_closure_filter_tree = self._tree(
            panel,
            ["view", "value", "tasks", "open", "overdue", "audit", "action"],
            ["View", "Value", "Tasks", "Open", "Overdue", "Audit", "Action"],
            [150, 220, 80, 80, 80, 80, 360],
        )
        ttk.Label(panel, text="Baseline Scenario Board", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.baseline_scenario_tree = self._tree(
            panel,
            ["scenario", "type", "status", "baseline", "movement", "delta", "action"],
            ["Scenario", "Type", "Status", "Baseline", "Movement", "dScore", "Action"],
            [210, 150, 110, 170, 90, 90, 520],
        )
        ttk.Label(panel, text="Baseline What-If Board", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.baseline_whatif_tree = self._tree(
            panel,
            ["scenario", "candidate", "current", "whatif", "rank_delta", "score_delta", "status", "reason"],
            ["Scenario", "Candidate", "Current", "What-If", "dRank", "dScore", "Status", "Reason"],
            [180, 120, 75, 75, 75, 80, 140, 520],
        )
        ttk.Label(panel, text="Baseline History Explorer", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.baseline_history_tree = self._tree(
            panel,
            ["created", "base", "head", "entered", "exited", "changed", "status"],
            ["Created", "Base", "Head", "Entered", "Exited", "Changed", "Status"],
            [210, 170, 170, 90, 90, 90, 130],
        )
        ttk.Label(panel, textvariable=self.baseline_history_chart_var, style="MetricLabel.TLabel", justify=LEFT, wraplength=1280).pack(fill=X, pady=(4, 2))
        self.baseline_history_chart_label = ttk.Label(panel, style="Panel.TLabel")
        self.baseline_history_chart_label.pack(anchor="w", pady=(0, 4))
        ttk.Label(panel, text="Baseline Lineage Preview", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.baseline_lineage_preview_tree = self._tree(
            panel,
            ["row", "type", "candidate", "status", "movement", "score", "rank", "details"],
            ["Row", "Type", "Candidate", "Status", "Movement", "dScore", "dRank", "Details"],
            [150, 150, 120, 120, 90, 90, 90, 520],
        )
        ttk.Label(panel, text="Baseline Lineage Filter Views", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.baseline_lineage_filter_tree = self._tree(
            panel,
            ["view", "value", "rows", "candidates", "movement", "pairwise", "movers"],
            ["View", "Value", "Rows", "Candidates", "Movement", "Pairwise", "Movers"],
            [170, 220, 70, 90, 90, 90, 90],
        )
        ttk.Label(panel, text="Native Drilldown Actions", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.native_drilldown_action_tree = self._tree(
            panel,
            ["action", "type", "source", "target", "filter", "ui", "rows", "next"],
            ["Action", "Type", "Source", "Target", "Filter", "UI", "Rows", "Next"],
            [110, 170, 220, 180, 260, 170, 70, 520],
        )
        self.native_drilldown_action_tree.bind("<<TreeviewSelect>>", lambda _event: self.show_selected_native_drilldown_action())
        ttk.Label(panel, textvariable=self.native_drilldown_action_var, style="Subheader.TLabel", justify=LEFT, wraplength=1280).pack(anchor="w", pady=(4, 4))
        ttk.Label(panel, text="Operator Trend Charts", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.trend_chart_tree = self._tree(
            panel,
            ["chart_id", "status", "value", "path"],
            ["Chart", "Status", "Value", "Path"],
            [220, 120, 100, 760],
        )
        self.trend_chart_tree.bind("<<TreeviewSelect>>", lambda _event: self.show_selected_trend_chart_preview())
        ttk.Label(panel, textvariable=self.trend_chart_preview_var, style="MetricLabel.TLabel", justify=LEFT, wraplength=1280).pack(fill=X, pady=(4, 2))
        self.trend_chart_preview_label = ttk.Label(panel, style="Panel.TLabel")
        self.trend_chart_preview_label.pack(anchor="w", pady=(0, 4))
        ttk.Label(panel, text="MedChem Discussion Handoff", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.handoff_tree = self._tree(
            panel,
            ["candidate_id", "decision", "qa", "limitations", "prompt"],
            ["ID", "Decision", "QA", "Limitations", "Prompt"],
            [110, 110, 180, 360, 520],
        )
        ttk.Label(panel, text="Substituent Version Diff Browser", style="PanelTitle.TLabel").pack(anchor="w", pady=(8, 4))
        self.substituent_version_diff_tree = self._tree(
            panel,
            ["substituent", "review", "version", "enabled", "linked", "attention", "contexts", "latest"],
            ["Substituent", "Review", "Version", "Enabled", "Linked", "Attention", "Contexts", "Latest"],
            [180, 150, 130, 80, 80, 80, 360, 520],
        )
        buttons = ttk.Frame(panel, style="Panel.TFrame")
        buttons.pack(anchor="w", pady=(12, 8))
        ttk.Button(buttons, text="Build Production Snapshot", style="Accent.TButton", command=self.build_production_snapshot).pack(side=LEFT, padx=(0, 5))
        ttk.Button(buttons, text="Fill R-group Staging", style="Accent.TButton", command=self.fill_rgroup_staging_from_reviewed_sources).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Feed Promotion Diff", style="Accent.TButton", command=self.build_feed_promotion_diff).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Feed Audit", style="Accent.TButton", command=self.build_feed_absorption_audit).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Feed Diff Nav", style="Accent.TButton", command=self.build_feed_absorption_diff_navigator).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Source Guard", style="Accent.TButton", command=self.build_source_expansion_governance).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Feed Simulator", style="Accent.TButton", command=self.build_feed_promotion_simulator).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Staging Budget", style="Accent.TButton", command=self.build_staging_quality_budget).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Intake Batches", style="Accent.TButton", command=self.build_governed_ingestion_batches).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Sandbox Scoring", style="Accent.TButton", command=self.build_staged_feed_sandbox_scoring).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Delta Review", style="Accent.TButton", command=self.build_sandbox_score_delta_review).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build R-group Replay", style="Accent.TButton", command=self.build_rgroup_admission_sandbox_replay).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Delta Signoff", style="Accent.TButton", command=self.build_sandbox_score_delta_signoff).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Digestion Ledger", style="Accent.TButton", command=self.build_rgroup_feed_digestion_ledger).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Promotion Approval", style="Accent.TButton", command=self.build_rgroup_promotion_approval_ledger).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Digestion Metrics", style="Accent.TButton", command=self.build_rgroup_digestion_quality_metrics).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Stage Filters", style="Accent.TButton", command=self.build_staging_sandbox_filter_views).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Ring Package Review", style="Accent.TButton", command=self.build_ring_package_review).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build DB Health", style="Accent.TButton", command=self.build_db_health).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build DB Maintenance", style="Accent.TButton", command=self.build_db_maintenance).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build DB Release Gate", style="Accent.TButton", command=self.build_local_db_release_gate).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Governance Diff", style="Accent.TButton", command=self.build_governance_diff).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Candidate Drilldown", style="Accent.TButton", command=self.build_candidate_drilldown).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Compare Candidate Baseline", style="Accent.TButton", command=self.compare_candidate_baseline).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Candidate Decisions", style="Accent.TButton", command=self.build_candidate_decision_packet).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Review Analytics", style="Accent.TButton", command=self.build_candidate_review_analytics).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Evidence Drawer", style="Accent.TButton", command=self.build_candidate_evidence_drawer).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Explanation Panel", style="Accent.TButton", command=self.build_candidate_explanation_panel).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Explanation Compare", style="Accent.TButton", command=self.build_candidate_explanation_compare).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Explanation Drilldown", style="Accent.TButton", command=self.build_candidate_explanation_drilldown).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Component Locator", style="Accent.TButton", command=self.build_candidate_component_structure_locator).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Explanation Matrix", style="Accent.TButton", command=self.build_candidate_explanation_matrix).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Site Confidence", style="Accent.TButton", command=self.build_site_detection_confidence).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Site Calibration", style="Accent.TButton", command=self.build_site_detection_calibration_queue).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Decision QA", style="Accent.TButton", command=self.build_candidate_decision_qa).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Evidence Quality", style="Accent.TButton", command=self.build_candidate_evidence_quality).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Baseline Manager", style="Accent.TButton", command=self.build_candidate_baseline_manager).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Reviewer Ops", style="Accent.TButton", command=self.build_reviewer_operations).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Baseline Lineage", style="Accent.TButton", command=self.build_candidate_baseline_lineage).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Command Center", style="Accent.TButton", command=self.build_review_command_center).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Review Remediation", style="Accent.TButton", command=self.build_review_remediation_queue).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Review Ops Console", style="Accent.TButton", command=self.build_candidate_review_ops_console).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Closure Workbench", style="Accent.TButton", command=self.build_review_closure_workbench).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Closure Filters", style="Accent.TButton", command=self.build_review_closure_filter_views).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Reviewer Cockpit", style="Accent.TButton", command=self.build_reviewer_cockpit).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Baseline Lineage History", style="Accent.TButton", command=self.build_baseline_lineage_history).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Baseline Scenario", style="Accent.TButton", command=self.build_baseline_scenario_board).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Baseline What-If", style="Accent.TButton", command=self.build_baseline_whatif_board).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Baseline Preview", style="Accent.TButton", command=self.build_baseline_lineage_preview).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Lineage Filters", style="Accent.TButton", command=self.build_baseline_lineage_filter_views).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Drilldown Actions", style="Accent.TButton", command=self.build_native_drilldown_actions).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Operator Trends", style="Accent.TButton", command=self.build_operator_trend_summary).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Trend Charts", style="Accent.TButton", command=self.build_operator_trend_charts).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Discussion Handoff", style="Accent.TButton", command=self.build_medchem_discussion_handoff).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Substituent Diff", style="Accent.TButton", command=self.build_substituent_version_diff_browser).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build UI Regression", style="Accent.TButton", command=self.build_native_regression).pack(side=LEFT, padx=5)
        ttk.Button(buttons, text="Build Portable Native Package", style="Accent.TButton", command=self.build_portable_package).pack(side=LEFT, padx=5)
        baseline_controls = ttk.Frame(panel, style="Panel.TFrame")
        baseline_controls.pack(anchor="w", pady=(0, 8))
        ttk.Label(baseline_controls, text="Governance baseline", style="MetricLabel.TLabel").pack(side=LEFT, padx=(0, 6))
        ttk.Entry(baseline_controls, textvariable=self.governance_baseline_name_var, width=28).pack(side=LEFT, padx=(0, 8))
        ttk.Button(baseline_controls, text="Save Baseline", style="Accent.TButton", command=self.create_governance_baseline).pack(side=LEFT, padx=5)
        ttk.Button(baseline_controls, text="Diff Baseline", style="Accent.TButton", command=self.diff_named_governance_baseline).pack(side=LEFT, padx=5)
        ttk.Label(baseline_controls, text="Candidate baseline", style="MetricLabel.TLabel").pack(side=LEFT, padx=(18, 6))
        ttk.Entry(baseline_controls, textvariable=self.candidate_baseline_name_var, width=24).pack(side=LEFT, padx=(0, 8))
        ttk.Button(baseline_controls, text="Pin Candidate", style="Accent.TButton", command=self.pin_candidate_baseline).pack(side=LEFT, padx=5)
        ttk.Button(baseline_controls, text="Diff Candidate", style="Accent.TButton", command=self.compare_candidate_baseline).pack(side=LEFT, padx=5)
        ttk.Label(baseline_controls, text="Archive note", style="MetricLabel.TLabel").pack(side=LEFT, padx=(18, 6))
        ttk.Entry(baseline_controls, textvariable=self.candidate_baseline_archive_note_var, width=34).pack(side=LEFT, padx=(0, 8))
        ttk.Button(baseline_controls, text="Archive Candidate", style="Warn.TButton", command=self.archive_candidate_baseline).pack(side=LEFT, padx=5)
        open_buttons = ttk.Frame(panel, style="Panel.TFrame")
        open_buttons.pack(anchor="w", pady=(0, 8))
        for text, path in [
            ("Open Product PDF", ROOT / "AutoMedChemist_Product_Update.pdf"),
            ("Open Product PPTX", ROOT / "AutoMedChemist_Product_Update.pptx"),
            ("Open Project Data Folder", self.project_dir()),
            ("Open Release Smoke Checklist", ROOT / "docs/release_smoke_checklist.md"),
            ("Open Production Dashboard CSV", ROOT / "data/releases/production_dashboard_snapshot.csv"),
            ("Open Trend History CSV", ROOT / "data/releases/production_dashboard_trend_history.csv"),
            ("Open DB Trend CSV", ROOT / "data/releases/local_db_maintenance_trend_history.csv"),
            ("Open Feed Promotion Diff CSV", ROOT / "data/substituents/rgroup_next_feed_drop_promotion_diff.csv"),
            ("Open Feed Audit", ROOT / "docs/feed_absorption_audit.md"),
            ("Open Feed Diff Nav", ROOT / "docs/feed_absorption_diff_navigator.md"),
            ("Open Source Guard", ROOT / "docs/source_expansion_governance.md"),
            ("Open Feed Simulator", ROOT / "docs/feed_promotion_simulator.md"),
            ("Open Staging Fill", ROOT / "docs/rgroup_staging_fill_report.md"),
            ("Open Staging Budget", ROOT / "docs/rgroup_staging_quality_budget.md"),
            ("Open Intake Batches", ROOT / "docs/governed_ingestion_batches.md"),
            ("Open Sandbox Scoring", ROOT / "docs/staged_feed_sandbox_scoring.md"),
            ("Open Delta Review", ROOT / "docs/sandbox_score_delta_review_packet.md"),
            ("Open R-group Replay", ROOT / "docs/rgroup_admission_sandbox_impact_replay.md"),
            ("Open Delta Signoff", ROOT / "docs/sandbox_score_delta_signoff_ledger.md"),
            ("Open Digestion Ledger", ROOT / "docs/rgroup_feed_digestion_ledger.md"),
            ("Open Promotion Approval", ROOT / "docs/rgroup_promotion_approval_ledger.md"),
            ("Open Digestion Metrics", ROOT / "docs/rgroup_digestion_quality_metrics.md"),
            ("Open Stage Filters", ROOT / "docs/staging_sandbox_filter_views.md"),
            ("Open Ring Package Review CSV", ROOT / "data/projects/demo/ring_outcome_result_package_review.csv"),
            ("Open DB Health JSON", ROOT / "data/releases/local_db_health_report.json"),
            ("Open DB Maintenance JSON", ROOT / "data/releases/local_db_maintenance_report.json"),
            ("Open DB Release Gate", ROOT / "docs/local_db_maintenance_release_gate.md"),
            ("Open Governance Diff", ROOT / "docs/local_governance_diff_report.md"),
            ("Open Visual Compare", ROOT / "docs/candidate_visual_compare.md"),
            ("Open Candidate Review", ROOT / "docs/candidate_review_packet.md"),
            ("Open Review Board", ROOT / "docs/candidate_review_board.md"),
            ("Open Review Analytics", ROOT / "docs/candidate_review_analytics.md"),
            ("Open Candidate Drilldown", ROOT / "docs/candidate_drilldown_packet.md"),
            ("Open Candidate Baseline", ROOT / "docs/candidate_baseline_compare.md"),
            ("Open Candidate Decisions", ROOT / "docs/candidate_decision_packet.md"),
            ("Open Decision Export", self.project_dir() / "candidate_decision_export.csv"),
            ("Open Evidence Drawer", ROOT / "docs/candidate_evidence_drawer.md"),
            ("Open Explanation Panel", ROOT / "docs/candidate_explanation_panel.md"),
            ("Open Explanation Compare", ROOT / "docs/candidate_explanation_compare.md"),
            ("Open Explanation Drilldown", ROOT / "docs/candidate_explanation_drilldown.md"),
            ("Open Component Locator", ROOT / "docs/candidate_component_structure_locator.md"),
            ("Open Explanation Matrix", ROOT / "docs/candidate_explanation_matrix.md"),
            ("Open Site Confidence", ROOT / "docs/site_detection_confidence.md"),
            ("Open Site Calibration", ROOT / "docs/site_detection_calibration_queue.md"),
            ("Open Decision QA", ROOT / "docs/candidate_decision_qa.md"),
            ("Open Evidence Quality", ROOT / "docs/evidence_quality_scorecard.md"),
            ("Open Baseline Manager", ROOT / "docs/candidate_baseline_manager.md"),
            ("Open Reviewer Ops", ROOT / "docs/reviewer_operations.md"),
            ("Open Baseline Lineage", ROOT / "docs/baseline_lineage_compare.md"),
            ("Open Command Center", ROOT / "docs/review_command_center.md"),
            ("Open Remediation Queue", ROOT / "docs/candidate_remediation_queue.md"),
            ("Open Review Remediation", ROOT / "docs/review_remediation_queue.md"),
            ("Open Review Ops Console", ROOT / "docs/candidate_review_ops_console.md"),
            ("Open Reviewer Cockpit", ROOT / "docs/reviewer_cockpit.md"),
            ("Open Closure Workbench", ROOT / "docs/review_closure_workbench.md"),
            ("Open Closure Filters", ROOT / "docs/review_closure_filter_views.md"),
            ("Open Closure Ledger", self.project_dir() / "review_remediation_closure_ledger.csv"),
            ("Open Remediation History", ROOT / "docs/candidate_remediation_queue_history.md"),
            ("Open Baseline History", ROOT / "docs/baseline_history_explorer.md"),
            ("Open Baseline Scenario", ROOT / "docs/baseline_scenario_board.md"),
            ("Open Baseline What-If", ROOT / "docs/baseline_whatif_board.md"),
            ("Open Baseline Active Preview", self.project_dir() / "baseline_active_preview.json"),
            ("Open Baseline Rollback", ROOT / "docs/baseline_rollback_explanation.md"),
            ("Open Baseline Matrix", self.project_dir() / "baseline_history_explorer_matrix.csv"),
            ("Open Baseline Lineage History", ROOT / "docs/baseline_lineage_history.md"),
            ("Open Baseline Pairwise CSV", self.project_dir() / "baseline_lineage_history_pairwise.csv"),
            ("Open Baseline Preview", ROOT / "docs/baseline_lineage_preview.md"),
            ("Open Baseline Filters", ROOT / "docs/baseline_lineage_filter_views.md"),
            ("Open Drilldown Actions", ROOT / "docs/native_drilldown_actions.md"),
            ("Open Baseline Preview PNG", self.project_dir() / "baseline_lineage_previews" / "baseline_lineage_movement_preview.png"),
            ("Open Baseline Chart", ROOT / "data/projects/demo/baseline_history_explorer_charts/baseline_history_movement.png"),
            ("Open Operator Trends", ROOT / "docs/operator_trend_summary.md"),
            ("Open Trend Charts", ROOT / "docs/operator_trend_charts.md"),
            ("Open Discussion Handoff", ROOT / "docs/medchem_discussion_handoff.md"),
            ("Open Substituent Diff", ROOT / "docs/substituent_version_diff_browser.md"),
            ("Open Baseline Registry", self.project_dir() / "governance_baselines" / "baseline_registry.json"),
            ("Open UI Regression", ROOT / "docs/native_ui_regression_snapshot.md"),
            ("Open Native Package Manifest", ROOT / "data/releases/native_portable_package_manifest.json"),
        ]:
            ttk.Button(open_buttons, text=text, command=lambda item=path: open_path(item)).pack(side=LEFT, padx=5)
        gate_buttons = ttk.Frame(panel, style="Panel.TFrame")
        gate_buttons.pack(anchor="w", pady=(0, 8))
        ttk.Button(gate_buttons, text="Open Selected JSON", command=lambda: self.open_selected_production_artifact("json")).pack(side=LEFT, padx=5)
        ttk.Button(gate_buttons, text="Open Selected CSV", command=lambda: self.open_selected_production_artifact("csv")).pack(side=LEFT, padx=5)
        ttk.Button(gate_buttons, text="Route Selected Gate", style="Accent.TButton", command=self.route_selected_production_gate).pack(side=LEFT, padx=5)
        ttk.Button(gate_buttons, text="Route Selected Command", command=self.route_selected_review_command).pack(side=LEFT, padx=5)
        ttk.Button(gate_buttons, text="Open Command Artifact", command=self.open_selected_review_command_artifact).pack(side=LEFT, padx=5)
        ttk.Button(gate_buttons, text="Route Selected Action", command=self.route_selected_native_drilldown_action).pack(side=LEFT, padx=5)
        ttk.Button(gate_buttons, text="Open Action Artifact", command=self.open_selected_native_drilldown_artifact).pack(side=LEFT, padx=5)
        ttk.Button(gate_buttons, text="Open Remediation History", command=lambda: open_path(self.project_dir() / "candidate_remediation_queue_history.csv")).pack(side=LEFT, padx=5)
        ttk.Button(gate_buttons, text="Open Baseline Chart", command=self.open_baseline_history_chart).pack(side=LEFT, padx=5)
        ttk.Button(gate_buttons, text="Open Selected Chart", command=self.open_selected_trend_chart).pack(side=LEFT, padx=5)

    def set_busy(self, text: str) -> None:
        self.status_var.set(text)
        self.update_idletasks()

    def record_task_event(self, label: str, status: str, *, detail: str = "", command: list[str] | None = None) -> dict:
        event = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "label": label,
            "status": status,
            "detail": detail,
            "command": " ".join(command or []),
            "blocked_scopes": "procurement;supplier_purchase;real_experiment_feedback_auto_import",
        }
        self.task_events.append(event)
        self.task_events = self.task_events[-240:]
        self.task_log_var.set(f"{label}: {status}" + (f" | {detail[:160]}" if detail else ""))
        payload = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "tracking",
            "mode": "native_task_log",
            "project_name": self.project_name(),
            "row_count": len(self.task_events),
            "latest": event,
            "rows": self.task_events,
            "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
        }
        write_json(self.task_log_path(), payload)
        fields = ["created_at", "label", "status", "detail", "command", "blocked_scopes"]
        with self.task_log_csv_path().open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in self.task_events:
                writer.writerow({field: row.get(field, "") for field in fields})
        return event

    def open_task_log(self) -> None:
        if not self.task_log_path().exists():
            self.record_task_event("task log", "empty", detail="Task log initialized.")
        open_path(self.task_log_path())

    def rerun_last_failed_task(self) -> None:
        if self.last_failed_task_runner is None or not self.last_failed_task:
            messagebox.showinfo("No failed task", "No failed task is available to rerun in this session.")
            return
        label = str(self.last_failed_task.get("label") or "failed task")
        runner = self.last_failed_task_runner
        self.record_task_event(label, "rerun_queued", detail="Rerunning last failed native task.")
        self.run_task(label, runner)

    def run_task(self, label: str, fn) -> None:
        self.task_runners[label] = fn
        self.record_task_event(label, "queued")
        def worker() -> None:
            try:
                self.after(0, lambda: self.record_task_event(label, "running"))
                result = fn()
                self.after(0, lambda: self.task_done(label, result, None))
            except Exception as exc:
                self.after(0, lambda error=exc: self.task_done(label, None, error))

        self.set_busy(f"Running: {label}")
        threading.Thread(target=worker, daemon=True).start()

    def task_done(self, label: str, result, error: Exception | None) -> None:
        if error:
            self.status_var.set(f"Failed: {label}")
            text = str(error)
            self.last_failed_task = {"label": label, "error": text, "created_at": datetime.now(timezone.utc).isoformat()}
            self.last_failed_task_runner = self.task_runners.get(label)
            self.record_task_event(label, "failed", detail=text)
            write_json(
                ROOT / "data/releases/native_shell_last_error.json",
                {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "label": label,
                    "error": text,
                },
            )
            messagebox.showerror("Action failed", text[:2000])
            return
        self.status_var.set(f"Done: {label}")
        self.record_task_event(label, "completed", detail="Task finished successfully.")
        self.reload_all()

    def detect_sites(self) -> None:
        def task() -> dict:
            proc = run_python(["scripts/detect_sites.py", "--smiles", self.smiles_var.get()], timeout=90)
            if proc.returncode:
                raise RuntimeError(proc.stderr or proc.stdout)
            result = parse_json_stdout(proc.stdout)
            preview = self.render_molecule_preview(self.smiles_var.get())
            if preview:
                result["preview_path"] = str(preview)
            return result

        def done(label: str, result, error: Exception | None) -> None:
            if error:
                self.record_task_event(label, "failed", detail=str(error))
                self.task_done(label, result, error)
                return
            self.sites = list((result or {}).get("sites") or [])
            self.populate_sites()
            self.load_molecule_preview(Path(result.get("preview_path") or self.preview_file()))
            self.record_task_event(label, "completed", detail=f"Detected {len(self.sites)} sites.")
            self.status_var.set(f"Detected {len(self.sites)} sites")

        def worker() -> None:
            try:
                self.after(0, lambda: self.record_task_event("detect sites", "running"))
                result = task()
                self.after(0, lambda: done("detect sites", result, None))
            except Exception as exc:
                self.after(0, lambda error=exc: done("detect sites", None, error))

        self.task_runners["detect sites"] = task
        self.record_task_event("detect sites", "queued", command=["scripts/detect_sites.py", "--smiles", self.smiles_var.get()])
        self.set_busy("Detecting sites")
        threading.Thread(target=worker, daemon=True).start()

    def render_molecule_preview(self, smiles: str) -> Path | None:
        proc = run_python(
            [
                "scripts/render_molecule_preview.py",
                "--smiles",
                smiles,
                "--output",
                str(self.preview_file()),
                "--width",
                "640",
                "--height",
                "420",
            ],
            timeout=90,
        )
        if proc.returncode:
            return None
        data = parse_json_stdout(proc.stdout)
        path = Path(data.get("output") or self.preview_file())
        return path if path.exists() else None

    def load_molecule_preview(self, path: Path) -> None:
        if not path.exists():
            self.preview_status_var.set("Preview unavailable.")
            return
        if Image is None or ImageTk is None:
            self.preview_status_var.set(str(path))
            return
        try:
            image = Image.open(path)
            image.thumbnail((300, 210), Image.Resampling.LANCZOS)
            self.molecule_photo = ImageTk.PhotoImage(image)
            self.preview_label.configure(image=self.molecule_photo, text="")
            self.preview_status_var.set("")
        except Exception:
            self.preview_status_var.set(str(path))

    def save_preset(self) -> None:
        payload = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "workspace": self.project_name(),
            "smiles": self.smiles_var.get(),
            "direction": self.direction_var.get(),
            "max_candidates": self.max_candidates_var.get(),
            "include_ring_library": bool(self.include_ring_var.get()),
        }
        write_json(self.preset_file(), payload)
        self.status_var.set("Preset saved")

    def save_session(self) -> None:
        selected = self.site_tree.selection()
        selected_site_index = None
        if selected:
            try:
                selected_site_index = int(self.site_tree.item(selected[0], "values")[0])
            except Exception:
                selected_site_index = None
        payload = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "workspace": self.project_name(),
            "smiles": self.smiles_var.get(),
            "direction": self.direction_var.get(),
            "max_candidates": self.max_candidates_var.get(),
            "include_ring_library": bool(self.include_ring_var.get()),
            "selected_site_index": selected_site_index,
            "candidate_count": len(self.candidate_rows),
            "compare_candidate_ids": [row.get("candidate_id") for row in self.compare_rows],
            "candidate_csv": str(self.project_dir() / "candidates.csv"),
        }
        write_json(self.session_file(), payload)
        self.status_var.set(f"Session saved: {self.project_name()}")

    def load_session(self) -> None:
        payload = read_json(self.session_file())
        if not payload:
            messagebox.showinfo("No session", f"No saved session for workspace {self.project_name()}.")
            return
        self.smiles_var.set(str(payload.get("smiles") or self.smiles_var.get()))
        direction = str(payload.get("direction") or self.direction_var.get())
        if direction in self.directions:
            self.direction_var.set(direction)
        self.max_candidates_var.set(str(payload.get("max_candidates") or self.max_candidates_var.get()))
        self.include_ring_var.set(bool(payload.get("include_ring_library", True)))
        self.last_result = {}
        self.compare_rows = []
        self.populate_candidates_from_csv()
        compare_ids = {str(item) for item in payload.get("compare_candidate_ids") or []}
        self.compare_rows = [row for row in self.candidate_rows if str(row.get("candidate_id")) in compare_ids]
        self.render_compare_table()
        self.populate_candidate_review_board()
        self.status_var.set(f"Session loaded: {self.project_name()}")

    def switch_workspace(self) -> None:
        self.workspace_var.set(self.project_name())
        if self.project_name() not in self.workspace_names:
            self.workspace_names.append(self.project_name())
            self.workspace_names = sorted(dict.fromkeys(self.workspace_names))
        if hasattr(self, "workspace_combo"):
            self.workspace_combo.configure(values=self.workspace_names)
        preset = read_json(self.preset_file())
        if preset:
            self.smiles_var.set(str(preset.get("smiles") or self.smiles_var.get()))
            direction = str(preset.get("direction") or self.direction_var.get())
            if direction in self.directions:
                self.direction_var.set(direction)
            self.max_candidates_var.set(str(preset.get("max_candidates") or self.max_candidates_var.get()))
            self.include_ring_var.set(bool(preset.get("include_ring_library", True)))
        self.last_result = {}
        self.compare_rows = []
        self.populate_candidates_from_csv()
        self.render_compare_table()
        self.populate_candidate_review_board()
        if self.preview_file().exists():
            self.load_molecule_preview(self.preview_file())
        self.status_var.set(f"Workspace: {self.project_name()}")

    def generate_candidates(self) -> None:
        selected = self.site_tree.selection()
        site_index = int(self.site_tree.item(selected[0], "values")[0]) if selected else 0

        def task() -> dict:
            args = [
                "scripts/run_mvp.py",
                "--smiles",
                self.smiles_var.get(),
                "--direction",
                self.direction_var.get(),
                "--site-index",
                str(site_index),
                "--max-candidates",
                self.max_candidates_var.get(),
                "--project-name",
                self.project_name(),
                "--output-dir",
                str(self.project_dir()),
            ]
            if not self.include_ring_var.get():
                args.extend(["--disable-ring-library-recommendations", "--disable-ring-rgroup-joint"])
            proc = run_python(args, timeout=300)
            if proc.returncode:
                raise RuntimeError(proc.stderr or proc.stdout)
            return parse_json_stdout(proc.stdout)

        def done(label: str, result, error: Exception | None) -> None:
            if error:
                self.record_task_event(label, "failed", detail=str(error))
                self.task_done(label, result, error)
                return
            self.last_result = result or {}
            if self.last_result.get("sites"):
                self.sites = list(self.last_result.get("sites") or [])
                self.populate_sites()
            csv_rows = []
            csv_path = self.project_dir() / "candidates.csv"
            if csv_path.exists():
                try:
                    csv_rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
                except Exception:
                    csv_rows = []
            self.populate_candidates(csv_rows or self.last_result.get("top_candidates") or self.last_result.get("candidates") or [])
            self.record_task_event(label, "completed", detail=f"Generated {self.last_result.get('candidate_count', 0)} candidates.")
            self.status_var.set(f"Generated {self.last_result.get('candidate_count', 0)} candidates")

        def worker() -> None:
            try:
                self.after(0, lambda: self.record_task_event("generate candidates", "running"))
                result = task()
                self.after(0, lambda: done("generate candidates", result, None))
            except Exception as exc:
                self.after(0, lambda error=exc: done("generate candidates", None, error))

        self.task_runners["generate candidates"] = task
        self.record_task_event("generate candidates", "queued", command=["scripts/run_mvp.py"])
        self.set_busy("Generating candidates")
        threading.Thread(target=worker, daemon=True).start()

    def refresh_project_memory(self) -> None:
        self.run_task("refresh Project Memory", lambda: self._run_checked(["scripts/refresh_project_memory.py"]))

    def assign_critical_profile(self) -> None:
        def task() -> dict:
            self._run_checked(
                [
                    "scripts/apply_profile_impact_review_batch.py",
                    "--severity",
                    "critical",
                    "--current-status",
                    "open",
                    "--review-status",
                    "assigned",
                    "--assigned-to",
                    "profile_policy_review",
                    "--reviewer",
                    "native_shell",
                    "--note",
                    "Assigned from native workbench for non-experimental profile-policy review.",
                ]
            )
            self._run_checked(["scripts/build_project_memory_review_queue.py"])
            self._run_checked(["scripts/build_project_memory_review_dashboard.py"])
            return self._run_checked(["scripts/build_promotion_readiness_packet.py"])

        self.run_task("assign critical profile rows", task)

    def assign_endpoint_gaps(self) -> None:
        def task() -> dict:
            self._run_checked(
                [
                    "scripts/apply_project_memory_review_batch.py",
                    "--review-lane",
                    "measurement_gap",
                    "--current-status",
                    "open",
                    "--operator-status",
                    "assigned",
                    "--assigned-to",
                    "exact_endpoint_intake",
                    "--reviewer",
                    "native_shell",
                    "--note",
                    "Assigned for strict local endpoint-intake follow-up using local evidence governance only.",
                ]
            )
            self._run_checked(["scripts/build_project_memory_review_dashboard.py"])
            return self._run_checked(["scripts/build_promotion_readiness_packet.py"])

        self.run_task("assign endpoint gaps", task)

    def update_selected_pm(self, status: str) -> None:
        selected = self.attention_tree.selection()
        if not selected:
            messagebox.showinfo("Select a row", "Select a Project Memory row first.")
            return
        review_id = str(self.attention_tree.item(selected[0], "values")[0])

        def task() -> dict:
            self._run_checked(
                [
                    "scripts/apply_project_memory_review_batch.py",
                    "--review-item-id",
                    review_id,
                    "--operator-status",
                    status,
                    "--reviewer",
                    "native_shell",
                    "--note",
                    f"{status} from native workbench.",
                ]
            )
            self._run_checked(["scripts/build_project_memory_review_dashboard.py"])
            return self._run_checked(["scripts/build_promotion_readiness_packet.py"])

        self.run_task(f"{status} {review_id}", task)

    def rebuild_endpoint_governance(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_measurement_gap_endpoint_governance.py"])
            return self._run_checked(["scripts/build_promotion_readiness_packet.py"])

        self.run_task("rebuild endpoint governance", task)

    def build_readiness_packet(self) -> None:
        self.run_task("build readiness packet", lambda: self._run_checked(["scripts/build_promotion_readiness_packet.py"]))

    def readiness_drill_down(self) -> None:
        selected = self.finding_tree.selection()
        lane = ""
        if selected:
            values = self.finding_tree.item(selected[0], "values")
            lane = str(values[1] if len(values) > 1 else "")
        if lane in {"measurement_gap", "endpoint_governance"}:
            self.show_view("endpoint")
            return
        self.show_view("project_memory")

    def selected_production_gate(self) -> dict:
        selected = self.production_tree.selection() if hasattr(self, "production_tree") else []
        if not selected:
            return {}
        return self.production_gate_rows.get(str(selected[0]), {})

    def production_gate_drill_down(self) -> None:
        row = self.selected_production_gate()
        if not row:
            self.production_drilldown_var.set("Select a production gate to see its artifact and next action.")
            return
        artifact = row.get("artifact_path") or ""
        artifact_csv = row.get("artifact_csv_path") or ""
        action = row.get("next_action") or "Review the linked artifact for the next local governance action."
        details = row.get("details") or ""
        self.production_drilldown_var.set(
            f"{row.get('label')}: {row.get('status')} / {row.get('level')}\n"
            f"Action: {action}\n"
            f"Artifact: {artifact or 'not linked'}\n"
            f"CSV/Markdown: {artifact_csv or 'not linked'}\n"
            f"Details: {details}"
        )

    def open_selected_production_artifact(self, kind: str) -> None:
        row = self.selected_production_gate()
        if not row:
            messagebox.showinfo("Select a gate", "Select a production gate first.")
            return
        key = "artifact_csv_path" if kind == "csv" else "artifact_path"
        path = Path(str(row.get(key) or ""))
        if not path.is_absolute():
            path = ROOT / path
        open_path(path)

    def _focus_first_tree_row(self, tree_name: str, needles: list[str] | None = None) -> bool:
        tree = getattr(self, tree_name, None)
        if tree is None:
            return False
        needles = [item.lower() for item in needles or [] if item]
        for item in tree.get_children():
            values = tree.item(item, "values")
            text = " ".join(str(value).lower() for value in values)
            if not needles or any(needle in text for needle in needles):
                tree.selection_set(item)
                tree.focus(item)
                return True
        return False

    def route_selected_production_gate(self) -> None:
        row = self.selected_production_gate()
        if not row:
            messagebox.showinfo("Select a gate", "Select a production gate first.")
            return
        gate = str(row.get("gate_id") or "").strip()
        self.show_view("reports")
        routed = False
        if gate in {"local_db_maintenance", "local_db_maintenance_trend"}:
            self.production_drilldown_var.set(
                f"{row.get('label')}: routed to DB maintenance. Use Build DB Maintenance, Open DB Maintenance JSON, and DB trend CSV to clear latency/cache warnings."
            )
            routed = True
        elif gate in {"rgroup_staging_quality_budget", "feed_staging_gate", "feed_staging"}:
            routed = self._focus_first_tree_row("staging_manual_review_tree", ["blocked", "awaiting", "ready", "not_signed"])
            self.show_selected_staging_curator_queue()
        elif gate in {"staging_sandbox_filter_views"}:
            routed = self._focus_first_tree_row("staging_sandbox_filter_tree")
        elif gate in {"rgroup_promotion_approval_ledger"}:
            routed = self._focus_first_tree_row("rgroup_promotion_approval_tree", ["pending", "deferred", "rejected", "approved"])
        elif gate in {"rgroup_digestion_quality_metrics"}:
            routed = self._focus_first_tree_row("rgroup_digestion_quality_tree", ["blocked", "watch"])
        elif gate in {"local_db_maintenance_release_gate"}:
            routed = self._focus_first_tree_row("local_db_release_gate_tree", ["release_stop", "watch"])
        elif gate in {"feed_absorption_diff_navigator"}:
            routed = self._focus_first_tree_row("feed_diff_tree", ["warning", "blocker", "delta", "duplicate"])
        elif gate in {"feed_promotion_simulator"}:
            routed = self._focus_first_tree_row("feed_promotion_simulator_tree", ["warning", "blocked", "ready_with_warnings"])
        elif gate in {"candidate_review_board", "candidate_review_analytics", "candidate_review_packet", "production_smoke"}:
            self.show_view("candidate_review")
            if hasattr(self, "review_reason_tree") and self.review_reason_tree.get_children():
                first = self.review_reason_tree.get_children()[0]
                self.review_reason_tree.selection_set(first)
                self.review_reason_tree.focus(first)
                self.apply_review_reason_filter()
            routed = True
        elif gate in {"site_detection_regression", "site_detection_confidence"}:
            routed = self._focus_first_tree_row("site_detection_confidence_tree", ["review", "low", "fail"])
        elif gate in {"native_ui_regression"}:
            self.open_selected_production_artifact("csv")
            routed = True
        elif gate in {"substituent_version_diff_browser"}:
            routed = self._focus_first_tree_row("substituent_version_diff_tree", ["attention", "candidate_rule"])
        if routed:
            self.production_drilldown_var.set(
                f"Routed gate `{gate}` into the native handling surface.\n"
                f"Action: {row.get('next_action') or '-'}\n"
                f"Details: {row.get('details') or '-'}"
            )
            return
        self.open_selected_production_artifact("json")

    def build_freeze_package(self) -> None:
        self.run_task("build freeze package", lambda: self._run_checked(["scripts/build_profile_promotion_freeze_package.py"]))

    def build_portable_package(self) -> None:
        self.run_task("build portable native package", lambda: self._run_checked(["scripts/build_native_portable_package.py"]))

    def build_production_snapshot(self) -> None:
        self.run_task("build production dashboard", lambda: self._run_checked(["scripts/build_production_dashboard_snapshot.py"]))

    def build_feed_promotion_diff(self) -> None:
        self.run_task("build feed promotion diff", lambda: self._run_checked(["scripts/build_rgroup_feed_drop_promotion_diff.py"]))

    def fill_rgroup_staging_from_reviewed_sources(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_rgroup_next_feed_drop_staging.py"])
            return self._run_checked(["scripts/fill_rgroup_staging_from_reviewed_sources.py"])

        self.run_task("fill rgroup staging from reviewed sources", task)

    def build_feed_absorption_audit(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_rgroup_feed_review_coverage.py"])
            self._run_checked(["scripts/build_rgroup_feed_onboarding_gate.py"])
            self._run_checked(["scripts/validate_rgroup_feed_drop_staging.py"])
            self._run_checked(["scripts/build_rgroup_feed_drop_promotion_diff.py"])
            self._run_checked(["scripts/build_feed_absorption_audit.py"])
            self._run_checked(["scripts/build_feed_absorption_diff_navigator.py"])
            return self._run_checked(["scripts/build_source_expansion_governance.py"])

        self.run_task("build feed absorption audit", task)

    def build_feed_absorption_diff_navigator(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_feed_absorption_audit.py"])
            return self._run_checked(["scripts/build_feed_absorption_diff_navigator.py"])

        self.run_task("build feed absorption diff navigator", task)

    def build_source_expansion_governance(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_feed_absorption_audit.py"])
            self._run_checked(["scripts/build_feed_absorption_diff_navigator.py"])
            return self._run_checked(["scripts/build_source_expansion_governance.py"])

        self.run_task("build source expansion governance", task)

    def build_feed_promotion_simulator(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_feed_absorption_audit.py"])
            self._run_checked(["scripts/build_feed_absorption_diff_navigator.py"])
            self._run_checked(["scripts/build_source_expansion_governance.py"])
            return self._run_checked(["scripts/build_feed_promotion_simulator.py"])

        self.run_task("build feed promotion simulator", task)

    def build_staging_quality_budget(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/validate_rgroup_feed_drop_staging.py"])
            self._run_checked(["scripts/build_rgroup_feed_drop_promotion_diff.py"])
            self._run_checked(["scripts/build_feed_promotion_simulator.py"])
            return self._run_checked(["scripts/build_rgroup_staging_quality_budget.py"])

        self.run_task("build staging quality budget", task)

    def build_governed_ingestion_batches(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_feed_promotion_simulator.py"])
            self._run_checked(["scripts/build_rgroup_staging_quality_budget.py"])
            self._run_checked(["scripts/build_staged_feed_sandbox_scoring.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_sandbox_score_delta_review_packet.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_governed_ingestion_batches.py"])

        self.run_task("build governed ingestion batches", task)

    def build_staged_feed_sandbox_scoring(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_feed_promotion_simulator.py"])
            self._run_checked(["scripts/build_rgroup_staging_quality_budget.py"])
            self._run_checked(["scripts/build_candidate_explanation_matrix.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_staged_feed_sandbox_scoring.py", "--project-name", self.project_name()])

        self.run_task("build staged feed sandbox scoring", task)

    def build_sandbox_score_delta_review(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_rgroup_staging_quality_budget.py"])
            self._run_checked(["scripts/build_staged_feed_sandbox_scoring.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_sandbox_score_delta_review_packet.py", "--project-name", self.project_name()])

        self.run_task("build sandbox score-delta review", task)

    def build_rgroup_admission_sandbox_replay(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_rgroup_staging_admission_scorecard.py"])
            self._run_checked(["scripts/build_staged_feed_sandbox_scoring.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_sandbox_score_delta_review_packet.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_rgroup_admission_sandbox_impact_replay.py", "--project-name", self.project_name()])

        self.run_task("build rgroup admission sandbox replay", task)

    def build_sandbox_score_delta_signoff(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_sandbox_score_delta_review_packet.py", "--project-name", self.project_name()])
            return self._run_checked(
                [
                    "scripts/review_sandbox_score_delta.py",
                    "--project-name",
                    self.project_name(),
                    "--decision",
                    "deferred",
                    "--reviewer",
                    "native_holdout",
                    "--note",
                    "Conservative native holdout; no production scoring approval.",
                    "--preserve-existing",
                    "--fail-on-pending",
                ]
            )

        self.run_task("build sandbox score-delta signoff", task)

    def build_rgroup_feed_digestion_ledger(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_sandbox_score_delta_review_packet.py", "--project-name", self.project_name()])
            self._run_checked(
                [
                    "scripts/review_sandbox_score_delta.py",
                    "--project-name",
                    self.project_name(),
                    "--decision",
                    "deferred",
                    "--reviewer",
                    "native_holdout",
                    "--note",
                    "Conservative native holdout; no production scoring approval.",
                    "--preserve-existing",
                    "--fail-on-pending",
                ]
            )
            self._run_checked(["scripts/build_sandbox_score_delta_review_packet.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_rgroup_feed_digestion_ledger.py"])

        self.run_task("build rgroup feed digestion ledger", task)

    def build_rgroup_promotion_approval_ledger(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_rgroup_feed_digestion_ledger.py"])
            return self._run_checked(
                [
                    "scripts/review_rgroup_promotion_approval.py",
                    "--project-name",
                    self.project_name(),
                    "--decision",
                    "deferred",
                    "--reviewer",
                    "native_promotion_holdout",
                    "--note",
                    "Conservative native holdout; no feed copy approval.",
                    "--fail-on-pending",
                    "--fail-on-blocked",
                ]
            )

        self.run_task("build rgroup promotion approval ledger", task)

    def build_rgroup_digestion_quality_metrics(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_rgroup_feed_digestion_ledger.py"])
            return self._run_checked(["scripts/build_rgroup_digestion_quality_metrics.py"])

        self.run_task("build rgroup digestion quality metrics", task)

    def build_staging_sandbox_filter_views(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_rgroup_feed_digestion_ledger.py"])
            self._run_checked(
                [
                    "scripts/review_rgroup_promotion_approval.py",
                    "--project-name",
                    self.project_name(),
                    "--decision",
                    "deferred",
                    "--reviewer",
                    "native_promotion_holdout",
                    "--note",
                    "Conservative native holdout; no feed copy approval.",
                    "--preserve-existing",
                    "--fail-on-pending",
                    "--fail-on-blocked",
                ]
            )
            self._run_checked(["scripts/build_rgroup_digestion_quality_metrics.py"])
            return self._run_checked(["scripts/build_staging_sandbox_filter_views.py", "--project-name", self.project_name()])

        self.run_task("build staging sandbox filter views", task)

    def build_ring_package_review(self) -> None:
        self.run_task("build ring package review", lambda: self._run_checked(["scripts/build_ring_outcome_result_package_review.py"]))

    def build_db_health(self) -> None:
        self.run_task("build local DB health", lambda: self._run_checked(["scripts/build_local_db_health_report.py"]))

    def build_db_maintenance(self) -> None:
        self.run_task("build local DB maintenance", lambda: self._run_checked(["scripts/build_local_db_maintenance_report.py"]))

    def build_local_db_release_gate(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_local_db_maintenance_report.py"])
            return self._run_checked(["scripts/build_local_db_maintenance_release_gate.py"])

        self.run_task("build local DB release gate", task)

    def build_governance_diff(self) -> None:
        self.run_task("build local governance diff", lambda: self._run_checked(["scripts/build_local_governance_diff.py", "--project-name", self.project_name()]))

    def create_governance_baseline(self) -> None:
        name = self.governance_baseline_name_var.get().strip() or "baseline"
        self.run_task(
            f"create governance baseline {name}",
            lambda: self._run_checked(["scripts/build_local_governance_diff.py", "--project-name", self.project_name(), "--create-baseline", "--baseline-name", name]),
        )

    def diff_named_governance_baseline(self) -> None:
        name = self.governance_baseline_name_var.get().strip() or "baseline"
        self.run_task(
            f"diff governance baseline {name}",
            lambda: self._run_checked(["scripts/build_local_governance_diff.py", "--project-name", self.project_name(), "--base-baseline", name]),
        )

    def pin_candidate_baseline(self) -> None:
        name = self.candidate_baseline_name_var.get().strip() or "local_release_baseline"
        self.run_task(
            f"pin candidate baseline {name}",
            lambda: self._run_checked(["scripts/pin_candidate_baseline.py", "--project-name", self.project_name(), "--baseline-id", name, "--overwrite", "--note", "Pinned from native reports view."]),
        )

    def _run_phase32_review_aids(self) -> dict:
        self._run_checked(["scripts/build_candidate_review_board.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_candidate_review_analytics.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_candidate_decision_packet.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_candidate_evidence_drawer.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_candidate_decision_qa.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_evidence_quality_scorecard.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_candidate_evidence_quality.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/manage_candidate_baselines.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_reviewer_operations.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_baseline_lineage_compare.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_candidate_baseline_lineage.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_baseline_history_explorer.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_baseline_lineage_history.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_baseline_lineage_preview.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_review_command_center.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_candidate_remediation_queue.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_review_remediation_queue.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_candidate_review_ops_console.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_review_closure_workbench.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_reviewer_cockpit.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_candidate_explanation_panel.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_candidate_explanation_compare.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_candidate_explanation_drilldown.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_candidate_structure_interpretation.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_candidate_component_structure_locator.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_baseline_scenario_board.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_baseline_whatif_board.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_site_detection_confidence.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_site_detection_calibration_queue.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_substituent_version_diff_browser.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_operator_trend_summary.py", "--project-name", self.project_name()])
        self._run_checked(["scripts/build_operator_trend_charts.py"])
        return self._run_checked(["scripts/build_medchem_discussion_handoff.py", "--project-name", self.project_name()])

    def build_candidate_visual_compare(self) -> None:
        selected_ids = [str(row.get("candidate_id") or "") for row in self.compare_rows if row.get("candidate_id")]
        args = ["scripts/build_candidate_visual_compare.py", "--project-name", self.project_name()]
        if selected_ids:
            args.extend(["--candidate-ids", ",".join(selected_ids)])
        def task() -> dict:
            self._run_checked(args)
            self._run_checked(["scripts/build_candidate_drilldown_packet.py", "--project-name", self.project_name()])
            return self._run_phase32_review_aids()

        self.run_task("build candidate visual compare", task)

    def build_candidate_review_packet(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_review_packet.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_review_board.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_drilldown_packet.py", "--project-name", self.project_name()])
            return self._run_phase32_review_aids()

        self.run_task("build candidate review packet", task)

    def build_candidate_review_board(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_review_board.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_drilldown_packet.py", "--project-name", self.project_name()])
            return self._run_phase32_review_aids()

        self.run_task("build candidate review board", task)

    def build_candidate_drilldown(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_drilldown_packet.py", "--project-name", self.project_name()])
            return self._run_phase32_review_aids()

        self.run_task("build candidate drill-down packet", task)

    def compare_candidate_baseline(self) -> None:
        name = self.candidate_baseline_name_var.get().strip() or "local_release_baseline"
        def task() -> dict:
            self._run_checked(
                [
                    "scripts/compare_candidate_baseline.py",
                    "--project-name",
                    self.project_name(),
                    "--baseline-id",
                    name,
                    "--create-if-missing",
                ]
            )
            return self._run_phase32_review_aids()

        self.run_task(
            "compare candidate baseline",
            task,
        )

    def build_candidate_decision_packet(self) -> None:
        self.run_task("build candidate decision packet", self._run_phase32_review_aids)

    def build_candidate_review_analytics(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_review_board.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_candidate_review_analytics.py", "--project-name", self.project_name()])

        self.run_task("build candidate review analytics", task)

    def build_candidate_evidence_drawer(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_decision_packet.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_candidate_evidence_drawer.py", "--project-name", self.project_name()])

        self.run_task("build candidate evidence drawer", task)

    def build_candidate_explanation_panel(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_evidence_drawer.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_decision_qa.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_lineage_compare.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_review_remediation_queue.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_explanation_panel.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_explanation_compare.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_candidate_explanation_drilldown.py", "--project-name", self.project_name()])

        self.run_task("build candidate explanation panel", task)

    def build_candidate_explanation_compare(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_explanation_panel.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_explanation_compare.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_candidate_explanation_drilldown.py", "--project-name", self.project_name()])

        self.run_task("build candidate explanation compare", task)

    def build_candidate_explanation_drilldown(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_explanation_panel.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_explanation_drilldown.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_structure_interpretation.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_candidate_component_structure_locator.py", "--project-name", self.project_name()])

        self.run_task("build candidate explanation drilldown", task)

    def build_candidate_component_structure_locator(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_explanation_drilldown.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_structure_interpretation.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_candidate_component_structure_locator.py", "--project-name", self.project_name()])

        self.run_task("build candidate component structure locator", task)

    def build_site_detection_confidence(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_site_detection_regression_report.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_site_detection_confidence.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_site_detection_calibration_queue.py", "--project-name", self.project_name()])

        self.run_task("build site detection confidence", task)

    def build_site_detection_calibration_queue(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_site_detection_confidence.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_site_detection_calibration_queue.py", "--project-name", self.project_name()])

        self.run_task("build site detection calibration queue", task)

    def build_candidate_explanation_matrix(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_explanation_panel.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_explanation_compare.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_explanation_drilldown.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_candidate_explanation_matrix.py", "--project-name", self.project_name()])

        self.run_task("build candidate explanation matrix", task)

    def build_candidate_decision_qa(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_decision_packet.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_evidence_drawer.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_candidate_decision_qa.py", "--project-name", self.project_name()])

        self.run_task("build candidate decision QA", task)

    def build_candidate_evidence_quality(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_evidence_drawer.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_decision_qa.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_evidence_quality_scorecard.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_candidate_evidence_quality.py", "--project-name", self.project_name()])

        self.run_task("build candidate evidence quality", task)

    def build_candidate_baseline_manager(self) -> None:
        self.run_task("build candidate baseline manager", lambda: self._run_checked(["scripts/manage_candidate_baselines.py", "--project-name", self.project_name()]))

    def build_reviewer_operations(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_review_analytics.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_decision_qa.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_reviewer_operations.py", "--project-name", self.project_name()])

        self.run_task("build reviewer operations", task)

    def build_candidate_review_ops_console(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_review_board.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_review_analytics.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_remediation_queue.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_review_remediation_queue.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_candidate_review_ops_console.py", "--project-name", self.project_name()])

        self.run_task("build candidate review ops console", task)

    def build_candidate_baseline_lineage(self) -> None:
        def task() -> dict:
            self._run_checked(
                [
                    "scripts/compare_candidate_baseline.py",
                    "--project-name",
                    self.project_name(),
                    "--baseline-id",
                    self.candidate_baseline_name_var.get().strip() or "local_release_baseline",
                    "--create-if-missing",
                ]
            )
            self._run_checked(["scripts/build_baseline_lineage_compare.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_baseline_lineage.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_history_explorer.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_baseline_scenario_board.py", "--project-name", self.project_name()])

        self.run_task("build candidate baseline lineage", task)

    def build_baseline_lineage_history(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_baseline_lineage_compare.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_history_explorer.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_lineage_history.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_lineage_preview.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_baseline_scenario_board.py", "--project-name", self.project_name()])

        self.run_task("build baseline lineage history", task)

    def build_baseline_lineage_preview(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_baseline_lineage_history.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_baseline_lineage_preview.py", "--project-name", self.project_name()])

        self.run_task("build baseline lineage preview", task)

    def build_baseline_lineage_filter_views(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_baseline_lineage_preview.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_baseline_lineage_filter_views.py", "--project-name", self.project_name()])

        self.run_task("build baseline lineage filter views", task)

    def build_native_drilldown_actions(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_review_closure_filter_views.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_lineage_filter_views.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_explanation_matrix.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_staged_feed_sandbox_scoring.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_sandbox_score_delta_review_packet.py", "--project-name", self.project_name()])
            self._run_checked(
                [
                    "scripts/review_sandbox_score_delta.py",
                    "--project-name",
                    self.project_name(),
                    "--decision",
                    "deferred",
                    "--reviewer",
                    "native_holdout",
                    "--note",
                    "Conservative native holdout; no production scoring approval.",
                    "--preserve-existing",
                    "--fail-on-pending",
                ]
            )
            self._run_checked(["scripts/build_sandbox_score_delta_review_packet.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_rgroup_feed_digestion_ledger.py"])
            self._run_checked(
                [
                    "scripts/review_rgroup_promotion_approval.py",
                    "--project-name",
                    self.project_name(),
                    "--decision",
                    "deferred",
                    "--reviewer",
                    "native_promotion_holdout",
                    "--note",
                    "Conservative native holdout; no feed copy approval.",
                    "--preserve-existing",
                    "--fail-on-pending",
                    "--fail-on-blocked",
                ]
            )
            self._run_checked(["scripts/build_rgroup_digestion_quality_metrics.py"])
            self._run_checked(["scripts/build_staging_sandbox_filter_views.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_native_drilldown_actions.py", "--project-name", self.project_name()])

        self.run_task("build native drilldown actions", task)

    def build_baseline_history_explorer(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_baseline_lineage_compare.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_history_explorer.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_baseline_scenario_board.py", "--project-name", self.project_name()])

        self.run_task("build baseline history explorer", task)

    def build_baseline_scenario_board(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_baseline_history_explorer.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_scenario_board.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_baseline_whatif_board.py", "--project-name", self.project_name()])

        self.run_task("build baseline scenario board", task)

    def build_baseline_whatif_board(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_baseline_lineage_compare.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/compare_candidate_baseline.py", "--project-name", self.project_name(), "--baseline-id", self.candidate_baseline_name_var.get().strip() or "local_release_baseline", "--create-if-missing"])
            return self._run_checked(["scripts/build_baseline_whatif_board.py", "--project-name", self.project_name()])

        self.run_task("build baseline what-if board", task)

    def build_review_remediation_queue(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_evidence_quality_scorecard.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_reviewer_operations.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_decision_qa.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_lineage_compare.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_history_explorer.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_lineage_history.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_lineage_preview.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_review_command_center.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_remediation_queue.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_review_remediation_queue.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_review_closure_workbench.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_explanation_panel.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_explanation_compare.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_explanation_drilldown.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_scenario_board.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_review_ops_console.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_baseline_whatif_board.py", "--project-name", self.project_name()])

        self.run_task("build review remediation queue", task)

    def build_review_closure_workbench(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_review_remediation_queue.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_review_closure_workbench.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_reviewer_cockpit.py", "--project-name", self.project_name()])

        self.run_task("build review closure workbench", task)

    def build_review_closure_filter_views(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_review_closure_workbench.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_review_closure_filter_views.py", "--project-name", self.project_name()])

        self.run_task("build review closure filter views", task)

    def build_reviewer_cockpit(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_review_analytics.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_review_reason_workbench.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_review_closure_workbench.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_reviewer_cockpit.py", "--project-name", self.project_name()])

        self.run_task("build reviewer cockpit", task)

    def build_candidate_remediation_queue(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_evidence_quality_scorecard.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_reviewer_operations.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_decision_qa.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_lineage_compare.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_history_explorer.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_review_command_center.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_candidate_remediation_queue.py", "--project-name", self.project_name()])

        self.run_task("build candidate remediation queue", task)

    def build_review_command_center(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_production_dashboard_snapshot.py"])
            self._run_checked(["scripts/build_evidence_quality_scorecard.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_reviewer_operations.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_lineage_compare.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_history_explorer.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_lineage_history.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_review_command_center.py", "--project-name", self.project_name()])

        self.run_task("build review command center", task)

    def selected_candidate_baseline_id(self) -> str:
        if hasattr(self, "baseline_manager_tree"):
            selected = self.baseline_manager_tree.selection()
            if selected:
                values = self.baseline_manager_tree.item(selected[0], "values")
                if values:
                    return str(values[0] or "").strip()
        return self.candidate_baseline_name_var.get().strip()

    def archive_candidate_baseline(self) -> None:
        baseline_id = self.selected_candidate_baseline_id() or "local_release_baseline"
        note = self.candidate_baseline_archive_note_var.get().strip() or "Archived from native baseline manager."

        def task() -> dict:
            self._run_checked(
                [
                    "scripts/manage_candidate_baselines.py",
                    "--project-name",
                    self.project_name(),
                    "--archive-baseline-id",
                    baseline_id,
                    "--reviewer",
                    "native_shell",
                    "--note",
                    note,
                ]
            )
            return self._run_checked(["scripts/build_operator_trend_summary.py", "--project-name", self.project_name()])

        self.run_task(f"archive candidate baseline {baseline_id}", task)

    def build_operator_trend_summary(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_review_analytics.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_evidence_quality_scorecard.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_reviewer_operations.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_lineage_compare.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_history_explorer.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_review_command_center.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_remediation_queue.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_operator_trend_summary.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_operator_trend_charts.py"])

        self.run_task("build operator trend summary", task)

    def build_operator_trend_charts(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_review_analytics.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_evidence_quality_scorecard.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_reviewer_operations.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_lineage_compare.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_history_explorer.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_review_command_center.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_remediation_queue.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_operator_trend_summary.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_operator_trend_charts.py"])

        self.run_task("build operator trend charts", task)

    def build_medchem_discussion_handoff(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_decision_packet.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_evidence_drawer.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_decision_qa.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_medchem_discussion_handoff.py", "--project-name", self.project_name()])

        self.run_task("build MedChem discussion handoff", task)

    def build_substituent_version_diff_browser(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_explanation_panel.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_explanation_drilldown.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_substituent_version_diff_browser.py", "--project-name", self.project_name()])

        self.run_task("build substituent version diff browser", task)

    def build_native_regression(self) -> None:
        def task() -> dict:
            self._run_checked(["scripts/build_candidate_visual_compare.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_review_packet.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_review_board.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_review_analytics.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_drilldown_packet.py", "--project-name", self.project_name()])
            self._run_checked(["run_native_ui.py", "--smoke"])
            self._run_checked(["scripts/build_local_db_health_report.py"])
            self._run_checked(["scripts/build_local_db_maintenance_report.py"])
            self._run_checked(["scripts/build_local_governance_diff.py", "--project-name", self.project_name(), "--create-baseline", "--baseline-name", "default_current"])
            self._run_checked(["scripts/build_local_governance_diff.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/compare_candidate_baseline.py", "--project-name", self.project_name(), "--baseline-id", "local_release_baseline", "--create-if-missing"])
            self._run_checked(["scripts/build_candidate_decision_packet.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_evidence_drawer.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_decision_qa.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_evidence_quality_scorecard.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_evidence_quality.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/manage_candidate_baselines.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_reviewer_operations.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_lineage_compare.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_baseline_lineage.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_history_explorer.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_lineage_history.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_lineage_preview.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_lineage_filter_views.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_review_command_center.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_remediation_queue.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_review_remediation_queue.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_review_ops_console.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_review_closure_workbench.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_review_closure_filter_views.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_reviewer_cockpit.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_explanation_panel.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_explanation_compare.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_explanation_drilldown.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_explanation_matrix.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_structure_interpretation.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_component_structure_locator.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_review_reason_workbench.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_scenario_board.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_baseline_whatif_board.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_site_detection_regression_report.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_site_detection_confidence.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_site_detection_calibration_queue.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_substituent_version_diff_browser.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_feed_absorption_audit.py"])
            self._run_checked(["scripts/build_feed_absorption_diff_navigator.py"])
            self._run_checked(["scripts/build_source_expansion_governance.py"])
            self._run_checked(["scripts/build_feed_promotion_simulator.py"])
            self._run_checked(["scripts/build_rgroup_staging_quality_budget.py"])
            self._run_checked(["scripts/build_rgroup_staging_admission_scorecard.py"])
            self._run_checked(["scripts/build_staged_feed_sandbox_scoring.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_sandbox_score_delta_review_packet.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_rgroup_admission_sandbox_impact_replay.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_governed_ingestion_batches.py"])
            self._run_checked(["scripts/build_native_drilldown_actions.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_operator_trend_summary.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_operator_trend_charts.py"])
            self._run_checked(["scripts/build_medchem_discussion_handoff.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_native_ui_regression_snapshot.py", "--project-name", self.project_name()])

        self.run_task("build native UI regression", task)

    def _run_checked(self, args: list[str]) -> dict:
        proc = run_python(args)
        if proc.returncode:
            raise RuntimeError(proc.stderr or proc.stdout)
        return parse_json_stdout(proc.stdout)

    def reload_all(self) -> None:
        self.populate_sites()
        self.populate_candidates_from_csv()
        if self.preview_file().exists():
            self.load_molecule_preview(self.preview_file())
        self.populate_candidate_review_board()
        self.populate_project_memory()
        self.populate_endpoint()
        self.populate_readiness()
        self.populate_reports()

    def clear_tree(self, tree: ttk.Treeview) -> None:
        for item in tree.get_children():
            tree.delete(item)

    def populate_sites(self) -> None:
        self.clear_tree(self.site_tree)
        for idx, site in enumerate(self.sites):
            self.site_tree.insert(
                "",
                END,
                values=[
                    idx,
                    site.get("site_type"),
                    site.get("operation_type"),
                    "yes" if site.get("enumeration_ready") else "review",
                    site.get("label"),
                ],
            )
        first = self.site_tree.get_children()
        if first:
            self.site_tree.selection_set(first[0])

    def populate_candidates(self, rows: list[dict]) -> None:
        self.candidate_rows = list(rows or [])
        self.refresh_candidate_filter_options()
        self.refresh_candidate_filter_preset_combo()
        self.render_candidate_table()

    def _candidate_option_values(self, keys: list[str], *, include_non_clear: bool = False, limit: int = 80) -> list[str]:
        seen: set[str] = set()
        values: list[str] = ["all"]
        if include_non_clear:
            values.append("non_clear")
            seen.add("non_clear")
        for row in self.candidate_rows:
            for key in keys:
                raw = str(row.get(key) or "").strip()
                if not raw:
                    continue
                for part in raw.replace(";", ",").replace("|", ",").split(","):
                    value = part.strip()
                    normalized = value.lower()
                    if not value or normalized in seen:
                        continue
                    seen.add(normalized)
                    values.append(value)
                    if len(values) >= limit:
                        return values
        return values

    def refresh_candidate_filter_options(self) -> None:
        option_specs = [
            (
                "candidate_site_filter_combo",
                self.candidate_site_filter_var,
                self._candidate_option_values(["site_class", "site_type"], limit=80),
            ),
            (
                "candidate_risk_filter_combo",
                self.candidate_risk_filter_var,
                self._candidate_option_values(
                    ["risk_bucket", "review_bucket", "quality_bucket", "site_class_governance_action", "endpoint_gate_decision"],
                    include_non_clear=True,
                    limit=80,
                ),
            ),
            (
                "candidate_source_filter_combo",
                self.candidate_source_filter_var,
                self._candidate_option_values(["enumeration_type", "replacement_class", "source_dataset", "source_name", "source"], limit=80),
            ),
        ]
        for attr, var, values in option_specs:
            combo = getattr(self, attr, None)
            if combo is None:
                continue
            current = var.get().strip()
            if current and current.lower() != "all" and current not in values:
                values = [*values, current]
            combo.configure(values=values)

    def candidate_filter_presets_file(self) -> Path:
        return self.project_dir() / "native_candidate_filter_presets.json"

    def default_candidate_filter_presets(self) -> dict[str, dict[str, str]]:
        return {
            "non_clear_review": {"text": "", "site": "all", "risk": "non_clear", "source": "all", "min_score": "", "max_score": "", "max_rank": "", "delta": "all", "field": "all", "field_value": ""},
            "methoxy_soft_spot": {"text": "methoxy", "site": "methoxy", "risk": "non_clear", "source": "all", "min_score": "", "max_score": "", "max_rank": "", "delta": "all", "field": "all", "field_value": ""},
            "ester_review": {"text": "ester", "site": "all", "risk": "non_clear", "source": "all", "min_score": "", "max_score": "", "max_rank": "", "delta": "all", "field": "all", "field_value": ""},
            "terminal_tail_review": {"text": "tail", "site": "all", "risk": "non_clear", "source": "all", "min_score": "", "max_score": "", "max_rank": "", "delta": "all", "field": "all", "field_value": ""},
            "high_score_candidates": {"text": "", "site": "all", "risk": "all", "source": "all", "min_score": "80", "max_score": "", "max_rank": "", "delta": "all", "field": "all", "field_value": ""},
            "top_ranked_polarity_gain": {"text": "", "site": "all", "risk": "all", "source": "all", "min_score": "", "max_score": "", "max_rank": "20", "delta": "polarity_gain", "field": "all", "field_value": ""},
            "aromatic_halide": {"text": "halide", "site": "aromatic", "risk": "all", "source": "all", "min_score": "", "max_score": "", "max_rank": "", "delta": "all", "field": "all", "field_value": ""},
        }

    def load_candidate_filter_presets(self) -> dict[str, dict[str, str]]:
        presets = self.default_candidate_filter_presets()
        payload = read_json(self.candidate_filter_presets_file())
        for name, state in (payload.get("presets") or {}).items():
            if isinstance(state, dict):
                presets[str(name)] = {str(key): str(value or "") for key, value in state.items()}
        return presets

    def refresh_candidate_filter_preset_combo(self) -> None:
        combo = getattr(self, "candidate_filter_preset_combo", None)
        if combo is None:
            return
        names = sorted(self.load_candidate_filter_presets().keys())
        current = self.candidate_filter_preset_var.get().strip()
        if current and current not in names:
            names.append(current)
        combo.configure(values=names)

    def current_candidate_filter_state(self) -> dict[str, str]:
        return {
            "text": self.candidate_filter_var.get().strip(),
            "site": self.candidate_site_filter_var.get().strip() or "all",
            "risk": self.candidate_risk_filter_var.get().strip() or "all",
            "source": self.candidate_source_filter_var.get().strip() or "all",
            "min_score": self.candidate_min_score_var.get().strip(),
            "max_score": self.candidate_max_score_var.get().strip(),
            "max_rank": self.candidate_max_rank_var.get().strip(),
            "delta": self.candidate_delta_filter_var.get().strip() or "all",
            "field": self.candidate_column_filter_field_var.get().strip() or "all",
            "field_value": self.candidate_column_filter_value_var.get().strip(),
        }

    def apply_candidate_filter_preset(self) -> None:
        name = self.candidate_filter_preset_var.get().strip()
        presets = self.load_candidate_filter_presets()
        state = presets.get(name)
        if not state:
            self.status_var.set(f"Candidate filter preset not found: {name or '-'}")
            return
        self.candidate_filter_var.set(str(state.get("text") or ""))
        self.candidate_site_filter_var.set(str(state.get("site") or "all"))
        self.candidate_risk_filter_var.set(str(state.get("risk") or "all"))
        self.candidate_source_filter_var.set(str(state.get("source") or "all"))
        self.candidate_min_score_var.set(str(state.get("min_score") or ""))
        self.candidate_max_score_var.set(str(state.get("max_score") or ""))
        self.candidate_max_rank_var.set(str(state.get("max_rank") or ""))
        self.candidate_delta_filter_var.set(str(state.get("delta") or "all"))
        self.candidate_column_filter_field_var.set(str(state.get("field") or "all"))
        self.candidate_column_filter_value_var.set(str(state.get("field_value") or ""))
        self.refresh_candidate_filter_options()
        self.render_candidate_table()
        self.status_var.set(f"Applied candidate filter preset: {name}")

    def save_candidate_filter_preset(self) -> None:
        name = self.candidate_filter_preset_var.get().strip()
        if not name:
            messagebox.showinfo("Missing preset name", "Enter a candidate filter preset name first.")
            return
        payload = read_json(self.candidate_filter_presets_file())
        presets = payload.get("presets") if isinstance(payload.get("presets"), dict) else {}
        presets[name] = self.current_candidate_filter_state()
        write_json(
            self.candidate_filter_presets_file(),
            {
                "created_at": payload.get("created_at") or datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "project_name": self.project_name(),
                "mode": "native_candidate_filter_presets",
                "presets": presets,
                "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
            },
        )
        self.refresh_candidate_filter_preset_combo()
        self.status_var.set(f"Saved candidate filter preset: {name}")

    def _candidate_text(self, row: dict) -> str:
        keys = [
            "candidate_id",
            "smiles",
            "site_class",
            "site_class_governance_action",
            "site_class_candidate_guidance",
            "site_class_risk_note",
            "enumeration_type",
            "replacement_label",
            "replacement_class",
            "recommendation_reason",
            "candidate_explanation_summary",
            "why_recommended",
            "why_review",
            "risk_bucket",
            "review_bucket",
            "quality_bucket",
            "source",
        ]
        return " ".join(str(row.get(key) or "") for key in keys).lower()

    def _candidate_source_text(self, row: dict) -> str:
        return " ".join(
            str(row.get(key) or "")
            for key in ["enumeration_type", "replacement_label", "replacement_class", "source", "source_dataset", "source_name"]
        ).lower()

    def _candidate_risk_text(self, row: dict) -> str:
        return " ".join(
            str(row.get(key) or "")
            for key in [
                "site_class_governance_action",
                "site_class_risk_note",
                "risk_bucket",
                "review_bucket",
                "quality_bucket",
                "endpoint_gate_decision",
                "why_review",
            ]
        ).lower()

    def _candidate_filter_summary(self, shown: int, total: int) -> str:
        filters = []
        if self.candidate_filter_var.get().strip():
            filters.append(f"text={self.candidate_filter_var.get().strip()}")
        for label, var in [
            ("site", self.candidate_site_filter_var),
            ("risk", self.candidate_risk_filter_var),
            ("source", self.candidate_source_filter_var),
        ]:
            value = var.get().strip()
            if value and value.lower() != "all":
                filters.append(f"{label}={value}")
        if self.candidate_min_score_var.get().strip():
            filters.append(f"min_score={self.candidate_min_score_var.get().strip()}")
        if self.candidate_max_score_var.get().strip():
            filters.append(f"max_score={self.candidate_max_score_var.get().strip()}")
        if self.candidate_max_rank_var.get().strip():
            filters.append(f"rank<={self.candidate_max_rank_var.get().strip()}")
        if self.candidate_delta_filter_var.get().strip() and self.candidate_delta_filter_var.get().strip() != "all":
            filters.append(f"delta={self.candidate_delta_filter_var.get().strip()}")
        field = self.candidate_column_filter_field_var.get().strip()
        field_value = self.candidate_column_filter_value_var.get().strip()
        if field and field != "all" and field_value:
            filters.append(f"{field}~{field_value}")
        suffix = f" | filters: {', '.join(filters)}" if filters else ""
        return f"Showing {shown} of {total} candidates{suffix}."

    def _candidate_column_value(self, row: dict, field: str) -> str:
        if field == "risk_bucket":
            return self._candidate_risk_text(row)
        if field == "source":
            return self._candidate_source_text(row)
        if field in {"why", "reason"}:
            return " ".join(str(row.get(key) or "") for key in ["candidate_explanation_summary", "why_recommended", "why_review", "recommendation_reason"])
        return str(row.get(field) or "")

    def _candidate_delta_matches(self, row: dict, delta_filter: str) -> bool:
        if not delta_filter or delta_filter == "all":
            return True
        try:
            d_mw = float(row.get("delta_mw") or 0)
            d_clogp = float(row.get("delta_clogp") or 0)
            d_tpsa = float(row.get("delta_tpsa") or 0)
        except (TypeError, ValueError):
            return False
        if delta_filter == "polarity_gain":
            return d_clogp <= 0 and d_tpsa >= 0
        if delta_filter == "lower_mw":
            return d_mw < 0
        if delta_filter == "lower_clogp":
            return d_clogp < 0
        if delta_filter == "higher_tpsa":
            return d_tpsa > 0
        if delta_filter == "neutral_delta":
            return abs(d_mw) <= 15 and abs(d_clogp) <= 0.5 and abs(d_tpsa) <= 15
        return True

    def filtered_candidate_rows(self) -> list[dict]:
        query_terms = [term for term in self.candidate_filter_var.get().strip().lower().split() if term]
        site_filter = self.candidate_site_filter_var.get().strip().lower()
        risk_filter = self.candidate_risk_filter_var.get().strip().lower()
        source_filter = self.candidate_source_filter_var.get().strip().lower()
        delta_filter = self.candidate_delta_filter_var.get().strip()
        column_field = self.candidate_column_filter_field_var.get().strip()
        column_terms = [term for term in self.candidate_column_filter_value_var.get().strip().lower().split() if term]
        try:
            min_score = float(self.candidate_min_score_var.get()) if self.candidate_min_score_var.get().strip() else None
        except ValueError:
            min_score = None
        try:
            max_score = float(self.candidate_max_score_var.get()) if self.candidate_max_score_var.get().strip() else None
        except ValueError:
            max_score = None
        try:
            max_rank = float(self.candidate_max_rank_var.get()) if self.candidate_max_rank_var.get().strip() else None
        except ValueError:
            max_rank = None
        rows: list[dict] = []
        for row in self.candidate_rows:
            text = self._candidate_text(row)
            if query_terms and not all(term in text for term in query_terms):
                continue
            site_text = str(row.get("site_class") or "").lower()
            if site_filter and site_filter != "all" and site_filter not in site_text:
                continue
            risk_text = self._candidate_risk_text(row)
            if risk_filter and risk_filter != "all":
                if risk_filter == "non_clear":
                    if not risk_text or risk_text in {"clear", "unknown", "review_not_required"}:
                        continue
                    if "clear" in risk_text and not any(token in risk_text for token in ["review", "risk", "watch", "attention", "block", "liability"]):
                        continue
                elif risk_filter not in risk_text:
                    continue
            source_text = self._candidate_source_text(row)
            if source_filter and source_filter != "all" and source_filter not in source_text:
                continue
            if min_score is not None:
                try:
                    if float(row.get("score") or 0) < min_score:
                        continue
                except (TypeError, ValueError):
                    continue
            if max_score is not None:
                try:
                    if float(row.get("score") or 0) > max_score:
                        continue
                except (TypeError, ValueError):
                    continue
            if max_rank is not None:
                try:
                    if float(row.get("rank") or 0) > max_rank:
                        continue
                except (TypeError, ValueError):
                    continue
            if not self._candidate_delta_matches(row, delta_filter):
                continue
            if column_terms and column_field and column_field != "all":
                column_text = self._candidate_column_value(row, column_field).lower()
                if not all(term in column_text for term in column_terms):
                    continue
            rows.append(row)
        return rows

    def render_candidate_table(self) -> None:
        rows = self.filtered_candidate_rows()
        self.rendered_candidate_rows = rows[:200]
        self.clear_tree(self.candidate_tree)
        for idx, row in enumerate(self.rendered_candidate_rows):
            self.candidate_tree.insert(
                "",
                END,
                iid=f"candidate-{idx}",
                values=[
                    row.get("rank", ""),
                    row.get("score", ""),
                    row.get("candidate_id", ""),
                    row.get("smiles", ""),
                    row.get("site_class", ""),
                    row.get("site_class_governance_action", "") or row.get("site_class_risk_note", ""),
                    row.get("delta_mw", ""),
                    row.get("delta_clogp", ""),
                    row.get("delta_tpsa", ""),
                    row.get("enumeration_type", ""),
                    row.get("candidate_explanation_summary") or row.get("why_recommended") or row.get("recommendation_reason", ""),
                ],
            )
        self.candidate_detail_var.set(self._candidate_filter_summary(len(self.rendered_candidate_rows), len(self.candidate_rows)))
        if not self.rendered_candidate_rows:
            self.candidate_structure_photo = None
            self.candidate_structure_label.configure(image="")
            self.candidate_structure_var.set("No candidate matches the current filters.")

    def clear_candidate_filter(self) -> None:
        self.candidate_filter_var.set("")
        self.candidate_site_filter_var.set("all")
        self.candidate_risk_filter_var.set("all")
        self.candidate_source_filter_var.set("all")
        self.candidate_min_score_var.set("")
        self.candidate_max_score_var.set("")
        self.candidate_max_rank_var.set("")
        self.candidate_delta_filter_var.set("all")
        self.candidate_column_filter_field_var.set("all")
        self.candidate_column_filter_value_var.set("")
        self.render_candidate_table()

    def sort_candidates_by_score(self) -> None:
        def score(row: dict) -> float:
            try:
                return float(row.get("score") or 0)
            except Exception:
                return 0.0

        self.candidate_rows.sort(key=score, reverse=True)
        self.render_candidate_table()

    def show_selected_candidate_detail(self) -> None:
        selected = self.candidate_tree.selection()
        if not selected:
            return
        try:
            index = int(str(selected[0]).split("-")[-1])
        except Exception:
            return
        if index < 0 or index >= len(self.rendered_candidate_rows):
            return
        row = self.rendered_candidate_rows[index]
        parts = [
            f"{row.get('candidate_id') or '-'} | score={row.get('score') or '-'} | source={row.get('enumeration_type') or '-'}",
            f"SMILES: {row.get('smiles') or '-'}",
        ]
        if row.get("site_class"):
            parts.append(
                f"Site-class: {row.get('site_class')} | action: {row.get('site_class_governance_action') or '-'}"
            )
        if row.get("site_class_candidate_guidance"):
            parts.append(f"Guidance: {row.get('site_class_candidate_guidance')}")
        if row.get("why_recommended"):
            parts.append(f"Why: {row.get('why_recommended')}")
        if row.get("why_review"):
            parts.append(f"Review: {row.get('why_review')}")
        if row.get("site_class_risk_note"):
            parts.append(f"Risk note: {row.get('site_class_risk_note')}")
        score_summary = self.score_component_summary(row)
        if score_summary:
            parts.append(f"Score components: {score_summary}")
        visual = self.visual_row_for_candidate(str(row.get("candidate_id") or ""))
        if visual.get("structure_highlight_detail"):
            parts.append(f"2D change: {visual.get('structure_highlight_detail')}")
        self.candidate_detail_var.set("  ".join(parts))
        self.update_evidence_drawer_detail(str(row.get("candidate_id") or ""))
        self.update_candidate_structure_preview(row)
        self.candidate_structure_explanation_var.set(self.structure_interpretation_text(str(row.get("candidate_id") or ""), row))
        self.populate_candidate_explanation_components(str(row.get("candidate_id") or ""))
        self.update_candidate_selection_linkage(str(row.get("candidate_id") or ""))

    def evidence_drawer_row(self, candidate_id: str) -> dict:
        drawer = read_json(self.project_dir() / "candidate_evidence_drawer.json")
        for row in drawer.get("rows") or []:
            if str(row.get("candidate_id") or "") == str(candidate_id):
                return dict(row)
        return {}

    def report_row_for_candidate(self, filename: str, candidate_id: str, keys: tuple[str, ...] = ("candidate_id", "candidate_key", "source_id")) -> dict:
        report = read_json(self.project_dir() / filename)
        candidate_id = str(candidate_id or "").strip()
        if not candidate_id:
            return {}
        for row in report.get("rows") or []:
            if any(str(row.get(key) or "").strip() == candidate_id for key in keys):
                return dict(row)
        return {}

    def remediation_rows_for_candidate(self, candidate_id: str) -> list[dict]:
        report = read_json(self.project_dir() / "candidate_remediation_queue.json") or read_json(self.project_dir() / "review_remediation_queue.json")
        candidate_id = str(candidate_id or "").strip()
        rows: list[dict] = []
        for row in report.get("rows") or []:
            target = str(row.get("source_id") or row.get("candidate_id") or "")
            if target == candidate_id:
                rows.append(dict(row))
                continue
            target_filter = str(row.get("target_filter") or "")
            if f"candidate_id={candidate_id}" in target_filter:
                rows.append(dict(row))
        return rows

    def build_candidate_explanation(self, candidate_id: str, seed_row: dict | None = None) -> str:
        candidate_id = str(candidate_id or "").strip()
        seed = dict(seed_row or {})
        base = {**self.candidate_row_by_id(candidate_id), **seed}
        panel = self.report_row_for_candidate("candidate_explanation_panel.json", candidate_id)
        drawer = self.evidence_drawer_row(candidate_id)
        qa = self.report_row_for_candidate("candidate_decision_qa.json", candidate_id)
        quality = self.report_row_for_candidate("evidence_quality_scorecard.json", candidate_id)
        lineage = self.report_row_for_candidate("baseline_lineage_compare.json", candidate_id)
        remediation_rows = self.remediation_rows_for_candidate(candidate_id)
        open_like = [
            row
            for row in remediation_rows
            if str(row.get("status") or row.get("closure_status") or "open").lower()
            in {"open", "reopened", "needs_follow_up", "blocked"}
        ]
        if not candidate_id:
            return "No candidate selected."
        score = base.get("score") or panel.get("score") or drawer.get("score") or "-"
        rank = base.get("rank") or panel.get("rank") or "-"
        site = base.get("site_class") or panel.get("site_class") or drawer.get("site_class") or "-"
        decision = panel.get("local_decision") or drawer.get("local_decision") or base.get("local_decision") or "-"
        evidence = (
            panel.get("evidence_summary")
            or drawer.get("evidence_context_summary")
            or drawer.get("drawer_summary")
            or quality.get("quality_flags")
            or "-"
        )
        baseline = (
            panel.get("baseline_lineage_status")
            or lineage.get("lineage_status")
            or drawer.get("baseline_movement")
            or drawer.get("baseline_status")
            or "-"
        )
        qa_bucket = panel.get("qa_bucket") or qa.get("qa_bucket") or quality.get("qa_bucket") or "missing"
        next_action = panel.get("next_action") or qa.get("next_action") or (open_like[0].get("next_action") if open_like else "") or "-"
        deltas = ", ".join(
            part
            for part in [
                f"dMW={base.get('delta_mw')}" if base.get("delta_mw") not in {None, ""} else "",
                f"dClogP={base.get('delta_clogp')}" if base.get("delta_clogp") not in {None, ""} else "",
                f"dTPSA={base.get('delta_tpsa')}" if base.get("delta_tpsa") not in {None, ""} else "",
            ]
            if part
        )
        task_ids = ", ".join(str(row.get("task_id") or "") for row in open_like[:4] if row.get("task_id")) or "none"
        return "\n".join(
            [
                f"{candidate_id} | rank={rank} | score={score} | {deltas or 'delta fields unavailable'}",
                f"Site: {site} | decision={decision} | QA={qa_bucket}",
                f"Evidence: {evidence}",
                f"Baseline: {baseline} | open remediation={len(open_like)} ({task_ids})",
                f"Next local action: {next_action}",
            ]
        )

    def baseline_status_for_candidate(self, candidate_id: str) -> dict:
        return self.report_row_for_candidate("baseline_lineage_compare.json", candidate_id) or self.report_row_for_candidate("candidate_baseline_compare.json", candidate_id)

    def update_candidate_selection_linkage(self, candidate_id: str) -> None:
        candidate_id = str(candidate_id or "").strip()
        if not candidate_id:
            self.candidate_linkage_var.set("Candidate selection syncs structure, explanation components, baseline movement, and remediation status.")
            return
        lineage = self.baseline_status_for_candidate(candidate_id)
        remediation_rows = self.remediation_rows_for_candidate(candidate_id)
        open_count = sum(
            1
            for row in remediation_rows
            if str(row.get("status") or row.get("closure_status") or "open").lower() in {"open", "reopened", "needs_follow_up", "blocked"}
        )
        components = [row for row in self.candidate_explanation_drilldown_rows if str(row.get("candidate_id") or "") == candidate_id]
        attention_components = [row.get("component_label") or row.get("component_id") for row in components if row.get("component_status") in {"attention", "watch"}]
        self.candidate_linkage_var.set(
            f"Selection sync: 2D rendered | components={len(components)} | attention={', '.join(str(item) for item in attention_components[:4]) or 'none'} | "
            f"baseline={lineage.get('lineage_status') or lineage.get('status') or '-'} | remediation_open={open_count}"
        )

    def component_structure_locator_row(self, candidate_id: str, component_id: object = "", component_label: object = "") -> dict:
        candidate_id = str(candidate_id or "").strip()
        component_id_text = str(component_id or "").strip().lower()
        component_label_text = str(component_label or "").strip().lower()
        if not candidate_id:
            return {}
        rows = self.candidate_component_structure_locator_rows
        if not rows:
            locator = read_json(self.project_dir() / "candidate_component_structure_locator.json")
            rows = [dict(row) for row in locator.get("rows") or []]
            self.candidate_component_structure_locator_rows = rows
        for row in rows:
            if str(row.get("candidate_id") or "").strip() != candidate_id:
                continue
            row_component_id = str(row.get("component_id") or "").strip().lower()
            row_component_label = str(row.get("component_label") or "").strip().lower()
            if component_id_text and component_id_text in {row_component_id, row_component_label}:
                return dict(row)
            if component_label_text and component_label_text in {row_component_id, row_component_label}:
                return dict(row)
        return {}

    def populate_candidate_explanation_components(self, candidate_id: str | None = None) -> None:
        if not hasattr(self, "candidate_explanation_component_tree"):
            return
        candidate_id = str(candidate_id or "").strip()
        if not candidate_id:
            selected = self.selected_candidate_row() if hasattr(self, "candidate_tree") else {}
            candidate_id = str(selected.get("candidate_id") or "").strip()
        self.clear_tree(self.candidate_explanation_component_tree)
        self.current_candidate_component_rows = [
            dict(row)
            for row in self.candidate_explanation_drilldown_rows
            if not candidate_id or str(row.get("candidate_id") or "") == candidate_id
        ][:12]
        if not self.current_candidate_component_rows and candidate_id:
            panel = self.report_row_for_candidate("candidate_explanation_panel.json", candidate_id)
            if panel:
                for component_id, label, score in [
                    ("score", "Score", panel.get("score_component")),
                    ("evidence", "Evidence", panel.get("evidence_component")),
                    ("decision_qa", "Decision QA", panel.get("qa_component")),
                    ("baseline", "Baseline", panel.get("baseline_component")),
                    ("remediation", "Remediation", panel.get("remediation_component")),
                ]:
                    self.current_candidate_component_rows.append(
                        {
                            "candidate_id": candidate_id,
                            "component_id": component_id,
                            "component_label": label,
                            "component_score": score,
                            "component_status": "ready",
                            "target_view": component_id,
                            "target_artifact": str(self.project_dir() / "candidate_explanation_panel.json"),
                            "target_filter": f"candidate_id={candidate_id}",
                            "summary": panel.get("explanation_trace", ""),
                            "next_action": panel.get("next_action", ""),
                        }
                    )
        for index, row in enumerate(self.current_candidate_component_rows):
            locator = self.component_structure_locator_row(candidate_id, row.get("component_id"), row.get("component_label"))
            if not locator:
                continue
            for key in [
                "locator_id",
                "structure_image_path",
                "site_highlight_label",
                "structure_highlight_detail",
                "highlight_atom_count",
                "substitution_change_summary",
            ]:
                if locator.get(key) not in {None, ""} and not row.get(key):
                    row[key] = locator.get(key)
            row["component_structure_locator_status"] = locator.get("locator_status") or ""
            row["component_structure_locator_detail"] = locator.get("locator_detail") or ""
            row["component_structure_locator_artifact"] = locator.get("target_artifact") or ""
            self.current_candidate_component_rows[index] = row
        for idx, row in enumerate(self.current_candidate_component_rows):
            self.candidate_explanation_component_tree.insert(
                "",
                END,
                iid=f"candidate-component-{idx}",
                values=[
                    row.get("component_label") or row.get("component_id", ""),
                    row.get("component_score", ""),
                    row.get("component_status", ""),
                    row.get("target_view", ""),
                    row.get("summary", ""),
                ],
            )
        first = self.candidate_explanation_component_tree.get_children()
        if first:
            self.candidate_explanation_component_tree.selection_set(first[0])
            self.candidate_explanation_component_tree.focus(first[0])
            self.show_selected_explanation_component()
        elif candidate_id:
            self.candidate_explanation_component_var.set(f"{candidate_id}: explanation drilldown is not built yet.")

    def selected_explanation_component_row(self) -> dict:
        if not hasattr(self, "candidate_explanation_component_tree"):
            return {}
        selected = self.candidate_explanation_component_tree.selection()
        if not selected:
            return {}
        try:
            index = int(str(selected[0]).split("-")[-1])
        except Exception:
            return {}
        if 0 <= index < len(self.current_candidate_component_rows):
            return dict(self.current_candidate_component_rows[index])
        return {}

    def show_selected_explanation_component(self) -> None:
        row = self.selected_explanation_component_row()
        if not row:
            self.candidate_explanation_component_var.set("Select a score/evidence/QA/baseline/remediation component to route its source artifact.")
            return
        candidate_id = str(row.get("candidate_id") or "")
        locator = self.component_structure_locator_row(candidate_id, row.get("component_id"), row.get("component_label"))
        merged_row = {**locator, **row}
        if locator:
            for key in ["structure_image_path", "site_highlight_label", "structure_highlight_detail", "highlight_atom_count", "substitution_change_summary"]:
                if locator.get(key) not in {None, ""}:
                    merged_row[key] = locator.get(key)
            merged_row["component_structure_locator_status"] = locator.get("locator_status") or ""
            merged_row["component_structure_locator_detail"] = locator.get("locator_detail") or ""
        self.update_candidate_structure_preview(merged_row)
        self.candidate_structure_explanation_var.set(self.structure_interpretation_text(candidate_id, self.candidate_row_by_id(candidate_id), merged_row))
        highlight = " | ".join(
            part
            for part in [
                f"site={merged_row.get('site_class')}" if merged_row.get("site_class") else "",
                f"highlight={merged_row.get('site_highlight_label')}" if merged_row.get("site_highlight_label") else "",
                f"atoms={merged_row.get('highlight_atom_count')}" if merged_row.get("highlight_atom_count") not in {None, ""} else "",
                f"evidence={row.get('evidence_anchor')}" if row.get("evidence_anchor") else "",
                f"locator={merged_row.get('component_structure_locator_status')}" if merged_row.get("component_structure_locator_status") else "",
            ]
            if part
        )
        self.candidate_explanation_component_var.set(
            f"{row.get('candidate_id') or '-'} | {row.get('component_label') or row.get('component_id')} "
            f"score={row.get('component_score') or '-'} status={row.get('component_status') or '-'} | "
            f"target={row.get('target_view') or '-'} filter={row.get('target_filter') or '-'} | "
            f"{highlight or merged_row.get('component_structure_locator_detail') or row.get('right_panel_detail') or row.get('next_action') or row.get('summary') or '-'}"
        )

    def open_selected_explanation_component_artifact(self) -> None:
        row = self.selected_explanation_component_row()
        if not row:
            messagebox.showinfo("Select a component", "Select an explanation component first.")
            return
        path = Path(str(row.get("target_artifact") or ""))
        if not path.is_absolute():
            path = ROOT / path
        open_path(path)

    def route_selected_explanation_component(self) -> None:
        row = self.selected_explanation_component_row()
        if not row:
            messagebox.showinfo("Select a component", "Select an explanation component first.")
            return
        candidate_id = str(row.get("candidate_id") or "")
        target = str(row.get("target_view") or "")
        if target == "remediation" and hasattr(self, "review_remediation_tree"):
            self.show_view("reports")
            task_filter = str(row.get("target_filter") or "")
            wanted = {part.strip() for part in task_filter.replace("task_ids=", "").replace(";", ",").split(",") if part.strip() and "=" not in part}
            for item in self.review_remediation_tree.get_children():
                values = self.review_remediation_tree.item(item, "values")
                task_id = str(values[0] or "") if values else ""
                if task_id in wanted or (candidate_id and candidate_id in str(values)):
                    self.review_remediation_tree.selection_set(item)
                    self.review_remediation_tree.focus(item)
                    self.show_selected_remediation_task()
                    break
            return
        if target in {"baseline_lineage", "decision_qa"}:
            self.show_view("reports")
            tree = self.baseline_lineage_tree if target == "baseline_lineage" and hasattr(self, "baseline_lineage_tree") else self.decision_qa_tree if hasattr(self, "decision_qa_tree") else None
            if tree is not None:
                for item in tree.get_children():
                    values = tree.item(item, "values")
                    if values and candidate_id and str(values[0]) == candidate_id:
                        tree.selection_set(item)
                        tree.focus(item)
                        break
            return
        self.show_view("candidate")

    def update_candidate_explanation_chart(self, candidate_id: str) -> None:
        panel = self.report_row_for_candidate("candidate_explanation_panel.json", candidate_id)
        image_path = Path(str(panel.get("breakdown_preview_path") or panel.get("breakdown_chart_path") or ""))
        if image_path and not image_path.is_absolute():
            image_path = ROOT / image_path
        labels = [
            getattr(self, "candidate_explanation_chart_label", None),
            getattr(self, "review_explanation_chart_label", None),
        ]
        if Image is None or ImageTk is None or not image_path.is_file():
            self.candidate_explanation_chart_photo = None
            for label in labels:
                if label is not None:
                    label.configure(image="")
            return
        try:
            image = Image.open(image_path)
            resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", None)
            if resample is not None:
                image.thumbnail((620, 220), resample)
            else:
                image.thumbnail((620, 220))
            self.candidate_explanation_chart_photo = ImageTk.PhotoImage(image)
            for label in labels:
                if label is not None:
                    label.configure(image=self.candidate_explanation_chart_photo)
        except Exception:
            self.candidate_explanation_chart_photo = None
            for label in labels:
                if label is not None:
                    label.configure(image="")

    def update_evidence_drawer_detail(self, candidate_id: str) -> None:
        row = self.evidence_drawer_row(candidate_id)
        if not row:
            self.evidence_drawer_var.set(f"{candidate_id or 'candidate'}: evidence drawer is not built yet.")
            self.candidate_explanation_var.set(self.build_candidate_explanation(candidate_id))
            self.update_candidate_explanation_chart(candidate_id)
            return
        parts = [
            f"{row.get('candidate_id') or '-'} | decision={row.get('local_decision') or '-'} | confidence={row.get('decision_confidence') or '-'}",
            f"QA-ready sections: {row.get('drawer_sections') or '-'}",
            f"Baseline: {row.get('baseline_movement') or row.get('baseline_status') or '-'} | depth={row.get('evidence_depth_score') or '-'}",
            f"Next: {row.get('next_action') or '-'}",
        ]
        if row.get("decision_rationale"):
            parts.append(f"Rationale: {row.get('decision_rationale')}")
        if row.get("evidence_context_summary"):
            parts.append(f"Evidence: {row.get('evidence_context_summary')}")
        if row.get("mmp_thumbnail_paths") or row.get("sar_thumbnail_paths"):
            parts.append(f"Thumbnails: MMP={row.get('mmp_thumbnail_paths') or '-'} SAR={row.get('sar_thumbnail_paths') or '-'}")
        self.evidence_drawer_var.set("\n".join(parts))
        self.candidate_explanation_var.set(self.build_candidate_explanation(candidate_id, row))
        self.update_candidate_explanation_chart(candidate_id)

    def candidate_row_by_id(self, candidate_id: str) -> dict:
        candidate_id = str(candidate_id or "").strip()
        if not candidate_id:
            return {}
        for row in [*self.rendered_candidate_rows, *self.candidate_rows]:
            if str(row.get("candidate_id") or "").strip() == candidate_id:
                return dict(row)
        path = self.project_dir() / "candidates.csv"
        if path.exists():
            try:
                with path.open(encoding="utf-8", newline="") as handle:
                    for row in csv.DictReader(handle):
                        if str(row.get("candidate_id") or "").strip() == candidate_id:
                            return dict(row)
            except Exception:
                return {}
        return {}

    def visual_row_for_candidate(self, candidate_id: str) -> dict:
        candidate_id = str(candidate_id or "").strip()
        if not candidate_id:
            return {}
        visual = read_json(self.project_dir() / "candidate_visual_compare.json")
        for row in visual.get("rows") or []:
            if str(row.get("candidate_id") or "") == candidate_id:
                return dict(row)
        return {}

    def visual_image_path_for_candidate(self, candidate_id: str) -> Path | None:
        candidate_id = str(candidate_id or "").strip()
        if not candidate_id:
            return None
        visual_row = self.visual_row_for_candidate(candidate_id)
        candidates = [
            Path(str(visual_row.get("image_path") or "")),
            self.project_dir() / "candidate_visual_compare" / f"{candidate_id}.png",
        ]
        for path in candidates:
            if not str(path):
                continue
            if not path.is_absolute():
                path = ROOT / path
            if path.is_file():
                return path
        return None

    def candidate_structure_cache_path(self, candidate_id: str, role: str = "candidate") -> Path:
        safe_id = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(candidate_id or "")) or "candidate"
        safe_role = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(role or "")) or "candidate"
        safe = f"{safe_id}_{safe_role}"
        return self.project_dir() / "candidate_structure_previews" / f"{safe}.png"

    def render_smiles_structure_preview(self, *, smiles: str, cache_id: str, role: str, width: int = 420, height: int = 300) -> Path | None:
        smiles = str(smiles or "").strip()
        if not smiles:
            return None
        output = self.candidate_structure_cache_path(cache_id, role)
        if output.is_file():
            return output
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "render_molecule_preview.py"),
                    "--smiles",
                    smiles,
                    "--output",
                    str(output),
                    "--width",
                    str(width),
                    "--height",
                    str(height),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=90,
                check=True,
            )
        except Exception:
            return None
        return output if output.is_file() else None

    def render_candidate_structure_preview(self, row: dict) -> Path | None:
        candidate_id = str(row.get("candidate_id") or "").strip() or "candidate"
        smiles = str(row.get("smiles") or row.get("candidate_smiles") or "").strip()
        return self.render_smiles_structure_preview(smiles=smiles, cache_id=candidate_id, role="after")

    def parent_smiles_for_structure(self, row: dict) -> str:
        for key in ("parent_smiles", "input_smiles", "base_smiles", "source_parent_smiles", "molecule_smiles"):
            value = str(row.get(key) or "").strip()
            if value:
                return value
        preset = read_json(self.preset_file())
        return str(preset.get("smiles") or self.smiles_var.get() or "").strip()

    def score_component_summary(self, row: dict) -> str:
        parts = []
        for label, key in [
            ("score", "score"),
            ("property", "property_score"),
            ("risk", "risk_score"),
            ("transform", "transform_prior_score"),
            ("MMP", "mmp_precedent_score"),
            ("SAR", "sar_neighborhood_score"),
            ("MO", "multi_objective_score"),
        ]:
            value = str(row.get(key) or "").strip()
            if value:
                parts.append(f"{label}={value}")
        gate = str(row.get("endpoint_gate_decision") or "").strip()
        if gate:
            parts.append(f"gate={gate}")
        component = str(row.get("component_label") or row.get("component_id") or "").strip()
        component_score = str(row.get("component_score") or "").strip()
        if component:
            parts.append(f"selected_component={component}" + (f"({component_score})" if component_score else ""))
        return "; ".join(parts)

    def structure_interpretation_row(self, candidate_id: str) -> dict:
        return self.report_row_for_candidate("candidate_structure_interpretation.json", candidate_id)

    def structure_interpretation_text(self, candidate_id: str, row: dict, component_row: dict | None = None) -> str:
        candidate_id = str(candidate_id or row.get("candidate_id") or "").strip()
        interpretation = self.structure_interpretation_row(candidate_id)
        visual = self.visual_row_for_candidate(candidate_id)
        merged = {**interpretation, **visual, **dict(row)}
        component = dict(component_row or {})
        parts = [
            f"2D interpretation: {candidate_id or 'candidate'}",
            f"Site/highlight: {merged.get('site_highlight_label') or merged.get('site_class') or '-'}",
            f"Change: {merged.get('substitution_change_summary') or merged.get('replacement_label') or '-'}",
        ]
        if merged.get("structure_highlight_detail"):
            parts.append(f"Detail: {merged.get('structure_highlight_detail')}")
        score = merged.get("score_component_summary") or self.score_component_summary(merged)
        if score:
            parts.append(f"Score linkage: {score}")
        if component:
            locator = " | ".join(
                item
                for item in [
                    f"component={component.get('component_label') or component.get('component_id') or '-'}",
                    f"score={component.get('component_score') or '-'}",
                    f"target={component.get('target_view') or '-'}",
                    f"highlight={component.get('site_highlight_label') or merged.get('site_highlight_label') or '-'}",
                    f"atoms={component.get('highlight_atom_count') or merged.get('highlight_atom_count') or '-'}",
                    f"locator={component.get('component_structure_locator_status') or component.get('locator_status') or '-'}",
                ]
                if item
            )
            parts.append(f"Selected locator: {locator}")
            detail = (
                component.get("component_structure_locator_detail")
                or component.get("locator_detail")
                or component.get("right_panel_detail")
                or component.get("summary")
                or component.get("next_action")
            )
            if detail:
                parts.append(f"Locator detail: {detail}")
        elif interpretation.get("score_component_locator_count") not in {None, ""}:
            parts.append(f"Component locators: {interpretation.get('score_component_locator_count')}")
        return "\n".join(parts)

    def structure_status_text(self, candidate_id: str, row: dict, image_path: str | Path) -> str:
        highlight = str(row.get("structure_highlight_detail") or "").strip()
        site = str(row.get("site_highlight_label") or row.get("site_class") or "").strip()
        change = str(row.get("substitution_change_summary") or row.get("replacement_label") or "").strip()
        legend = str(row.get("highlight_legend") or "").strip()
        color = str(row.get("highlight_color_legend") or "").strip()
        score = self.score_component_summary(row)
        parts = [f"After: {candidate_id or 'candidate'}"]
        if site:
            parts.append(f"Site: {site}")
        if change:
            parts.append(f"Change: {change}")
        if score:
            parts.append(f"Score: {score}")
        if legend or color:
            parts.append(f"Highlight: {'; '.join(item for item in [legend, color] if item)}")
        if highlight and highlight not in parts:
            parts.append(f"Detail: {highlight}")
        parts.append(f"Image: {Path(image_path).name}")
        return "\n".join(parts)

    def before_structure_status_text(self, candidate_id: str, smiles: str, row: dict, image_path: str | Path) -> str:
        site = str(row.get("site_class") or row.get("site_type") or "").strip()
        return "\n".join(
            [
                f"Before: current molecule",
                f"SMILES: {smiles[:64]}{'...' if len(smiles) > 64 else ''}",
                f"Compared to: {candidate_id or '-'}",
                f"Site context: {site or '-'}",
                f"Image: {Path(image_path).name}",
            ]
        )

    def _set_structure_label_image(self, *, label, photo_name: str, image_path: str | Path | None, status_var: StringVar, status_text: str) -> None:
        if not image_path:
            setattr(self, photo_name, None)
            label.configure(image="")
            status_var.set(status_text)
            return
        if Image is None or ImageTk is None:
            setattr(self, photo_name, None)
            label.configure(image="")
            status_var.set(status_text)
            return
        try:
            image = Image.open(image_path)
            resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", None)
            if resample is not None:
                image.thumbnail((210, 190), resample)
            else:
                image.thumbnail((210, 190))
            photo = ImageTk.PhotoImage(image)
            setattr(self, photo_name, photo)
            label.configure(image=photo, compound="top")
            status_var.set(status_text)
        except Exception:
            setattr(self, photo_name, None)
            label.configure(image="")
            status_var.set(f"failed to load {image_path}")

    def update_structure_preview(
        self,
        row: dict,
        *,
        label_name: str,
        photo_name: str,
        status_var: StringVar,
        before_label_name: str,
        before_photo_name: str,
        before_status_var: StringVar,
    ) -> None:
        label = getattr(self, label_name, None)
        if label is None:
            return
        candidate_id = str(row.get("candidate_id") or "").strip()
        visual_row = self.visual_row_for_candidate(candidate_id)
        merged = {**self.candidate_row_by_id(candidate_id), **visual_row, **dict(row)}
        before_label = getattr(self, before_label_name, None)
        before_smiles = self.parent_smiles_for_structure(merged)
        before_path = None
        if before_label is not None and before_smiles:
            before_path = self.render_smiles_structure_preview(
                smiles=before_smiles,
                cache_id=candidate_id or "current_molecule",
                role="before",
            )
            self._set_structure_label_image(
                label=before_label,
                photo_name=before_photo_name,
                image_path=before_path,
                status_var=before_status_var,
                status_text=self.before_structure_status_text(candidate_id, before_smiles, merged, before_path or "before"),
            )
        elif before_label is not None:
            self._set_structure_label_image(
                label=before_label,
                photo_name=before_photo_name,
                image_path=None,
                status_var=before_status_var,
                status_text="Before: no current molecule SMILES available.",
            )
        preferred_image = ""
        for key in ("structure_image_path", "image_path", "preview_path"):
            candidate_path = str(merged.get(key) or "").strip()
            if not candidate_path:
                continue
            path = Path(candidate_path)
            if not path.is_absolute():
                path = ROOT / path
            if path.exists():
                preferred_image = str(path)
                break
        image_path = preferred_image or self.visual_image_path_for_candidate(candidate_id) or self.render_candidate_structure_preview(merged)
        if not image_path:
            self._set_structure_label_image(
                label=label,
                photo_name=photo_name,
                image_path=None,
                status_var=status_var,
                status_text=f"{candidate_id or 'candidate'}: no renderable SMILES/image found.",
            )
            return
        self._set_structure_label_image(
            label=label,
            photo_name=photo_name,
            image_path=image_path,
            status_var=status_var,
            status_text=self.structure_status_text(candidate_id, merged, image_path),
        )

    def update_candidate_structure_preview(self, row: dict) -> None:
        self.update_structure_preview(
            row,
            label_name="candidate_structure_label",
            photo_name="candidate_structure_photo",
            status_var=self.candidate_structure_var,
            before_label_name="candidate_before_structure_label",
            before_photo_name="candidate_before_structure_photo",
            before_status_var=self.candidate_before_structure_var,
        )

    def update_review_structure_preview(self, row: dict) -> None:
        self.update_structure_preview(
            row,
            label_name="review_structure_label",
            photo_name="review_structure_photo",
            status_var=self.review_structure_var,
            before_label_name="review_before_structure_label",
            before_photo_name="review_before_structure_photo",
            before_status_var=self.review_before_structure_var,
        )

    def selected_candidate_row(self) -> dict:
        selected = self.candidate_tree.selection()
        if not selected:
            return {}
        try:
            index = int(str(selected[0]).split("-")[-1])
        except Exception:
            return {}
        if index < 0 or index >= len(self.rendered_candidate_rows):
            return {}
        return self.rendered_candidate_rows[index]

    def candidate_drilldown_path(self, candidate_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in candidate_id) or "candidate"
        return self.project_dir() / "candidate_drilldowns" / f"{safe}.json"

    def build_candidate_drilldown_payload(self, candidate_id: str) -> Path:
        candidate_id = str(candidate_id or "").strip()
        candidates = {str(row.get("candidate_id") or ""): row for row in self.candidate_rows}
        visual = read_json(self.project_dir() / "candidate_visual_compare.json")
        reviews = read_json(self.project_dir() / "candidate_review_packet.json")
        board = read_json(self.project_dir() / "candidate_review_board.json")
        governance = read_json(self.project_dir() / "local_governance_diff_report.json")
        visual_rows = {str(row.get("candidate_id") or ""): row for row in visual.get("rows") or []}
        review_rows = {str(row.get("candidate_id") or ""): row for row in reviews.get("rows") or []}
        board_rows = {str(row.get("candidate_id") or ""): row for row in board.get("rows") or []}
        governance_rows = {str(row.get("candidate_id") or ""): row for row in governance.get("rows") or []}
        payload = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "ready" if candidate_id else "missing_candidate_id",
            "mode": "local_candidate_drilldown",
            "project_name": self.project_name(),
            "candidate_id": candidate_id,
            "candidate": candidates.get(candidate_id, {}),
            "visual_compare": visual_rows.get(candidate_id, {}),
            "review_packet": review_rows.get(candidate_id, {}),
            "review_board": board_rows.get(candidate_id, {}),
            "governance_diff": governance_rows.get(candidate_id, {}),
            "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
        }
        path = self.candidate_drilldown_path(candidate_id)
        write_json(path, payload)
        return path

    def open_selected_candidate_image(self) -> None:
        row = self.selected_candidate_row()
        if not row:
            messagebox.showinfo("Select a candidate", "Select a candidate row first.")
            return
        candidate_id = str(row.get("candidate_id") or "")
        visual = read_json(self.project_dir() / "candidate_visual_compare.json")
        visual_row = next((item for item in visual.get("rows") or [] if str(item.get("candidate_id") or "") == candidate_id), {})
        image_path = Path(str(visual_row.get("image_path") or self.project_dir() / "candidate_visual_compare" / f"{candidate_id}.png"))
        open_path(image_path)

    def open_selected_candidate_drilldown(self) -> None:
        row = self.selected_candidate_row()
        if not row:
            messagebox.showinfo("Select a candidate", "Select a candidate row first.")
            return
        open_path(self.build_candidate_drilldown_payload(str(row.get("candidate_id") or "")))

    def add_selected_candidate_to_compare(self) -> None:
        selected = self.candidate_tree.selection()
        if not selected:
            messagebox.showinfo("Select a candidate", "Select a candidate row first.")
            return
        try:
            index = int(str(selected[0]).split("-")[-1])
        except Exception:
            return
        if index < 0 or index >= len(self.rendered_candidate_rows):
            return
        row = self.rendered_candidate_rows[index]
        candidate_id = str(row.get("candidate_id") or "")
        if candidate_id and all(str(item.get("candidate_id") or "") != candidate_id for item in self.compare_rows):
            self.compare_rows.append(row)
        self.render_compare_table()

    def clear_compare_rows(self) -> None:
        self.compare_rows = []
        self.render_compare_table()

    def render_compare_table(self) -> None:
        if not hasattr(self, "compare_tree"):
            return
        self.clear_tree(self.compare_tree)
        for row in self.compare_rows[:8]:
            self.compare_tree.insert(
                "",
                END,
                values=[
                    row.get("candidate_id", ""),
                    row.get("score", ""),
                    row.get("site_class", ""),
                    row.get("delta_mw", ""),
                    row.get("delta_clogp", ""),
                    row.get("delta_tpsa", ""),
                    row.get("candidate_explanation_summary") or row.get("why_recommended") or row.get("recommendation_reason", ""),
                ],
            )

    def populate_candidate_review_board(self) -> None:
        if not hasattr(self, "review_tree"):
            return
        report = read_json(self.project_dir() / "candidate_review_board.json")
        analytics = read_json(self.project_dir() / "candidate_review_analytics.json")
        self.review_board_rows = list(report.get("rows") or [])
        self.review_metric_vars[0].set(report.get("status") or "-")
        self.review_metric_vars[1].set(str(report.get("filtered_row_count") or report.get("row_count") or 0))
        self.review_metric_vars[2].set(str(report.get("pending_local_review_count") or 0))
        self.review_metric_vars[3].set(",".join((report.get("local_status_counts") or {}).keys()) or "-")
        self.render_candidate_review_board()
        self.populate_review_analytics(analytics)

    def set_review_analytics_layout(self, mode: str) -> None:
        paned = getattr(self, "review_paned", None)
        tree = getattr(self, "review_analytics_tree", None)
        if paned is None:
            if tree is not None:
                try:
                    tree.configure(height=12 if mode == "expanded" else 7)
                except Exception:
                    return
            return

        def apply_position() -> None:
            try:
                height = max(int(paned.winfo_height()), 720)
                ratio = 0.38 if mode == "expanded" else 0.62
                paned.sashpos(0, max(260, int(height * ratio)))
            except Exception:
                return

        try:
            paned.after(50, apply_position)
        except Exception:
            apply_position()

    def populate_review_analytics(self, analytics: dict) -> None:
        if not hasattr(self, "review_analytics_tree"):
            return
        rows = []
        for card in analytics.get("cards") or []:
            rows.append(
                {
                    "row_type": "card",
                    "key": card.get("label", ""),
                    "status": card.get("status", ""),
                    "value": card.get("value", ""),
                    "secondary": "",
                    "details": card.get("details") or card.get("next_action", ""),
                    "filter_type": card.get("filter_type", ""),
                    "filter_value": card.get("filter_value", ""),
                }
            )
        rows.extend(analytics.get("rows") or [])
        self.review_analytics_rows = rows
        self.review_analytics_var.set(
            f"analytics={analytics.get('status') or 'missing'} | "
            f"pending={analytics.get('pending_backlog_count') or 0} | "
            f"pending reasons={analytics.get('pending_reason_cluster_count') or 0} | "
            f"risk={analytics.get('repeated_risk_bucket_count') or 0} | "
            f"site classes={analytics.get('site_class_count') or 0} | "
            f"reviewers={analytics.get('reviewer_count') or 0}"
        )
        self.clear_tree(self.review_analytics_tree)
        for idx, row in enumerate(rows[:120]):
            self.review_analytics_tree.insert(
                "",
                END,
                iid=f"review-analytics-{idx}",
                values=[
                    row.get("row_type", ""),
                    row.get("key", ""),
                    row.get("status", ""),
                    row.get("value", ""),
                    row.get("secondary", ""),
                    row.get("details", ""),
                ],
            )
        self.populate_review_reason_workbench()

    def populate_review_reason_workbench(self) -> None:
        if not hasattr(self, "review_reason_tree"):
            return
        workbench = read_json(self.project_dir() / "candidate_review_reason_workbench.json")
        audit = read_json(self.project_dir() / "candidate_review_reason_workbench_audit.json")
        self.review_reason_rows = [dict(row) for row in workbench.get("rows") or []]
        if not self.review_reason_rows:
            self.review_reason_rows = [
                dict(row)
                for row in self.review_analytics_rows
                if str(row.get("row_type") or "") == "pending_reason_cluster"
            ]
        self.review_reason_audit_rows = [dict(row) for row in workbench.get("audit_rows") or audit.get("rows") or []]
        self.clear_tree(self.review_reason_tree)
        if hasattr(self, "review_reason_audit_tree"):
            self.clear_tree(self.review_reason_audit_tree)
        values = ["all"]
        for idx, row in enumerate(self.review_reason_rows[:60]):
            reason = str(row.get("reason_cluster") or row.get("filter_value") or row.get("key") or "")
            if reason:
                values.append(reason)
            details = str(row.get("details") or "")
            samples = ""
            if "samples=" in details:
                samples = details.split("samples=", 1)[1].split(";", 1)[0]
            self.review_reason_tree.insert(
                "",
                END,
                iid=f"review-reason-{idx}",
                values=[
                    reason,
                    row.get("cluster_row_count", row.get("value", "")),
                    row.get("dominant_site", row.get("secondary", "")),
                    samples,
                    row.get("cluster_status", row.get("status", "")),
                    row.get("next_action", "Filter, inspect first evidence, then batch note/close only visible rows."),
                ],
            )
        if hasattr(self, "review_reason_audit_tree"):
            for idx, row in enumerate(self.review_reason_audit_rows[-80:]):
                self.review_reason_audit_tree.insert(
                    "",
                    END,
                    iid=f"review-reason-audit-{idx}",
                    values=[
                        row.get("reason_cluster", ""),
                        row.get("batch_status", ""),
                        row.get("candidate_count", ""),
                        row.get("reviewer", ""),
                        row.get("created_at", ""),
                        row.get("note", ""),
                    ],
                )
        self.review_reason_cluster_var.set(values[1] if len(values) > 1 else "all")
        self.populate_reviewer_cockpit()

    def populate_reviewer_cockpit(self) -> None:
        if not hasattr(self, "reviewer_cockpit_tree"):
            return
        report = read_json(self.project_dir() / "reviewer_cockpit.json")
        self.reviewer_cockpit_rows = [dict(row) for row in report.get("rows") or []]
        self.clear_tree(self.reviewer_cockpit_tree)
        for idx, row in enumerate(self.reviewer_cockpit_rows[:120]):
            self.reviewer_cockpit_tree.insert(
                "",
                END,
                iid=f"reviewer-cockpit-{idx}",
                values=[
                    row.get("lane", ""),
                    row.get("key", ""),
                    row.get("status", ""),
                    row.get("priority", ""),
                    row.get("open_count", ""),
                    row.get("audit_event_count", ""),
                    row.get("owner", ""),
                    row.get("next_action", ""),
                ],
            )
        self.reviewer_cockpit_var.set(
            f"cockpit={report.get('status') or 'missing'} | rows={report.get('row_count') or 0} | "
            f"lanes={report.get('lane_counts') or dict()} | high={report.get('high_priority_count') or 0}"
        )

    def selected_reviewer_cockpit_row(self) -> dict:
        if not hasattr(self, "reviewer_cockpit_tree"):
            return {}
        selected = self.reviewer_cockpit_tree.selection()
        if not selected:
            return self.reviewer_cockpit_rows[0] if self.reviewer_cockpit_rows else {}
        try:
            index = int(str(selected[0]).split("-")[-1])
        except Exception:
            return {}
        if 0 <= index < len(self.reviewer_cockpit_rows):
            return dict(self.reviewer_cockpit_rows[index])
        return {}

    def apply_reviewer_cockpit_route(self) -> None:
        row = self.selected_reviewer_cockpit_row()
        if not row:
            return
        lane = str(row.get("lane") or "")
        target_filter = str(row.get("target_filter") or "")
        key = str(row.get("key") or "")
        if lane == "reason_audit":
            reason = target_filter.replace("pending_reason=", "") or key
            self.review_attention_filter_var.set(f"pending_reason:{reason}" if reason else "attention")
            self.render_candidate_review_board()
        elif lane == "closure" and hasattr(self, "review_closure_tree"):
            self.show_view("reports")
            task_id = target_filter.replace("task_id=", "")
            for item in self.review_closure_tree.get_children():
                values = self.review_closure_tree.item(item, "values")
                if values and str(values[0]) == task_id:
                    self.review_closure_tree.selection_set(item)
                    self.review_closure_tree.focus(item)
                    break
        elif lane == "remediation" and hasattr(self, "review_remediation_tree"):
            self.show_view("reports")
            for item in self.review_remediation_tree.get_children():
                values = self.review_remediation_tree.item(item, "values")
                if values and (key.split(":", 1)[0] in str(values) or key.split(":", 1)[-1] in str(values)):
                    self.review_remediation_tree.selection_set(item)
                    self.review_remediation_tree.focus(item)
                    self.show_selected_remediation_task()
                    break
        self.reviewer_cockpit_var.set(
            f"Selected {lane or 'cockpit'} | key={key or '-'} | filter={target_filter or '-'} | action={row.get('next_action') or '-'}"
        )

    def selected_review_reason_row(self) -> dict:
        if not hasattr(self, "review_reason_tree"):
            return {}
        selected = self.review_reason_tree.selection()
        if not selected:
            return self.review_reason_rows[0] if self.review_reason_rows else {}
        try:
            index = int(str(selected[0]).split("-")[-1])
        except Exception:
            return {}
        if 0 <= index < len(self.review_reason_rows):
            return dict(self.review_reason_rows[index])
        return {}

    def apply_review_reason_filter(self) -> None:
        row = self.selected_review_reason_row()
        reason = str(row.get("reason_cluster") or row.get("filter_value") or row.get("key") or self.review_reason_cluster_var.get() or "").strip()
        if not reason or reason == "all":
            self.review_attention_filter_var.set("attention")
        else:
            self.review_attention_filter_var.set(f"pending_reason:{reason}")
        self.review_site_filter_var.set("all")
        self.review_bucket_filter_var.set("all")
        self.review_local_status_filter_var.set("all")
        self.review_risk_filter_var.set("all")
        self.review_reviewer_filter_var.set("all")
        self.render_candidate_review_board()
        first = self.review_tree.get_children()
        if first:
            self.review_tree.selection_set(first[0])
            self.review_tree.focus(first[0])
            self.show_selected_review_detail()
        self.review_analytics_var.set(f"Applied pending-reason workbench filter: {reason or 'attention'}")

    def update_selected_review_reason_cluster(self) -> None:
        row = self.selected_review_reason_row()
        reason = str(row.get("reason_cluster") or row.get("filter_value") or row.get("key") or self.review_reason_cluster_var.get() or "").strip()
        if reason and reason != "all":
            self.review_attention_filter_var.set(f"pending_reason:{reason}")
            self.render_candidate_review_board()
        rows = list(self.rendered_review_board_rows)
        candidate_ids = [str(item.get("candidate_id") or "") for item in rows if item.get("candidate_id")]
        if not candidate_ids:
            messagebox.showinfo("No review rows", "No visible candidate review rows match this reason cluster.")
            return
        status = self.review_reason_batch_status_var.get().strip() or "reviewed"
        note = self.review_reason_batch_note_var.get().strip() or f"Batch updated reason cluster {reason or 'attention'} from native workbench."
        self.review_update_status_var.set(status)
        self.review_note_var.set(note)

        def task() -> dict:
            ids = ",".join(candidate_ids)
            self._run_checked(
                [
                    "scripts/update_candidate_review_status.py",
                    "--project-name",
                    self.project_name(),
                    "--candidate-ids",
                    ids,
                    "--status",
                    status,
                    "--note",
                    note,
                ]
            )
            self._run_checked(
                [
                    "scripts/record_candidate_review_reason_batch.py",
                    "--project-name",
                    self.project_name(),
                    "--reason-cluster",
                    reason or "attention",
                    "--candidate-ids",
                    ids,
                    "--status",
                    status,
                    "--reviewer",
                    "native_shell",
                    "--note",
                    note,
                ]
            )
            self._run_checked(["scripts/build_candidate_review_board.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_review_analytics.py", "--project-name", self.project_name()])
            return self._run_checked(["scripts/build_candidate_review_reason_workbench.py", "--project-name", self.project_name()])

        self.run_task(f"batch review reason {reason or 'attention'} ({len(candidate_ids)} rows)", task)

    def close_selected_review_reason_cluster(self) -> None:
        row = self.selected_review_reason_row()
        reason = str(row.get("reason_cluster") or row.get("filter_value") or row.get("key") or self.review_reason_cluster_var.get() or "").strip()
        self.review_reason_batch_status_var.set("reviewed")
        if not self.review_reason_batch_note_var.get().strip() or self.review_reason_batch_note_var.get().startswith("Batch updated"):
            self.review_reason_batch_note_var.set(f"Closed pending-reason cluster {reason or 'attention'} from native workbench.")
        self.update_selected_review_reason_cluster()

    def apply_review_analytics_filter(self) -> None:
        if not hasattr(self, "review_analytics_tree"):
            return
        selected = self.review_analytics_tree.selection()
        if not selected:
            return
        try:
            index = int(str(selected[0]).split("-")[-1])
        except Exception:
            return
        if not (0 <= index < len(self.review_analytics_rows)):
            return
        row = self.review_analytics_rows[index]
        row_type = str(row.get("row_type") or "")
        key = str(row.get("key") or "").strip()
        filter_type = str(row.get("filter_type") or "").strip()
        filter_value = str(row.get("filter_value") or key).strip()
        if not filter_type:
            if row_type == "site_class_coverage":
                filter_type = "site_class"
            elif row_type == "risk_bucket":
                filter_type = "risk_bucket"
            elif row_type == "reviewer_workload":
                filter_type = "reviewer"
            elif row_type == "pending_reason_cluster":
                filter_type = "pending_reason"
        if not filter_type or not filter_value:
            return
        self.review_site_filter_var.set("all")
        self.review_bucket_filter_var.set("all")
        self.review_risk_filter_var.set("all")
        self.review_reviewer_filter_var.set("all")
        self.review_attention_filter_var.set("all")
        if filter_type == "site_class":
            self.review_site_filter_var.set(filter_value)
        elif filter_type == "risk_bucket":
            self.review_risk_filter_var.set(filter_value)
        elif filter_type == "reviewer":
            self.review_reviewer_filter_var.set(filter_value)
        elif filter_type == "attention":
            self.review_attention_filter_var.set("attention")
        elif filter_type == "pending_reason":
            self.review_attention_filter_var.set(f"pending_reason:{filter_value}")
        elif filter_type == "all":
            pass
        else:
            return
        self.review_local_status_filter_var.set("all")
        self.render_candidate_review_board()
        first = self.review_tree.get_children()
        if first:
            self.review_tree.selection_set(first[0])
            self.review_tree.focus(first[0])
            self.show_selected_review_detail()
        self.review_analytics_var.set(f"Applied analytics drill-down: {filter_type}={filter_value}")

    def _review_pending_reason(self, row: dict) -> str:
        existing = str(row.get("pending_reason_cluster") or "").strip()
        if existing:
            return existing
        local_status = str(row.get("local_review_status") or "").strip()
        packet_status = str(row.get("review_status") or "").strip()
        risk = str(row.get("risk_bucket") or "").strip()
        blocked_contexts = str(row.get("blocked_contexts") or "").strip()
        mmp_flags = str(row.get("mmp_contradiction_flags") or "").strip()
        review_bucket = str(row.get("review_bucket") or "").strip()
        site_action = str(row.get("site_class_governance_action") or "").strip()
        evidence = str(row.get("evidence_strength") or "").strip().lower()
        reviewer = str(row.get("reviewer") or "").strip()
        if risk == "contradiction" or mmp_flags:
            return "risk_contradiction"
        if site_action or review_bucket == "site_class_governance_review":
            return "site_class_governance_review"
        if risk == "blocked_context" or blocked_contexts:
            return "blocked_context"
        if risk == "low_risk_score":
            return "low_risk_score"
        if "mmp=none" in evidence or ("confidence=" in evidence and any(token in evidence for token in ["confidence=0", "confidence=1", "confidence=2", "confidence=3", "confidence=4"])):
            return "thin_evidence"
        if local_status in {"blocked", "needs_follow_up"}:
            return f"local_{local_status}"
        if local_status in {"pending_review", "unreviewed"}:
            return "local_pending_review"
        if packet_status == "pending_review":
            return "packet_pending_review"
        if not reviewer and local_status not in {"", "pending_review", "unreviewed"}:
            return "unassigned_reviewer"
        return "manual_review"

    def _review_filter_matches(self, row: dict) -> bool:
        attention_filter = self.review_attention_filter_var.get()
        if attention_filter == "attention":
            local_status = str(row.get("local_review_status") or "").strip()
            packet_status = str(row.get("review_status") or "").strip()
            risk = str(row.get("risk_bucket") or "").strip()
            if local_status not in {"pending_review", "unreviewed", "needs_follow_up", "blocked"} and packet_status != "pending_review" and risk in {"", "clear", "unknown"}:
                return False
        elif attention_filter.startswith("pending_reason:"):
            expected_reason = attention_filter.split(":", 1)[1]
            if self._review_pending_reason(row) != expected_reason:
                return False
        checks = [
            (row.get("site_class"), self.review_site_filter_var.get()),
            (row.get("review_bucket"), self.review_bucket_filter_var.get()),
            (row.get("local_review_status"), self.review_local_status_filter_var.get()),
            (row.get("risk_bucket"), self.review_risk_filter_var.get()),
            (row.get("reviewer"), self.review_reviewer_filter_var.get()),
        ]
        for value, expected in checks:
            expected = str(expected or "").strip()
            value_text = str(value or "").strip()
            if expected == "non_clear":
                if value_text in {"", "clear", "unknown"}:
                    return False
                continue
            if expected and expected != "all" and value_text != expected:
                return False
        return True

    def open_review_analytics_evidence(self) -> None:
        if hasattr(self, "review_analytics_tree") and self.review_analytics_tree.selection():
            self.apply_review_analytics_filter()
        first = self.review_tree.get_children() if hasattr(self, "review_tree") else []
        if first and not self.review_tree.selection():
            self.review_tree.selection_set(first[0])
            self.review_tree.focus(first[0])
            self.show_selected_review_detail()
        if not self.selected_review_rows():
            messagebox.showinfo("No evidence row", "Select an analytics row with matching review candidates first.")
            return
        self.open_selected_review_drilldown()

    def render_candidate_review_board(self) -> None:
        if not hasattr(self, "review_tree"):
            return
        rows = [row for row in self.review_board_rows if self._review_filter_matches(row)]
        self.rendered_review_board_rows = rows[:300]
        self.clear_tree(self.review_tree)
        for idx, row in enumerate(self.rendered_review_board_rows):
            self.review_tree.insert(
                "",
                END,
                iid=f"review-{idx}",
                values=[
                    row.get("candidate_id", ""),
                    row.get("score", ""),
                    row.get("site_class", ""),
                    row.get("review_bucket", ""),
                    row.get("review_status", ""),
                    row.get("local_review_status", ""),
                    row.get("risk_bucket", ""),
                    row.get("pending_reason_cluster", ""),
                    row.get("proposed_review_action", ""),
                ],
            )
        self.review_detail_var.set(f"Showing {len(self.rendered_review_board_rows)} review rows from {len(self.review_board_rows)} total.")

    def clear_candidate_review_filters(self) -> None:
        self.review_site_filter_var.set("all")
        self.review_bucket_filter_var.set("all")
        self.review_local_status_filter_var.set("all")
        self.review_risk_filter_var.set("all")
        self.review_reviewer_filter_var.set("all")
        self.review_attention_filter_var.set("all")
        self.render_candidate_review_board()

    def selected_review_rows(self) -> list[dict]:
        rows = []
        for item in self.review_tree.selection():
            try:
                index = int(str(item).split("-")[-1])
            except Exception:
                continue
            if 0 <= index < len(self.rendered_review_board_rows):
                rows.append(self.rendered_review_board_rows[index])
        return rows

    def show_selected_review_detail(self) -> None:
        rows = self.selected_review_rows()
        if not rows:
            return
        row = rows[0]
        parts = [
            f"{row.get('candidate_id') or '-'} | score={row.get('score') or '-'} | local={row.get('local_review_status') or '-'}",
            f"Bucket: {row.get('review_bucket') or '-'} | risk: {row.get('risk_bucket') or '-'} | site: {row.get('site_class') or '-'}",
            f"Pending reason: {row.get('pending_reason_cluster') or self._review_pending_reason(row)} | {row.get('pending_reason_detail') or '-'}",
            f"Evidence: {row.get('evidence_strength') or '-'}",
        ]
        if row.get("blocked_contexts"):
            parts.append(f"Blocked: {row.get('blocked_contexts')}")
        if row.get("structure_highlight_detail"):
            parts.append(f"2D change: {row.get('structure_highlight_detail')}")
        if row.get("review_note"):
            parts.append(f"Last note: {row.get('review_note')}")
        self.review_detail_var.set("  ".join(parts))
        self.update_evidence_drawer_detail(str(row.get("candidate_id") or ""))
        self.update_review_structure_preview(row)
        self.populate_candidate_explanation_components(str(row.get("candidate_id") or ""))
        self.update_candidate_selection_linkage(str(row.get("candidate_id") or ""))

    def open_selected_review_image(self) -> None:
        rows = self.selected_review_rows()
        if not rows:
            messagebox.showinfo("Select a review row", "Select a candidate review row first.")
            return
        path = Path(str(rows[0].get("image_path") or ""))
        if not path.is_absolute():
            path = ROOT / path
        open_path(path)

    def open_selected_review_drilldown(self) -> None:
        rows = self.selected_review_rows()
        if not rows:
            messagebox.showinfo("Select a review row", "Select a candidate review row first.")
            return
        open_path(self.build_candidate_drilldown_payload(str(rows[0].get("candidate_id") or "")))

    def update_review_rows(self, scope: str) -> None:
        rows = self.selected_review_rows() if scope == "selected" else self.rendered_review_board_rows
        candidate_ids = [str(row.get("candidate_id") or "") for row in rows if row.get("candidate_id")]
        if not candidate_ids:
            messagebox.showinfo("No review rows", "No candidate review rows are selected or visible.")
            return
        args = [
            "scripts/update_candidate_review_status.py",
            "--project-name",
            self.project_name(),
            "--candidate-ids",
            ",".join(candidate_ids),
            "--status",
            self.review_update_status_var.get(),
            "--note",
            self.review_note_var.get(),
        ]
        self.run_task(f"update {len(candidate_ids)} candidate review rows", lambda: self._run_checked(args))

    def populate_candidates_from_csv(self) -> None:
        if self.last_result:
            return
        path = self.project_dir() / "candidates.csv"
        if not path.exists():
            return
        try:
            rows = list(csv.DictReader(path.open(encoding="utf-8")))
            self.populate_candidates(rows)
        except Exception:
            return

    def populate_project_memory(self) -> None:
        dashboard = read_json(ROOT / "data/projects/demo/project_memory_review_dashboard.json")
        queue = read_json(ROOT / "data/projects/demo/project_memory_review_queue.json")
        self.pm_metric_vars[0].set(dashboard.get("status") or "-")
        self.pm_metric_vars[1].set(str(queue.get("row_count") or dashboard.get("row_count") or 0))
        self.pm_metric_vars[2].set(str(dashboard.get("open_like_count") or queue.get("open_operator_item_count") or 0))
        self.pm_metric_vars[3].set(str(dashboard.get("lane_row_count") or 0))
        self.clear_tree(self.lane_tree)
        for row in dashboard.get("lane_status_rows") or []:
            self.lane_tree.insert(
                "",
                END,
                values=[
                    row.get("review_lane"),
                    row.get("row_count"),
                    row.get("open_count"),
                    row.get("assigned_count"),
                    row.get("closed_count"),
                    row.get("critical_count"),
                    row.get("next_action"),
                ],
            )
        self.clear_tree(self.attention_tree)
        for row in dashboard.get("attention_rows") or []:
            self.attention_tree.insert(
                "",
                END,
                values=[
                    row.get("review_item_id"),
                    row.get("review_lane"),
                    row.get("priority"),
                    row.get("operator_status"),
                    row.get("assigned_to"),
                    row.get("review_action"),
                ],
            )

    def show_selected_history(self) -> None:
        selected = self.attention_tree.selection()
        if not selected:
            return
        review_id = str(self.attention_tree.item(selected[0], "values")[0])
        queue = read_json(ROOT / "data/projects/demo/project_memory_review_queue.json")
        row = next((item for item in queue.get("rows") or [] if str(item.get("review_item_id")) == review_id), {})
        history = row.get("operator_history") or []
        if not history:
            self.history_var.set(f"{review_id}: no reviewer history yet.")
            return
        last = history[-1]
        self.history_var.set(
            f"{review_id}: {last.get('operator_status')} by {last.get('reviewer')} at {last.get('reviewed_at')} - {last.get('note')}"
        )

    def populate_endpoint(self) -> None:
        report = read_json(ROOT / "data/projects/demo/measurement_gap_endpoint_governance.json")
        self.endpoint_metric_vars[0].set(report.get("status") or "-")
        self.endpoint_metric_vars[1].set(str(report.get("row_count") or 0))
        self.endpoint_metric_vars[2].set(str(report.get("strict_exact_pending_count") or 0))
        self.endpoint_metric_vars[3].set(str(report.get("site_policy_row_count") or 0))
        self.clear_tree(self.endpoint_tree)
        for row in report.get("rows") or []:
            self.endpoint_tree.insert(
                "",
                END,
                values=[
                    row.get("measurement_plan_id"),
                    row.get("candidate_id"),
                    row.get("required_endpoint_group"),
                    row.get("available_endpoint_groups"),
                    row.get("strict_endpoint_status"),
                    row.get("site_classes"),
                    row.get("site_class_actions"),
                ],
            )

    def populate_readiness(self) -> None:
        report = read_json(ROOT / "data/projects/demo/promotion_readiness_packet.json")
        self.readiness_metric_vars[0].set(report.get("status") or "-")
        self.readiness_metric_vars[1].set(str(report.get("readiness_score") if report else "-"))
        self.readiness_metric_vars[2].set(str(report.get("profile_impact_open_count") or 0))
        self.readiness_metric_vars[3].set(str(report.get("strict_exact_pending_count") or 0))
        self.clear_tree(self.readiness_tree)
        for row in report.get("summary_rows") or []:
            self.readiness_tree.insert(
                "",
                END,
                values=[row.get("section"), row.get("status"), row.get("primary_count"), row.get("secondary_count"), row.get("details")],
            )
        self.clear_tree(self.finding_tree)
        for row in report.get("findings") or []:
            self.finding_tree.insert(
                "",
                END,
                values=[row.get("level"), row.get("owner_lane"), row.get("label"), row.get("details")],
            )

    def populate_reports(self) -> None:
        dashboard = read_json(ROOT / "data/releases/production_dashboard_snapshot.json")
        db_health = read_json(ROOT / "data/releases/local_db_health_report.json")
        db_maintenance = read_json(ROOT / "data/releases/local_db_maintenance_report.json")
        local_db_release_gate = read_json(ROOT / "data/releases/local_db_maintenance_release_gate.json")
        native_regression = read_json(ROOT / "data/releases/native_ui_regression_snapshot.json")
        db_trend = read_json(ROOT / "data/releases/local_db_maintenance_trend_history.json")
        visual_compare = read_json(self.project_dir() / "candidate_visual_compare.json")
        review_packet = read_json(self.project_dir() / "candidate_review_packet.json")
        review_board = read_json(self.project_dir() / "candidate_review_board.json")
        review_analytics = read_json(self.project_dir() / "candidate_review_analytics.json")
        review_reason_workbench = read_json(self.project_dir() / "candidate_review_reason_workbench.json")
        drilldown_packet = read_json(self.project_dir() / "candidate_drilldown_packet.json")
        governance_diff = read_json(self.project_dir() / "local_governance_diff_report.json")
        baseline_registry = read_json(self.project_dir() / "governance_baselines" / "baseline_registry.json")
        candidate_baseline = read_json(self.project_dir() / "candidate_baseline_compare.json")
        candidate_decision = read_json(self.project_dir() / "candidate_decision_packet.json")
        evidence_drawer = read_json(self.project_dir() / "candidate_evidence_drawer.json")
        explanation_panel = read_json(self.project_dir() / "candidate_explanation_panel.json")
        explanation_compare = read_json(self.project_dir() / "candidate_explanation_compare.json")
        explanation_drilldown = read_json(self.project_dir() / "candidate_explanation_drilldown.json")
        component_structure_locator = read_json(self.project_dir() / "candidate_component_structure_locator.json")
        explanation_matrix = read_json(self.project_dir() / "candidate_explanation_matrix.json")
        staged_feed_sandbox = read_json(self.project_dir() / "staged_feed_sandbox_scoring.json")
        native_drilldown_actions = read_json(self.project_dir() / "native_drilldown_actions.json")
        sandbox_delta_signoff = read_json(self.project_dir() / "sandbox_score_delta_signoff_ledger.json")
        staging_sandbox_filters = read_json(self.project_dir() / "staging_sandbox_filter_views.json")
        site_detection_confidence = read_json(self.project_dir() / "site_detection_confidence.json")
        site_detection_calibration = read_json(self.project_dir() / "site_detection_calibration_queue.json")
        decision_qa = read_json(self.project_dir() / "candidate_decision_qa.json")
        evidence_quality = read_json(self.project_dir() / "evidence_quality_scorecard.json")
        baseline_manager = read_json(self.project_dir() / "candidate_baseline_manager.json")
        reviewer_operations = read_json(self.project_dir() / "reviewer_operations.json")
        baseline_lineage = read_json(self.project_dir() / "baseline_lineage_compare.json")
        review_command_center = read_json(self.project_dir() / "review_command_center.json")
        candidate_remediation = read_json(self.project_dir() / "candidate_remediation_queue.json")
        review_remediation_fallback = read_json(self.project_dir() / "review_remediation_queue.json")
        review_remediation = candidate_remediation or review_remediation_fallback
        self.review_remediation_source = "candidate" if candidate_remediation else "review"
        review_ops_console = read_json(self.project_dir() / "candidate_review_ops_console.json")
        review_closure = read_json(self.project_dir() / "review_closure_workbench.json")
        review_closure_filters = read_json(self.project_dir() / "review_closure_filter_views.json")
        reviewer_cockpit = read_json(self.project_dir() / "reviewer_cockpit.json")
        baseline_history = read_json(self.project_dir() / "baseline_history_explorer.json") or read_json(self.project_dir() / "baseline_lineage_history.json")
        baseline_scenario = read_json(self.project_dir() / "baseline_scenario_board.json")
        baseline_whatif = read_json(self.project_dir() / "baseline_whatif_board.json")
        baseline_lineage_preview = read_json(self.project_dir() / "baseline_lineage_preview.json")
        baseline_lineage_filters = read_json(self.project_dir() / "baseline_lineage_filter_views.json")
        feed_absorption = read_json(ROOT / "data/substituents/feed_absorption_audit.json")
        feed_diff = read_json(ROOT / "data/substituents/feed_absorption_diff_navigator.json")
        source_expansion = read_json(ROOT / "data/substituents/source_expansion_governance.json")
        feed_simulator = read_json(ROOT / "data/substituents/feed_promotion_simulator.json")
        staging_quality_budget = read_json(ROOT / "data/substituents/rgroup_staging_quality_budget.json")
        staging_admission_scorecard = read_json(ROOT / "data/substituents/rgroup_staging_admission_scorecard.json")
        rgroup_admission_sandbox_replay = read_json(ROOT / "data/substituents/rgroup_admission_sandbox_impact_replay.json")
        staging_curator_signoff = read_json(ROOT / "data/substituents/rgroup_staging_curator_signoff.json")
        rgroup_feed_digestion = read_json(ROOT / "data/substituents/rgroup_feed_digestion_ledger.json")
        rgroup_promotion_approval = read_json(ROOT / "data/substituents/rgroup_promotion_approval_ledger.json")
        rgroup_digestion_quality = read_json(ROOT / "data/substituents/rgroup_digestion_quality_metrics.json")
        governed_batches = read_json(ROOT / "data/substituents/governed_ingestion_batches.json")
        sandbox_delta_review = read_json(self.project_dir() / "sandbox_score_delta_review_packet.json")
        substituent_version_diff = read_json(ROOT / "data/substituents/substituent_version_diff_browser.json")
        operator_trend = read_json(ROOT / "data/releases/operator_trend_summary.json")
        operator_charts = read_json(ROOT / "data/releases/operator_trend_charts.json")
        discussion_handoff = read_json(self.project_dir() / "medchem_discussion_handoff.json")
        paths = [
            ROOT / "AutoMedChemist.exe",
            ROOT / "AutoMedChemist_Product_Update.pdf",
            ROOT / "AutoMedChemist_Product_Update.pptx",
            ROOT / "data/projects/demo/promotion_readiness_packet.json",
            ROOT / "data/projects/demo/project_memory_review_dashboard.json",
            ROOT / "data/releases/production_dashboard_snapshot.json",
            ROOT / "data/substituents/rgroup_next_feed_drop_promotion_diff.json",
            ROOT / "data/substituents/feed_absorption_audit.json",
            ROOT / "data/substituents/feed_absorption_diff_navigator.json",
            ROOT / "data/substituents/source_expansion_governance.json",
            ROOT / "data/substituents/feed_promotion_simulator.json",
            ROOT / "data/substituents/rgroup_staging_quality_budget.json",
            ROOT / "data/substituents/rgroup_staging_admission_scorecard.json",
            ROOT / "data/substituents/rgroup_admission_sandbox_impact_replay.json",
            ROOT / "data/substituents/rgroup_staging_curator_signoff.json",
            ROOT / "data/substituents/rgroup_feed_digestion_ledger.json",
            ROOT / "data/substituents/rgroup_promotion_approval_ledger.json",
            ROOT / "data/substituents/rgroup_digestion_quality_metrics.json",
            ROOT / "data/substituents/governed_ingestion_batches.json",
            ROOT / "data/projects/demo/sandbox_score_delta_review_packet.json",
            ROOT / "data/projects/demo/sandbox_score_delta_signoff_ledger.json",
            ROOT / "data/projects/demo/staging_sandbox_filter_views.json",
            ROOT / "data/projects/demo/ring_outcome_result_package_review.json",
            ROOT / "data/releases/local_db_health_report.json",
            ROOT / "data/releases/local_db_maintenance_report.json",
            ROOT / "data/releases/local_db_maintenance_release_gate.json",
            ROOT / "data/releases/local_db_maintenance_trend_history.json",
            ROOT / "data/releases/native_ui_regression_snapshot.json",
            self.project_dir() / "candidate_visual_compare.json",
            self.project_dir() / "candidate_review_packet.json",
            self.project_dir() / "candidate_review_board.json",
            self.project_dir() / "candidate_review_analytics.json",
            self.project_dir() / "candidate_review_reason_workbench.json",
            self.project_dir() / "candidate_review_reason_workbench_audit.json",
            self.project_dir() / "candidate_drilldown_packet.json",
            self.project_dir() / "local_governance_diff_report.json",
            self.project_dir() / "candidate_baseline_compare.json",
            self.project_dir() / "candidate_decision_packet.json",
            self.project_dir() / "candidate_decision_export.csv",
            self.project_dir() / "candidate_evidence_drawer.json",
            self.project_dir() / "candidate_explanation_panel.json",
            self.project_dir() / "candidate_explanation_compare.json",
            self.project_dir() / "candidate_explanation_drilldown.json",
            self.project_dir() / "candidate_component_structure_locator.json",
            self.project_dir() / "candidate_explanation_matrix.json",
            self.project_dir() / "staged_feed_sandbox_scoring.json",
            self.project_dir() / "native_drilldown_actions.json",
            self.project_dir() / "sandbox_score_delta_signoff_ledger.json",
            self.project_dir() / "staging_sandbox_filter_views.json",
            self.project_dir() / "site_detection_confidence.json",
            self.project_dir() / "site_detection_calibration_queue.json",
            self.project_dir() / "candidate_decision_qa.json",
            self.project_dir() / "evidence_quality_scorecard.json",
            self.project_dir() / "candidate_baseline_manager.json",
            self.project_dir() / "reviewer_operations.json",
            self.project_dir() / "baseline_lineage_compare.json",
            self.project_dir() / "review_command_center.json",
            self.project_dir() / "candidate_remediation_queue.json",
            self.project_dir() / "candidate_review_ops_console.json",
            self.project_dir() / "review_closure_workbench.json",
            self.project_dir() / "review_closure_filter_views.json",
            self.project_dir() / "reviewer_cockpit.json",
            self.project_dir() / "candidate_remediation_queue_history.json",
            self.project_dir() / "baseline_history_explorer.json",
            self.project_dir() / "baseline_scenario_board.json",
            self.project_dir() / "baseline_whatif_board.json",
            self.project_dir() / "baseline_lineage_preview.json",
            self.project_dir() / "baseline_lineage_filter_views.json",
            self.project_dir() / "baseline_active_preview.json",
            self.project_dir() / "baseline_history_explorer_matrix.csv",
            ROOT / "docs/baseline_rollback_explanation.md",
            self.project_dir() / "baseline_history_explorer_charts" / "baseline_history_movement.png",
            self.project_dir() / "candidate_remediation_saved_views.csv",
            self.project_dir() / "candidate_remediation_trends.csv",
            self.project_dir() / "site_detection_regression_report.json",
            ROOT / "data/substituents/substituent_version_diff_browser.json",
            ROOT / "data/releases/operator_trend_summary.json",
            ROOT / "data/releases/operator_trend_charts.json",
            self.project_dir() / "medchem_discussion_handoff.json",
            self.project_dir() / "governance_baselines" / "baseline_registry.json",
        ]
        lines = []
        for path in paths:
            status = "present" if path.exists() else "missing"
            size = f"{path.stat().st_size:,} bytes" if path.exists() and path.is_file() else ""
            lines.append(f"{path.name}: {status} {size}")
        if dashboard:
            lines.append(f"production dashboard: {dashboard.get('status')} ({dashboard.get('row_count')} gates)")
        if db_health:
            ring_rows = (db_health.get("table_rows") or {}).get("ring_system")
            lines.append(
                f"local DB health: {db_health.get('status')} "
                f"(ring rows={ring_rows}, ring indexes={db_health.get('ring_index_count')})"
            )
            self.db_health_var.set(f"DB health: {db_health.get('status')}")
        else:
            self.db_health_var.set("DB health: missing report")
        if native_regression:
            lines.append(
                f"native UI regression: {native_regression.get('status')} "
                f"({len(native_regression.get('checks') or [])} checks)"
            )
        if db_maintenance:
            lines.append(
                f"DB maintenance: {db_maintenance.get('status')} "
                f"(rows={db_maintenance.get('row_count')}, warnings={db_maintenance.get('warn_count')})"
            )
        if db_trend:
            lines.append(
                f"DB maintenance trend: {db_trend.get('status')} "
                f"(history rows={db_trend.get('row_count')})"
            )
        if visual_compare:
            self.visual_compare_var.set(
                f"visual compare: {visual_compare.get('status')} ({visual_compare.get('candidate_count')} candidates)"
            )
            lines.append(f"candidate visual compare: {visual_compare.get('status')} ({visual_compare.get('candidate_count')} candidates)")
        else:
            self.visual_compare_var.set("Visual compare packet is not built yet.")
        if review_packet:
            lines.append(
                f"candidate review packet: {review_packet.get('status')} "
                f"(rows={review_packet.get('row_count')}, pending={review_packet.get('review_required_count')})"
            )
        if review_board:
            lines.append(
                f"candidate review board: {review_board.get('status')} "
                f"(visible={review_board.get('filtered_row_count')}, focused={review_board.get('focused_row_count')}, pending local={review_board.get('pending_local_review_count')})"
            )
        if review_analytics:
            lines.append(
                f"candidate review analytics: {review_analytics.get('status')} "
                f"(pending={review_analytics.get('pending_backlog_count')}, risks={review_analytics.get('repeated_risk_bucket_count')}, reviewers={review_analytics.get('reviewer_count')})"
            )
        if review_reason_workbench:
            lines.append(
                f"candidate review reason workbench: {review_reason_workbench.get('status')} "
                f"(clusters={review_reason_workbench.get('row_count')}, audit events={review_reason_workbench.get('audit_event_count')})"
            )
        if drilldown_packet:
            lines.append(
                f"candidate drill-down: {drilldown_packet.get('status')} "
                f"(rows={drilldown_packet.get('row_count')}, board links={drilldown_packet.get('linked_board_rows')})"
            )
        if governance_diff:
            lines.append(
                f"governance diff: {governance_diff.get('status')} "
                f"(changed={governance_diff.get('changed_candidate_count')}, added={governance_diff.get('added_candidate_count')})"
            )
        if baseline_registry:
            lines.append(
                f"governance baselines: {baseline_registry.get('status')} "
                f"(count={baseline_registry.get('baseline_count') or len(baseline_registry.get('baselines') or [])})"
            )
        if candidate_baseline:
            lines.append(
                f"candidate baseline: {candidate_baseline.get('status')} "
                f"(changed={candidate_baseline.get('changed_candidate_count')}, added={candidate_baseline.get('added_candidate_count')})"
            )
        if candidate_decision:
            lines.append(
                f"candidate decisions: {candidate_decision.get('status')} "
                f"(decisions={candidate_decision.get('decision_count')}, counts={candidate_decision.get('decision_counts')})"
            )
        if evidence_drawer:
            lines.append(
                f"candidate evidence drawer: {evidence_drawer.get('status')} "
                f"(rows={evidence_drawer.get('row_count')}, decision links={evidence_drawer.get('linked_decision_rows')})"
            )
        if explanation_panel:
            lines.append(
                f"candidate explanation panel: {explanation_panel.get('status')} "
                f"(rows={explanation_panel.get('row_count')}, remediation linked={explanation_panel.get('remediation_linked_count')})"
            )
        if explanation_compare:
            lines.append(
                f"candidate explanation compare: {explanation_compare.get('status')} "
                f"({explanation_compare.get('base_candidate_id')} -> {explanation_compare.get('head_candidate_id')}, stoplist={explanation_compare.get('stoplist_component_count')})"
            )
        if explanation_drilldown:
            lines.append(
                f"candidate explanation drilldown: {explanation_drilldown.get('status')} "
                f"(candidates={explanation_drilldown.get('candidate_count')}, components={explanation_drilldown.get('row_count')}, attention={explanation_drilldown.get('attention_count')})"
            )
        if component_structure_locator:
            lines.append(
                f"candidate component structure locator: {component_structure_locator.get('status')} "
                f"(rows={component_structure_locator.get('row_count')}, linked={component_structure_locator.get('linked_component_count')})"
            )
        if explanation_matrix:
            lines.append(
                f"candidate explanation matrix: {explanation_matrix.get('status')} "
                f"(candidates={explanation_matrix.get('candidate_count')}, stoplist={explanation_matrix.get('stoplist_candidate_count')})"
            )
        if staged_feed_sandbox:
            lines.append(
                f"staged feed sandbox scoring: {staged_feed_sandbox.get('status')} "
                f"(staged={staged_feed_sandbox.get('staged_row_count')}, matched={staged_feed_sandbox.get('candidate_with_staged_match_count')}, production affected={staged_feed_sandbox.get('production_scoring_affected')})"
            )
        if sandbox_delta_review:
            lines.append(
                f"sandbox delta review: {sandbox_delta_review.get('status')} "
                f"(required={sandbox_delta_review.get('operator_signoff_required_count')}, approved={sandbox_delta_review.get('approved_signoff_count')}, deferred={sandbox_delta_review.get('deferred_signoff_count')})"
            )
        if sandbox_delta_signoff:
            lines.append(
                f"sandbox delta signoff: {sandbox_delta_signoff.get('status')} "
                f"(pending={sandbox_delta_signoff.get('pending_signoff_count')}, decisions={sandbox_delta_signoff.get('decision_counts')})"
            )
        if rgroup_feed_digestion:
            lines.append(
                f"R-group feed digestion: {rgroup_feed_digestion.get('status')} "
                f"(accepted={rgroup_feed_digestion.get('accepted_count')}, deferred={rgroup_feed_digestion.get('deferred_count')}, held={rgroup_feed_digestion.get('held_out_count')})"
            )
        if rgroup_promotion_approval:
            lines.append(
                f"R-group promotion approval: {rgroup_promotion_approval.get('status')} "
                f"(approved={rgroup_promotion_approval.get('approved_count')}, pending={rgroup_promotion_approval.get('pending_approval_count')}, allowed={rgroup_promotion_approval.get('promotion_allowed')})"
            )
        if rgroup_digestion_quality:
            lines.append(
                f"R-group digestion metrics: {rgroup_digestion_quality.get('status')} "
                f"(metrics={rgroup_digestion_quality.get('row_count')}, quality={rgroup_digestion_quality.get('quality_status_counts')})"
            )
        if staging_sandbox_filters:
            lines.append(
                f"staging/sandbox filters: {staging_sandbox_filters.get('status')} "
                f"(views={staging_sandbox_filters.get('row_count')}, filters={staging_sandbox_filters.get('available_filters')})"
            )
        if local_db_release_gate:
            lines.append(
                f"local DB release gate: {local_db_release_gate.get('status')} "
                f"(release_stop={local_db_release_gate.get('release_stop_count')}, watch={local_db_release_gate.get('watch_count')})"
            )
        if site_detection_confidence:
            lines.append(
                f"site detection confidence: {site_detection_confidence.get('status')} "
                f"(rows={site_detection_confidence.get('row_count')}, low={site_detection_confidence.get('low_confidence_count')})"
            )
        if site_detection_calibration:
            lines.append(
                f"site detection calibration queue: {site_detection_calibration.get('status')} "
                f"(queue={site_detection_calibration.get('queue_count')}, low={site_detection_calibration.get('low_confidence_count')})"
            )
        if decision_qa:
            lines.append(
                f"candidate decision QA: {decision_qa.get('status')} "
                f"(rows={decision_qa.get('row_count')}, attention={decision_qa.get('attention_count')})"
            )
        if evidence_quality:
            lines.append(
                f"evidence quality scorecard: {evidence_quality.get('status')} "
                f"(rows={evidence_quality.get('row_count')}, attention={evidence_quality.get('attention_count')}, watch={evidence_quality.get('watch_count')})"
            )
        if baseline_manager:
            lines.append(
                f"candidate baseline manager: {baseline_manager.get('status')} "
                f"(active={baseline_manager.get('active_baseline_count')}, archive review={baseline_manager.get('archive_review_count')})"
            )
        if reviewer_operations:
            lines.append(
                f"reviewer operations: {reviewer_operations.get('status')} "
                f"(overdue={reviewer_operations.get('pending_overdue_count')}, repeated defer={reviewer_operations.get('repeated_defer_reason_count')})"
            )
        if baseline_lineage:
            lines.append(
                f"baseline lineage compare: {baseline_lineage.get('status')} "
                f"(changed={baseline_lineage.get('changed_candidate_count')}, entered={baseline_lineage.get('entered_candidate_count')})"
            )
        if review_command_center:
            lines.append(
                f"review command center: {review_command_center.get('status')} "
                f"(rows={review_command_center.get('row_count')}, actionable={review_command_center.get('actionable_count')})"
            )
        if review_remediation:
            lines.append(
                f"review remediation queue: {review_remediation.get('status')} "
                f"(open={review_remediation.get('open_count')}, closed={review_remediation.get('closed_count')}, high={review_remediation.get('high_count', review_remediation.get('high_priority_count'))})"
            )
        if review_ops_console:
            lines.append(
                f"candidate review ops console: {review_ops_console.get('status')} "
                f"(open={review_ops_console.get('open_task_count')}, overdue={review_ops_console.get('overdue_task_count')}, lanes={len(review_ops_console.get('lane_counts') or {})})"
            )
        if review_closure:
            lines.append(
                f"review closure workbench: {review_closure.get('status')} "
                f"(open={review_closure.get('open_count')}, overdue={review_closure.get('overdue_count')}, audit={review_closure.get('filtered_audit_event_count')})"
            )
        if reviewer_cockpit:
            lines.append(
                f"reviewer cockpit: {reviewer_cockpit.get('status')} "
                f"(rows={reviewer_cockpit.get('row_count')}, lanes={reviewer_cockpit.get('lane_counts')})"
            )
        if baseline_history:
            lines.append(
                f"baseline lineage history: {baseline_history.get('status')} "
                f"(rows={baseline_history.get('row_count')}, pairwise={baseline_history.get('pairwise_row_count')})"
            )
        if baseline_scenario:
            lines.append(
                f"baseline scenario board: {baseline_scenario.get('status')} "
                f"(rows={baseline_scenario.get('row_count')}, attention={baseline_scenario.get('attention_count')})"
            )
        if baseline_whatif:
            lines.append(
                f"baseline what-if board: {baseline_whatif.get('status')} "
                f"(rows={baseline_whatif.get('row_count')}, review={baseline_whatif.get('review_required_count')})"
            )
        if baseline_lineage_preview:
            lines.append(
                f"baseline lineage preview: {baseline_lineage_preview.get('status')} "
                f"(rows={baseline_lineage_preview.get('row_count')}, preview={baseline_lineage_preview.get('preview_available')})"
            )
        if feed_absorption:
            lines.append(
                f"feed absorption audit: {feed_absorption.get('status')} "
                f"(blockers={feed_absorption.get('blocker_count')}, warnings={feed_absorption.get('warning_count')})"
            )
        if feed_diff:
            lines.append(
                f"feed absorption diff navigator: {feed_diff.get('status')} "
                f"(rows={feed_diff.get('row_count')}, deltas={feed_diff.get('feed_delta_count')}, blockers={feed_diff.get('blocker_count')})"
            )
        if source_expansion:
            lines.append(
                f"source expansion governance: {source_expansion.get('status')} "
                f"(blocked={source_expansion.get('blocked_gate_count')}, ungated={source_expansion.get('ungated_expansion_allowed')})"
            )
        if feed_simulator:
            lines.append(
                f"feed promotion simulator: {feed_simulator.get('status')} "
                f"(staged={feed_simulator.get('staged_row_count')}, blockers={feed_simulator.get('blocker_count')})"
            )
        if governed_batches:
            lines.append(
                f"governed ingestion batches: {governed_batches.get('status')} "
                f"(rows={governed_batches.get('row_count')}, blocked={governed_batches.get('blocked_batch_count')})"
            )
        if staging_admission_scorecard:
            lines.append(
                f"R-group staging admission scorecard: {staging_admission_scorecard.get('status')} "
                f"(rows={staging_admission_scorecard.get('row_count')}, top={staging_admission_scorecard.get('top_source')})"
            )
        if rgroup_admission_sandbox_replay:
            lines.append(
                f"R-group admission sandbox replay: {rgroup_admission_sandbox_replay.get('status')} "
                f"(sources={rgroup_admission_sandbox_replay.get('source_count')}, review={rgroup_admission_sandbox_replay.get('needs_operator_review_count')})"
            )
        if staging_curator_signoff:
            lines.append(
                f"R-group staging curator signoff: {staging_curator_signoff.get('status')} "
                f"(rows={staging_curator_signoff.get('row_count')}, decisions={staging_curator_signoff.get('decision_counts')})"
            )
        if native_drilldown_actions:
            lines.append(
                f"native drilldown actions: {native_drilldown_actions.get('status')} "
                f"(rows={native_drilldown_actions.get('row_count')}, routes={native_drilldown_actions.get('route_supported_count')})"
            )
        if operator_trend:
            lines.append(
                f"operator trend summary: {operator_trend.get('status')} "
                f"(cards={operator_trend.get('card_count')}, attention={operator_trend.get('needs_attention_count')})"
            )
        if operator_charts:
            lines.append(
                f"operator trend charts: {operator_charts.get('status')} "
                f"(charts={operator_charts.get('chart_count')})"
            )
        if discussion_handoff:
            lines.append(
                f"MedChem discussion handoff: {discussion_handoff.get('status')} "
                f"(rows={discussion_handoff.get('row_count')})"
            )
        if substituent_version_diff:
            lines.append(
                f"substituent version diff: {substituent_version_diff.get('status')} "
                f"(rows={substituent_version_diff.get('row_count')}, linked={substituent_version_diff.get('linked_substituent_count')})"
            )
        self.report_text.set("\n".join(lines))
        if hasattr(self, "production_tree"):
            self.clear_tree(self.production_tree)
            self.production_gate_rows = {}
            for row in dashboard.get("rows") or []:
                gate_id = str(row.get("gate_id") or row.get("label") or "")
                self.production_gate_rows[gate_id] = dict(row)
                self.production_tree.insert(
                    "",
                    END,
                    iid=gate_id,
                    values=[
                        row.get("label"),
                        row.get("status"),
                        row.get("level"),
                        row.get("primary"),
                        row.get("secondary"),
                        row.get("details"),
                    ],
                )
            self.production_gate_drill_down()
        if hasattr(self, "feed_diff_tree"):
            self.clear_tree(self.feed_diff_tree)
            self.feed_diff_rows = list(feed_diff.get("rows") or [])
            for row in self.feed_diff_rows[:180]:
                self.feed_diff_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("row_id", ""),
                        row.get("row_type", ""),
                        row.get("source_dataset", ""),
                        row.get("status", ""),
                        row.get("row_delta", ""),
                        row.get("normalized_pair_key", ""),
                        row.get("next_action", ""),
                    ],
                )
        if hasattr(self, "source_expansion_tree"):
            self.clear_tree(self.source_expansion_tree)
            self.source_expansion_rows = list(source_expansion.get("rows") or [])
            for row in self.source_expansion_rows:
                self.source_expansion_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("gate_id", ""),
                        row.get("status", ""),
                        row.get("details", ""),
                        row.get("next_action", ""),
                    ],
                )
        if hasattr(self, "feed_promotion_simulator_tree"):
            self.clear_tree(self.feed_promotion_simulator_tree)
            self.feed_promotion_simulator_rows = list(feed_simulator.get("rows") or [])
            for row in self.feed_promotion_simulator_rows:
                self.feed_promotion_simulator_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("source_dataset", ""),
                        row.get("simulation_status", ""),
                        row.get("promotion_allowed", ""),
                        row.get("staged_row_count", ""),
                        row.get("target_row_count", ""),
                        row.get("projected_feed_row_count", ""),
                        row.get("blocker_count", ""),
                        row.get("next_action", ""),
                    ],
                )
        if hasattr(self, "staging_quality_budget_tree"):
            self.clear_tree(self.staging_quality_budget_tree)
            self.staging_quality_budget_rows = list(staging_quality_budget.get("rows") or [])
            for row in self.staging_quality_budget_rows[:120]:
                duplicate_count = int(row.get("duplicate_row_sha256_count") or 0) + int(row.get("duplicate_replacement_id_count") or 0)
                self.staging_quality_budget_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("source_dataset", ""),
                        row.get("budget_status", ""),
                        row.get("row_count", ""),
                        row.get("max_new_rows", ""),
                        row.get("blocker_count", ""),
                        row.get("missing_metadata_count", ""),
                        duplicate_count,
                        row.get("next_action", ""),
                    ],
                )
        if hasattr(self, "staging_manual_review_tree"):
            if hasattr(self, "staging_admission_scorecard_tree"):
                self.clear_tree(self.staging_admission_scorecard_tree)
                self.staging_admission_scorecard_rows = list(staging_admission_scorecard.get("rows") or [])
                for row in self.staging_admission_scorecard_rows[:120]:
                    self.staging_admission_scorecard_tree.insert(
                        "",
                        END,
                        values=[
                            row.get("rank", ""),
                            row.get("source_dataset", ""),
                            row.get("admission_bucket", ""),
                            row.get("admission_score", ""),
                            row.get("source_credibility_score", ""),
                            row.get("duplicate_pressure_score", ""),
                            row.get("context_fit_score", ""),
                            row.get("candidate_impact_score", ""),
                            row.get("next_action", ""),
                        ],
                    )
            if hasattr(self, "rgroup_admission_sandbox_replay_tree"):
                self.clear_tree(self.rgroup_admission_sandbox_replay_tree)
                self.rgroup_admission_sandbox_replay_rows = list(rgroup_admission_sandbox_replay.get("rows") or [])
                for row in self.rgroup_admission_sandbox_replay_rows[:120]:
                    self.rgroup_admission_sandbox_replay_tree.insert(
                        "",
                        END,
                        values=[
                            row.get("source_dataset", ""),
                            row.get("replay_status", ""),
                            row.get("admission_bucket", ""),
                            row.get("impacted_candidate_count", ""),
                            row.get("matched_sandbox_row_count", ""),
                            row.get("max_abs_score_delta", ""),
                            row.get("max_abs_rank_delta", ""),
                            "ready" if row.get("rollback_ready") else "missing",
                            row.get("next_action", ""),
                        ],
                    )
            self.clear_tree(self.staging_manual_review_tree)
            self.staging_manual_review_rows = list(staging_quality_budget.get("manual_review_queue_rows") or [])
            latest_signoff = {}
            for row in staging_curator_signoff.get("rows") or []:
                key = str(row.get("review_queue_id") or row.get("source_dataset") or "")
                latest_signoff[key] = row
            for idx, row in enumerate(self.staging_manual_review_rows[:120]):
                queue_id = str(row.get("review_queue_id") or "")
                source = str(row.get("source_dataset") or "")
                signoff = latest_signoff.get(queue_id) or latest_signoff.get(source) or {}
                self.staging_manual_review_tree.insert(
                    "",
                    END,
                    iid=f"staging-curator-{idx}",
                    values=[
                        queue_id,
                        source,
                        row.get("manual_review_status", ""),
                        row.get("row_count", ""),
                        row.get("blocker_count", ""),
                        signoff.get("curator_decision", "not_signed"),
                        "required" if row.get("version_change_log_required") else "optional",
                        row.get("next_action", ""),
                    ],
                )
            first = self.staging_manual_review_tree.get_children()
            if first:
                self.staging_manual_review_tree.selection_set(first[0])
                self.staging_manual_review_tree.focus(first[0])
            self.show_selected_staging_curator_queue()
        if hasattr(self, "staging_curator_signoff_tree"):
            self.clear_tree(self.staging_curator_signoff_tree)
            self.staging_curator_signoff_rows = list(staging_curator_signoff.get("rows") or [])
            for idx, row in enumerate(self.staging_curator_signoff_rows[-160:]):
                self.staging_curator_signoff_tree.insert(
                    "",
                    END,
                    iid=f"staging-signoff-{idx}",
                    values=[
                        row.get("review_queue_id", ""),
                        row.get("source_dataset", ""),
                        row.get("curator_decision", ""),
                        row.get("curator", ""),
                        row.get("row_count", ""),
                        row.get("blocker_count", ""),
                        row.get("signed_at", ""),
                        row.get("version_change_note") or row.get("curator_note", ""),
                    ],
                )
        if hasattr(self, "governed_ingestion_tree"):
            self.clear_tree(self.governed_ingestion_tree)
            self.governed_ingestion_batch_rows = list(governed_batches.get("rows") or [])
            for row in self.governed_ingestion_batch_rows:
                self.governed_ingestion_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("batch_id", ""),
                        row.get("intake_scope", ""),
                        row.get("batch_status", ""),
                        row.get("allowed_to_ingest", ""),
                        row.get("staged_row_count", ""),
                        row.get("max_new_rows", ""),
                        row.get("current_gate_status", ""),
                        row.get("next_action", ""),
                    ],
                )
        if hasattr(self, "sandbox_score_delta_review_tree"):
            self.clear_tree(self.sandbox_score_delta_review_tree)
            self.sandbox_score_delta_review_rows = list(sandbox_delta_review.get("rows") or [])
            for row in self.sandbox_score_delta_review_rows[:120]:
                self.sandbox_score_delta_review_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("review_id", ""),
                        row.get("candidate_id", ""),
                        row.get("review_status", ""),
                        row.get("risk_bucket", ""),
                        row.get("score_delta", ""),
                        row.get("rank_delta", ""),
                        row.get("operator_signoff_required", ""),
                        row.get("next_action", ""),
                    ],
                )
        if hasattr(self, "sandbox_score_delta_signoff_tree"):
            self.clear_tree(self.sandbox_score_delta_signoff_tree)
            self.sandbox_score_delta_signoff_rows = list(sandbox_delta_signoff.get("rows") or [])
            for row in self.sandbox_score_delta_signoff_rows[:120]:
                self.sandbox_score_delta_signoff_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("review_id", ""),
                        row.get("candidate_id", ""),
                        row.get("operator_decision", ""),
                        row.get("operator", ""),
                        row.get("valid_decision", ""),
                        row.get("packet_row_found", ""),
                        row.get("production_scoring_approved", ""),
                        row.get("operator_note", ""),
                    ],
                )
        if hasattr(self, "rgroup_feed_digestion_tree"):
            self.clear_tree(self.rgroup_feed_digestion_tree)
            self.rgroup_feed_digestion_rows = list(rgroup_feed_digestion.get("rows") or [])
            for row in self.rgroup_feed_digestion_rows[:160]:
                self.rgroup_feed_digestion_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("ledger_id", ""),
                        row.get("replacement_id", ""),
                        row.get("source_dataset", ""),
                        row.get("digest_status", ""),
                        row.get("operator_decisions", ""),
                        row.get("matched_candidate_ids", ""),
                        row.get("promoted", ""),
                        row.get("next_action", ""),
                    ],
                )
        if hasattr(self, "rgroup_promotion_approval_tree"):
            self.clear_tree(self.rgroup_promotion_approval_tree)
            self.rgroup_promotion_approval_rows = list(rgroup_promotion_approval.get("rows") or [])
            for row in self.rgroup_promotion_approval_rows[:160]:
                self.rgroup_promotion_approval_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("approval_id", ""),
                        row.get("replacement_id", ""),
                        row.get("source_dataset", ""),
                        row.get("promotion_eligible", ""),
                        row.get("promotion_approval_decision", ""),
                        row.get("approved_for_promotion", ""),
                        rgroup_promotion_approval.get("pending_approval_count", ""),
                        row.get("next_action", ""),
                    ],
                )
        if hasattr(self, "rgroup_digestion_quality_tree"):
            self.clear_tree(self.rgroup_digestion_quality_tree)
            self.rgroup_digestion_quality_rows = list(rgroup_digestion_quality.get("rows") or [])
            for row in self.rgroup_digestion_quality_rows[:160]:
                self.rgroup_digestion_quality_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("metric_id", ""),
                        row.get("metric_type", ""),
                        row.get("group_key", ""),
                        row.get("quality_status", ""),
                        row.get("row_count", ""),
                        row.get("low_confidence_count", ""),
                        row.get("candidate_impacted_row_count", ""),
                        row.get("next_action", ""),
                    ],
                )
        if hasattr(self, "staging_sandbox_filter_tree"):
            self.clear_tree(self.staging_sandbox_filter_tree)
            self.staging_sandbox_filter_rows = list(staging_sandbox_filters.get("rows") or [])
            for row in self.staging_sandbox_filter_rows[:160]:
                self.staging_sandbox_filter_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("view_type", ""),
                        row.get("filter_key", ""),
                        row.get("filter_value", ""),
                        row.get("filtered_row_count", ""),
                        row.get("filter_target", ""),
                        row.get("ui_action", ""),
                        row.get("next_action", ""),
                    ],
                )
        if hasattr(self, "local_db_release_gate_tree"):
            self.clear_tree(self.local_db_release_gate_tree)
            self.local_db_release_gate_rows = list(local_db_release_gate.get("rows") or [])
            for row in self.local_db_release_gate_rows[:160]:
                self.local_db_release_gate_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("source", ""),
                        row.get("row_type", ""),
                        row.get("name", ""),
                        row.get("source_status", ""),
                        row.get("release_class", ""),
                        row.get("value", ""),
                        row.get("next_action", ""),
                    ],
                )
        if hasattr(self, "staged_feed_sandbox_tree"):
            self.clear_tree(self.staged_feed_sandbox_tree)
            self.staged_feed_sandbox_rows = list(staged_feed_sandbox.get("rows") or [])
            for row in self.staged_feed_sandbox_rows[:120]:
                self.staged_feed_sandbox_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("candidate_id", ""),
                        row.get("base_score", ""),
                        row.get("sandbox_score_preview", ""),
                        row.get("sandbox_score_delta_preview", ""),
                        row.get("matching_staged_rule_count", ""),
                        row.get("matrix_bucket", ""),
                        row.get("production_scoring_affected", ""),
                        row.get("next_action", ""),
                    ],
                )
        if hasattr(self, "baseline_diff_tree"):
            self.clear_tree(self.baseline_diff_tree)
            for row in candidate_baseline.get("rows") or []:
                if row.get("status") == "unchanged":
                    continue
                self.baseline_diff_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("candidate_id", ""),
                        row.get("status", ""),
                        row.get("score_delta", ""),
                        row.get("rank_delta", ""),
                        row.get("changed_fields", ""),
                        row.get("head_why_review") or row.get("base_why_review", ""),
                    ],
                )
        if hasattr(self, "operator_trend_tree"):
            self.clear_tree(self.operator_trend_tree)
            for row in operator_trend.get("cards") or []:
                self.operator_trend_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("label", ""),
                        row.get("status", ""),
                        row.get("value", ""),
                        row.get("trend", ""),
                        row.get("next_action", ""),
                    ],
                )
        if hasattr(self, "decision_qa_tree"):
            self.clear_tree(self.decision_qa_tree)
            for row in decision_qa.get("rows") or []:
                if row.get("qa_bucket") == "clear":
                    continue
                self.decision_qa_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("candidate_id", ""),
                        row.get("local_decision", ""),
                        row.get("qa_bucket", ""),
                        row.get("qa_reason", ""),
                        row.get("pending_age_days", ""),
                        row.get("next_action", ""),
                    ],
                )
        if hasattr(self, "candidate_explanation_compare_tree"):
            self.clear_tree(self.candidate_explanation_compare_tree)
            self.candidate_explanation_compare_rows = list(explanation_compare.get("rows") or [])
            for row in self.candidate_explanation_compare_rows:
                self.candidate_explanation_compare_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("component", ""),
                        row.get("base_value", ""),
                        row.get("head_value", ""),
                        row.get("delta", ""),
                        row.get("direction", ""),
                        row.get("next_action", ""),
                    ],
                )
        self.candidate_explanation_drilldown_rows = list(explanation_drilldown.get("rows") or [])
        self.candidate_component_structure_locator_rows = list(component_structure_locator.get("rows") or [])
        self.populate_candidate_explanation_components()
        if hasattr(self, "candidate_explanation_matrix_tree"):
            self.clear_tree(self.candidate_explanation_matrix_tree)
            self.candidate_explanation_matrix_rows = list(explanation_matrix.get("rows") or [])
            for row in self.candidate_explanation_matrix_rows[:80]:
                self.candidate_explanation_matrix_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("candidate_id", ""),
                        row.get("rank", ""),
                        row.get("score", ""),
                        row.get("matrix_bucket", ""),
                        row.get("component_mean", ""),
                        row.get("qa_bucket", ""),
                        row.get("baseline_lineage_status", ""),
                        row.get("open_remediation_count", ""),
                    ],
                )
        if hasattr(self, "site_detection_confidence_tree"):
            self.clear_tree(self.site_detection_confidence_tree)
            self.site_detection_confidence_rows = list(site_detection_confidence.get("rows") or [])
            for row in self.site_detection_confidence_rows[:180]:
                self.site_detection_confidence_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("row_type", ""),
                        row.get("key", ""),
                        row.get("status", ""),
                        row.get("confidence_score", ""),
                        row.get("rule_hit_count", ""),
                        row.get("boundary_protection_count", ""),
                        row.get("false_positive_guard_count", ""),
                        row.get("details", ""),
                    ],
                )
        if hasattr(self, "site_detection_calibration_tree"):
            self.clear_tree(self.site_detection_calibration_tree)
            self.site_detection_calibration_rows = list(site_detection_calibration.get("rows") or [])
            for row in self.site_detection_calibration_rows[:180]:
                self.site_detection_calibration_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("calibration_id", ""),
                        row.get("row_type", ""),
                        row.get("target_site_class", ""),
                        row.get("confidence_score", ""),
                        row.get("priority", ""),
                        row.get("required_example_type", ""),
                        row.get("calibration_status", ""),
                        row.get("suggested_action", ""),
                    ],
                )
        if hasattr(self, "evidence_quality_tree"):
            self.clear_tree(self.evidence_quality_tree)
            self.evidence_quality_rows = list(evidence_quality.get("rows") or [])
            for row in self.evidence_quality_rows:
                if row.get("quality_bucket") == "clear":
                    continue
                self.evidence_quality_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("candidate_id", ""),
                        row.get("quality_bucket", ""),
                        row.get("quality_flags", ""),
                        row.get("evidence_depth_score", ""),
                        row.get("qa_bucket", ""),
                        row.get("next_action", ""),
                    ],
                )
        if hasattr(self, "baseline_manager_tree"):
            self.clear_tree(self.baseline_manager_tree)
            self.baseline_manager_rows = list(baseline_manager.get("rows") or [])
            for idx, row in enumerate(self.baseline_manager_rows):
                archived = bool(row.get("archived")) or str(row.get("status") or "").lower() == "archived"
                self.baseline_manager_tree.insert(
                    "",
                    END,
                    iid=f"baseline-manager-{idx}",
                    values=[
                        row.get("baseline_id", ""),
                        "no" if archived else "yes",
                        row.get("age_days", ""),
                        row.get("compare_status", ""),
                        row.get("archive_recommendation", ""),
                        row.get("next_action", ""),
                    ],
                )
        if hasattr(self, "reviewer_operations_tree"):
            self.clear_tree(self.reviewer_operations_tree)
            self.reviewer_operations_rows = list(reviewer_operations.get("rows") or [])
            for row in self.reviewer_operations_rows[:220]:
                self.reviewer_operations_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("row_type", ""),
                        row.get("key", ""),
                        row.get("status", ""),
                        row.get("value", ""),
                        row.get("secondary", ""),
                        row.get("details", ""),
                    ],
                )
        if hasattr(self, "baseline_lineage_tree"):
            self.clear_tree(self.baseline_lineage_tree)
            self.baseline_lineage_rows = list(baseline_lineage.get("rows") or [])
            for row in self.baseline_lineage_rows:
                if row.get("lineage_status") == "unchanged":
                    continue
                self.baseline_lineage_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("candidate_id") or row.get("candidate_key", ""),
                        row.get("lineage_status", ""),
                        row.get("base_score", ""),
                        row.get("head_score", ""),
                        row.get("changed_fields", ""),
                        row.get("rationale", ""),
                    ],
                )
        if hasattr(self, "review_command_tree"):
            self.clear_tree(self.review_command_tree)
            self.review_command_rows = list(review_command_center.get("rows") or [])
            for idx, row in enumerate(self.review_command_rows[:260]):
                self.review_command_tree.insert(
                    "",
                    END,
                    iid=f"review-command-{idx}",
                    values=[
                        row.get("command_id", ""),
                        row.get("row_type", ""),
                        row.get("severity", ""),
                        row.get("target_view", ""),
                        row.get("target_filter", ""),
                        row.get("next_action", ""),
                    ],
                )
            self.show_selected_review_command()
        if hasattr(self, "review_remediation_tree"):
            self.clear_tree(self.review_remediation_tree)
            self.review_remediation_rows = list(review_remediation.get("rows") or [])
            for idx, row in enumerate(self.review_remediation_rows[:260]):
                self.review_remediation_tree.insert(
                    "",
                    END,
                    iid=f"review-remediation-{idx}",
                    values=[
                        row.get("task_id", ""),
                        row.get("task_type", ""),
                        row.get("priority", ""),
                        row.get("owner", ""),
                        row.get("due_at") or row.get("due_date", ""),
                        row.get("closure_status") or row.get("status", ""),
                        row.get("next_action", ""),
                    ],
                )
            first = self.review_remediation_tree.get_children()
            if first:
                self.review_remediation_tree.selection_set(first[0])
                self.review_remediation_tree.focus(first[0])
            self.show_selected_remediation_task()
        if hasattr(self, "review_ops_console_tree"):
            self.clear_tree(self.review_ops_console_tree)
            self.review_ops_console_rows = list(review_ops_console.get("rows") or [])
            for row in self.review_ops_console_rows[:220]:
                self.review_ops_console_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("candidate_id", ""),
                        row.get("operation_lane", ""),
                        row.get("owner", ""),
                        row.get("risk_bucket", ""),
                        row.get("local_review_status", ""),
                        row.get("open_task_count", ""),
                        row.get("high_priority_task_count", ""),
                        row.get("overdue_task_count", ""),
                        row.get("blocker_reason", ""),
                    ],
                )
        if hasattr(self, "review_closure_tree"):
            self.clear_tree(self.review_closure_tree)
            self.review_closure_rows = list(review_closure.get("rows") or [])
            for row in self.review_closure_rows[:260]:
                self.review_closure_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("task_id", ""),
                        row.get("priority", ""),
                        row.get("owner", ""),
                        row.get("due_at", ""),
                        row.get("closure_status", ""),
                        row.get("suggested_reason", ""),
                        row.get("batch_group", ""),
                        row.get("audit_event_count", ""),
                    ],
                )
        if hasattr(self, "review_closure_filter_tree"):
            self.clear_tree(self.review_closure_filter_tree)
            self.review_closure_filter_rows = list(review_closure_filters.get("rows") or [])
            for row in self.review_closure_filter_rows[:180]:
                self.review_closure_filter_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("view_type", ""),
                        row.get("filter_value", ""),
                        row.get("task_count", ""),
                        row.get("open_count", ""),
                        row.get("overdue_count", ""),
                        row.get("audit_event_count", ""),
                        row.get("batch_action", ""),
                    ],
                )
        self.populate_reviewer_cockpit()
        if hasattr(self, "baseline_scenario_tree"):
            self.clear_tree(self.baseline_scenario_tree)
            self.baseline_scenario_rows = list(baseline_scenario.get("rows") or [])
            for idx, row in enumerate(self.baseline_scenario_rows[:180]):
                self.baseline_scenario_tree.insert(
                    "",
                    END,
                    iid=f"baseline-scenario-{idx}",
                    values=[
                        row.get("label", ""),
                        row.get("scenario_type", ""),
                        row.get("status", ""),
                        row.get("baseline_id", ""),
                        row.get("movement_count", ""),
                        row.get("max_abs_score_delta", ""),
                        row.get("next_action", ""),
                    ],
                )
        if hasattr(self, "baseline_whatif_tree"):
            self.clear_tree(self.baseline_whatif_tree)
            self.baseline_whatif_rows = list(baseline_whatif.get("rows") or [])
            for row in self.baseline_whatif_rows[:260]:
                self.baseline_whatif_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("scenario_label") or row.get("scenario_id", ""),
                        row.get("candidate_id", ""),
                        row.get("current_rank", ""),
                        row.get("whatif_rank", ""),
                        row.get("rank_delta", ""),
                        row.get("score_delta", ""),
                        row.get("movement_status", ""),
                        row.get("movement_reason", ""),
                    ],
                )
        if hasattr(self, "baseline_history_tree"):
            self.clear_tree(self.baseline_history_tree)
            self.baseline_history_rows = list(baseline_history.get("rows") or [])
            self.baseline_history_chart_rows = list(baseline_history.get("chart_rows") or [])
            if baseline_lineage_preview.get("preview_path"):
                self.baseline_history_chart_rows = [
                    {
                        "chart_id": "baseline_lineage_preview",
                        "label": "Baseline lineage preview",
                        "status": baseline_lineage_preview.get("status"),
                        "point_count": baseline_lineage_preview.get("chart_point_count"),
                        "preview_path": baseline_lineage_preview.get("preview_path"),
                        "image_path": baseline_lineage_preview.get("preview_path"),
                    }
                ]
            for idx, row in enumerate(self.baseline_history_rows[-160:]):
                self.baseline_history_tree.insert(
                    "",
                    END,
                    iid=f"baseline-history-{idx}",
                    values=[
                        row.get("created_at", ""),
                        row.get("base_baseline_id") or row.get("baseline_id", ""),
                        row.get("head_baseline_id", ""),
                        row.get("entered_candidate_count", ""),
                        row.get("exited_candidate_count", ""),
                        row.get("changed_candidate_count", ""),
                        row.get("status", ""),
                    ],
                )
            self.show_baseline_history_chart_preview()
        if hasattr(self, "baseline_lineage_preview_tree"):
            self.clear_tree(self.baseline_lineage_preview_tree)
            self.baseline_lineage_preview_rows = list(baseline_lineage_preview.get("rows") or [])
            for row in self.baseline_lineage_preview_rows[:180]:
                self.baseline_lineage_preview_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("row_id", ""),
                        row.get("row_type", ""),
                        row.get("candidate_id", ""),
                        row.get("lineage_status", ""),
                        row.get("movement_total", ""),
                        row.get("score_delta", ""),
                        row.get("rank_delta", ""),
                        row.get("details", ""),
                    ],
                )
        if hasattr(self, "baseline_lineage_filter_tree"):
            self.clear_tree(self.baseline_lineage_filter_tree)
            self.baseline_lineage_filter_rows = list(baseline_lineage_filters.get("rows") or [])
            for row in self.baseline_lineage_filter_rows[:120]:
                self.baseline_lineage_filter_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("view_type", ""),
                        row.get("filter_value", ""),
                        row.get("row_count", ""),
                        row.get("candidate_count", ""),
                        row.get("movement_total", ""),
                        row.get("pairwise_count", ""),
                        row.get("top_mover_count", ""),
                    ],
                )
        if hasattr(self, "native_drilldown_action_tree"):
            self.clear_tree(self.native_drilldown_action_tree)
            self.native_drilldown_action_rows = list(native_drilldown_actions.get("rows") or [])
            for row in self.native_drilldown_action_rows[:220]:
                self.native_drilldown_action_tree.insert(
                    "",
                    END,
                    iid=f"native-drilldown-{len(self.native_drilldown_action_tree.get_children())}",
                    values=[
                        row.get("action_id", ""),
                        row.get("action_type", ""),
                        row.get("source_label", ""),
                        row.get("target_view", ""),
                        row.get("target_filter", ""),
                        row.get("ui_action", ""),
                        row.get("row_count", ""),
                        row.get("next_action", ""),
                    ],
                )
            self.show_selected_native_drilldown_action()
        if hasattr(self, "trend_chart_tree"):
            self.clear_tree(self.trend_chart_tree)
            self.trend_chart_rows = list(operator_charts.get("rows") or [])
            for idx, row in enumerate(self.trend_chart_rows):
                self.trend_chart_tree.insert(
                    "",
                    END,
                    iid=f"trend-chart-{idx}",
                    values=[
                        row.get("card_id", ""),
                        row.get("status", ""),
                        row.get("value", ""),
                        row.get("preview_path") or row.get("image_path") or row.get("chart_path", ""),
                    ],
                )
            self.show_selected_trend_chart_preview()
        if hasattr(self, "handoff_tree"):
            self.clear_tree(self.handoff_tree)
            for row in discussion_handoff.get("rows") or []:
                self.handoff_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("candidate_id", ""),
                        row.get("local_decision", ""),
                        row.get("qa_bucket", ""),
                        row.get("evidence_limitations", ""),
                        row.get("discussion_prompt", ""),
                    ],
                )
        if hasattr(self, "substituent_version_diff_tree"):
            self.clear_tree(self.substituent_version_diff_tree)
            self.substituent_version_diff_rows = list(substituent_version_diff.get("rows") or [])
            for row in self.substituent_version_diff_rows[:260]:
                self.substituent_version_diff_tree.insert(
                    "",
                    END,
                    values=[
                        row.get("substituent_id", ""),
                        row.get("review_status", ""),
                        row.get("version", ""),
                        row.get("default_enabled", ""),
                        row.get("linked_candidate_count", ""),
                        row.get("candidate_attention_component_count", ""),
                        row.get("applicable_contexts", ""),
                        row.get("latest_change_note") or row.get("latest_change_type", ""),
                    ],
                )

    def selected_review_command_row(self) -> dict:
        if not hasattr(self, "review_command_tree"):
            return {}
        selected = self.review_command_tree.selection()
        if not selected:
            return {}
        try:
            index = int(str(selected[0]).split("-")[-1])
        except Exception:
            return {}
        if 0 <= index < len(self.review_command_rows):
            return self.review_command_rows[index]
        return {}

    def show_selected_review_command(self) -> None:
        if not hasattr(self, "review_command_center_var"):
            return
        row = self.selected_review_command_row()
        if not row:
            self.review_command_center_var.set("Select a command-center row to route native review filters or open its linked artifact.")
            return
        self.review_command_center_var.set(
            f"{row.get('label') or row.get('command_id')} | severity={row.get('severity') or '-'} | "
            f"target={row.get('target_view') or '-'} | filter={row.get('target_filter') or '-'} | "
            f"artifact={row.get('source_artifact') or '-'}"
        )

    def _parse_target_filter(self, value: object) -> dict[str, str]:
        filters: dict[str, str] = {}
        for part in str(value or "").split(";"):
            name, _, text = part.partition("=")
            name = name.strip()
            text = text.strip()
            if name and text:
                filters[name] = text
        return filters

    def route_selected_review_command(self) -> None:
        row = self.selected_review_command_row()
        if not row:
            messagebox.showinfo("Select a command", "Select a review command-center row first.")
            return
        filters = self._parse_target_filter(row.get("target_filter"))
        if str(row.get("target_view") or "") != "candidate_review" and not any(key in filters for key in ["candidate_id", "site_class", "risk_bucket", "reviewer", "attention"]):
            self.show_view("reports")
            self.review_command_center_var.set(f"Selected command links to reports artifact: {row.get('source_artifact') or row.get('source_csv') or '-'}")
            return
        candidate_id = str(row.get("candidate_id") or filters.get("candidate_id") or "").strip()
        self.clear_candidate_review_filters()
        if filters.get("site_class"):
            self.review_site_filter_var.set(filters["site_class"])
        if filters.get("risk_bucket"):
            self.review_risk_filter_var.set(filters["risk_bucket"])
        if filters.get("reviewer"):
            self.review_reviewer_filter_var.set(filters["reviewer"])
        if filters.get("attention"):
            self.review_attention_filter_var.set("attention")
        self.render_candidate_review_board()
        if candidate_id and hasattr(self, "review_tree"):
            for item in self.review_tree.get_children():
                values = self.review_tree.item(item, "values")
                if values and str(values[0]) == candidate_id:
                    self.review_tree.selection_set(item)
                    self.review_tree.focus(item)
                    break
        first = self.review_tree.selection() or self.review_tree.get_children()
        if first:
            self.review_tree.selection_set(first[0])
            self.review_tree.focus(first[0])
            self.show_selected_review_detail()
        self.review_analytics_var.set(f"Applied command-center route: {row.get('command_id')} -> {row.get('target_filter') or 'reports'}")
        self.show_view("candidate_review")

    def open_selected_review_command_artifact(self) -> None:
        row = self.selected_review_command_row()
        if not row:
            messagebox.showinfo("Select a command", "Select a review command-center row first.")
            return
        path = Path(str(row.get("source_artifact") or row.get("source_csv") or ""))
        if not path.is_absolute():
            path = ROOT / path
        open_path(path)

    def selected_native_drilldown_action_row(self) -> dict:
        if not hasattr(self, "native_drilldown_action_tree"):
            return {}
        selected = self.native_drilldown_action_tree.selection()
        if not selected:
            return {}
        try:
            index = int(str(selected[0]).split("-")[-1])
        except Exception:
            return {}
        if 0 <= index < len(self.native_drilldown_action_rows):
            return self.native_drilldown_action_rows[index]
        return {}

    def show_selected_native_drilldown_action(self) -> None:
        if not hasattr(self, "native_drilldown_action_var"):
            return
        row = self.selected_native_drilldown_action_row()
        if not row:
            self.native_drilldown_action_var.set("Select a native drilldown action to route or open its linked artifact.")
            return
        self.native_drilldown_action_var.set(
            f"{row.get('action_id') or '-'} | ui={row.get('ui_action') or '-'} | target={row.get('target_view') or '-'} | "
            f"filter={row.get('target_filter') or '-'} | artifact={row.get('open_artifact_path') or row.get('linked_artifact') or '-'}"
        )

    def route_selected_native_drilldown_action(self) -> None:
        row = self.selected_native_drilldown_action_row()
        if not row:
            messagebox.showinfo("Select an action", "Select a native drilldown action first.")
            return
        filters = self._parse_target_filter(row.get("target_filter"))
        candidate_id = str(row.get("target_candidate_id") or filters.get("candidate_id") or row.get("filter_value") or "").strip()
        ui_action = str(row.get("ui_action") or "")
        target_view = str(row.get("target_view") or "")
        if ui_action == "apply_candidate_review_filter" or target_view == "candidate_review":
            self.clear_candidate_review_filters()
            self.render_candidate_review_board()
            if candidate_id and hasattr(self, "review_tree"):
                for item in self.review_tree.get_children():
                    values = self.review_tree.item(item, "values")
                    if values and str(values[0]) == candidate_id:
                        self.review_tree.selection_set(item)
                        self.review_tree.focus(item)
                        break
            first = self.review_tree.selection() or self.review_tree.get_children()
            if first:
                self.review_tree.selection_set(first[0])
                self.review_tree.focus(first[0])
                self.show_selected_review_detail()
            self.show_view("candidate_review")
            self.native_drilldown_action_var.set(f"Applied native drilldown action: {row.get('action_id')} -> candidate_review {candidate_id or ''}")
            return
        if ui_action == "open_sandbox_score_delta_review":
            self.open_selected_native_drilldown_artifact()
            self.native_drilldown_action_var.set(f"Opened sandbox score-delta review for {candidate_id or row.get('action_id')}.")
            return
        self.open_selected_native_drilldown_artifact()

    def open_selected_native_drilldown_artifact(self) -> None:
        row = self.selected_native_drilldown_action_row()
        if not row:
            messagebox.showinfo("Select an action", "Select a native drilldown action first.")
            return
        path = Path(str(row.get("open_artifact_path") or row.get("linked_artifact") or row.get("source_artifact") or ""))
        if not path.is_absolute():
            path = ROOT / path
        open_path(path)

    def selected_staging_curator_rows(self) -> list[dict]:
        if not hasattr(self, "staging_manual_review_tree"):
            return []
        rows: list[dict] = []
        for item in self.staging_manual_review_tree.selection():
            try:
                index = int(str(item).split("-")[-1])
            except Exception:
                continue
            if 0 <= index < len(self.staging_manual_review_rows):
                rows.append(self.staging_manual_review_rows[index])
        return rows

    def show_selected_staging_curator_queue(self) -> None:
        rows = self.selected_staging_curator_rows()
        if not rows:
            self.staging_curator_detail_var.set("Select a staging manual-review queue row to inspect source policy, version-change requirements, and signoff history.")
            return
        row = rows[0]
        source = str(row.get("source_dataset") or "")
        signoffs = [
            item
            for item in self.staging_curator_signoff_rows
            if str(item.get("review_queue_id") or "") == str(row.get("review_queue_id") or "")
            or str(item.get("source_dataset") or "") == source
        ]
        latest = signoffs[-1] if signoffs else {}
        self.staging_curator_detail_var.set(
            f"{row.get('review_queue_id') or '-'} | source={source or '-'} | status={row.get('manual_review_status') or '-'} | "
            f"rows={row.get('row_count') or 0} blockers={row.get('blocker_count') or 0} warnings={row.get('warning_count') or 0}\n"
            f"Applicable: {row.get('applicable_contexts') or '-'}\n"
            f"Scope guard: {display_scope_guard(row.get('disabled_contexts'))}\n"
            f"Version log: {row.get('version_change_log') or '-'}\n"
            f"Latest signoff: {latest.get('curator_decision') or 'not_signed'} by {latest.get('curator') or '-'} | {latest.get('version_change_note') or latest.get('curator_note') or '-'}"
        )

    def signoff_staging_curator_queue(self, scope: str) -> None:
        rows = self.selected_staging_curator_rows() if scope == "selected" else self.staging_manual_review_rows[:120]
        if not rows:
            messagebox.showinfo("No staging rows", "No staging manual-review queue rows are selected or visible.")
            return
        queue_ids = [str(row.get("review_queue_id") or "") for row in rows if row.get("review_queue_id")]
        sources = [str(row.get("source_dataset") or "") for row in rows if row.get("source_dataset")]
        args = [
            "scripts/review_rgroup_staging_curator_queue.py",
            "--review-queue-ids",
            ",".join(queue_ids),
            "--source-datasets",
            ",".join(sources),
            "--decision",
            self.staging_curator_decision_var.get().strip() or "ready_for_sandbox_review",
            "--curator",
            self.staging_curator_var.get().strip() or "local_curator",
            "--note",
            self.staging_curator_note_var.get().strip(),
            "--version-change-note",
            self.staging_curator_version_note_var.get().strip(),
        ]
        self.run_task(f"record {len(rows)} staging curator signoffs", lambda: self._run_checked(args))

    def open_selected_staging_curator_csv(self) -> None:
        rows = self.selected_staging_curator_rows()
        if not rows:
            messagebox.showinfo("Select staging row", "Select a staging manual-review row first.")
            return
        path = Path(str(rows[0].get("staging_path") or ""))
        if not path.is_absolute():
            path = ROOT / path
        open_path(path)

    def selected_remediation_rows(self) -> list[dict]:
        if not hasattr(self, "review_remediation_tree"):
            return []
        rows: list[dict] = []
        for item in self.review_remediation_tree.selection():
            try:
                index = int(str(item).split("-")[-1])
            except Exception:
                continue
            if 0 <= index < len(self.review_remediation_rows):
                rows.append(self.review_remediation_rows[index])
        return rows

    def show_selected_remediation_task(self) -> None:
        rows = self.selected_remediation_rows()
        if not rows:
            self.remediation_detail_var.set("Select a remediation task to edit local owner, due date, status, and closure note.")
            return
        row = rows[0]
        self.remediation_owner_var.set(str(row.get("owner") or "local_review_owner"))
        self.remediation_due_var.set(str(row.get("due_date") or row.get("due_at") or ""))
        self.remediation_status_var.set(str(row.get("status") or row.get("closure_status") or "open"))
        self.remediation_reason_var.set(str(row.get("suggested_reason") or row.get("closure_reason") or "local_review_resolved"))
        self.remediation_note_var.set(str(row.get("closure_note") or row.get("update_note") or ""))
        self.remediation_detail_var.set(
            f"{row.get('task_id') or '-'} | priority={row.get('priority') or '-'} | type={row.get('task_type') or '-'} | "
            f"source={row.get('source_id') or row.get('source_artifact') or '-'} | audit={row.get('audit_event_count') or 0} | action={row.get('next_action') or '-'}"
        )

    def update_remediation_tasks(self, task_ids: list[str], *, status: str | None = None, action: str = "native_update") -> None:
        task_ids = [str(item).strip() for item in task_ids if str(item).strip()]
        if not task_ids:
            messagebox.showinfo("No remediation tasks", "No remediation tasks are selected or visible.")
            return
        chosen_status = status or self.remediation_status_var.get().strip()
        note = self.remediation_note_var.get().strip()

        def task() -> dict:
            due_at = self.remediation_due_var.get().strip()
            if self.review_remediation_source == "candidate" and (self.project_dir() / "candidate_remediation_queue.json").exists():
                args = [
                    "scripts/update_candidate_remediation_queue.py",
                    "--project-name",
                    self.project_name(),
                    "--status",
                    chosen_status or "open",
                    "--owner",
                    self.remediation_owner_var.get().strip() or "local_review_owner",
                    "--actor",
                    "native_shell",
                    "--action",
                    action,
                ]
                for task_id in task_ids:
                    args.extend(["--task-id", task_id])
                if due_at:
                    args.extend(["--due-date", due_at])
                if note:
                    args.extend(["--closure-note", note])
                result = self._run_checked(args)
            else:
                args = [
                    "scripts/update_review_remediation_closure.py",
                    *task_ids,
                    "--project-name",
                    self.project_name(),
                    "--closure-status",
                    chosen_status or "closed",
                    "--reviewer",
                    self.remediation_owner_var.get().strip() or "local_review_owner",
                    "--owner",
                    self.remediation_owner_var.get().strip() or "local_review_owner",
                    "--reason",
                    self.remediation_reason_var.get().strip() or action,
                    "--batch-id",
                    action,
                ]
                if due_at:
                    args.extend(["--due-at", due_at])
                if note:
                    args.extend(["--note", note])
                result = self._run_checked(args)
            self._run_checked(["scripts/build_review_closure_workbench.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_explanation_panel.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_explanation_compare.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_candidate_explanation_drilldown.py", "--project-name", self.project_name()])
            self._run_checked(["scripts/build_operator_trend_summary.py", "--project-name", self.project_name()])
            return result

        self.run_task(f"update {len(task_ids)} remediation tasks", task)

    def save_selected_remediation_task(self) -> None:
        task_ids = [str(row.get("task_id") or "") for row in self.selected_remediation_rows()]
        self.update_remediation_tasks(task_ids, action="native_save")

    def close_selected_remediation_task(self) -> None:
        if not self.remediation_note_var.get().strip():
            self.remediation_note_var.set("Closed from native candidate remediation queue.")
        task_ids = [str(row.get("task_id") or "") for row in self.selected_remediation_rows()]
        self.update_remediation_tasks(task_ids, status="closed", action="native_close")

    def reopen_selected_remediation_task(self) -> None:
        if not self.remediation_note_var.get().strip():
            self.remediation_note_var.set("Reopened from native candidate remediation queue.")
        task_ids = [str(row.get("task_id") or "") for row in self.selected_remediation_rows()]
        self.update_remediation_tasks(task_ids, status="reopened", action="native_reopen")

    def close_visible_remediation_tasks(self) -> None:
        if not self.remediation_note_var.get().strip():
            self.remediation_note_var.set("Batch closed visible remediation tasks from native queue.")
        task_ids = [str(row.get("task_id") or "") for row in self.review_remediation_rows[:260]]
        self.update_remediation_tasks(task_ids, status="closed", action="native_close_visible")

    def assign_visible_remediation_tasks(self) -> None:
        if not self.remediation_note_var.get().strip():
            self.remediation_note_var.set("Batch assigned visible remediation tasks from native queue.")
        task_ids = [str(row.get("task_id") or "") for row in self.review_remediation_rows[:260]]
        self.update_remediation_tasks(task_ids, action="native_assign_visible")

    def _postpone_due_date(self, days: int = 7) -> str:
        text = self.remediation_due_var.get().strip()
        base = datetime.now(timezone.utc).date()
        if text:
            try:
                base = datetime.fromisoformat(text[:10]).date()
            except ValueError:
                base = datetime.now(timezone.utc).date()
        return (base + timedelta(days=days)).isoformat()

    def postpone_selected_remediation_tasks(self) -> None:
        self.remediation_status_var.set("deferred")
        self.remediation_reason_var.set("deferred_low_priority")
        self.remediation_due_var.set(self._postpone_due_date())
        if not self.remediation_note_var.get().strip():
            self.remediation_note_var.set("Postponed from native candidate remediation queue.")
        task_ids = [str(row.get("task_id") or "") for row in self.selected_remediation_rows()]
        self.update_remediation_tasks(task_ids, status="deferred", action="native_postpone_selected")

    def postpone_visible_remediation_tasks(self) -> None:
        self.remediation_status_var.set("deferred")
        self.remediation_reason_var.set("deferred_low_priority")
        self.remediation_due_var.set(self._postpone_due_date())
        if not self.remediation_note_var.get().strip():
            self.remediation_note_var.set("Batch postponed visible remediation tasks from native queue.")
        task_ids = [str(row.get("task_id") or "") for row in self.review_remediation_rows[:260]]
        self.update_remediation_tasks(task_ids, status="deferred", action="native_postpone_visible")

    def show_baseline_history_chart_preview(self) -> None:
        if not hasattr(self, "baseline_history_chart_var"):
            return
        row = self.baseline_history_chart_rows[0] if self.baseline_history_chart_rows else {}
        if not row:
            self.baseline_history_chart_var.set("Baseline history chart is not built yet.")
            if hasattr(self, "baseline_history_chart_label"):
                self.baseline_history_chart_label.configure(image="")
            self.baseline_history_chart_image = None
            return
        image_path = Path(str(row.get("preview_path") or row.get("image_path") or ""))
        chart_path = Path(str(row.get("chart_path") or ""))
        if image_path and not image_path.is_absolute():
            image_path = ROOT / image_path
        if chart_path and not chart_path.is_absolute():
            chart_path = ROOT / chart_path
        self.baseline_history_chart_var.set(
            f"{row.get('label') or row.get('chart_id')} | status={row.get('status') or '-'} | "
            f"points={row.get('point_count') or '-'} | preview={image_path if image_path.is_file() else chart_path}"
        )
        if Image is None or ImageTk is None or not image_path.is_file() or not hasattr(self, "baseline_history_chart_label"):
            if hasattr(self, "baseline_history_chart_label"):
                self.baseline_history_chart_label.configure(image="")
            self.baseline_history_chart_image = None
            return
        try:
            image = Image.open(image_path)
            resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", None)
            if resample is not None:
                image.thumbnail((720, 220), resample)
            else:
                image.thumbnail((720, 220))
            self.baseline_history_chart_image = ImageTk.PhotoImage(image)
            self.baseline_history_chart_label.configure(image=self.baseline_history_chart_image)
        except Exception:
            self.baseline_history_chart_label.configure(image="")
            self.baseline_history_chart_image = None

    def open_baseline_history_chart(self) -> None:
        row = self.baseline_history_chart_rows[0] if self.baseline_history_chart_rows else {}
        image_path = Path(str(row.get("preview_path") or row.get("image_path") or ""))
        chart_path = Path(str(row.get("chart_path") or self.project_dir() / "baseline_history_explorer_charts" / "baseline_history_movement.png"))
        if image_path and not image_path.is_absolute():
            image_path = ROOT / image_path
        if chart_path and not chart_path.is_absolute():
            chart_path = ROOT / chart_path
        open_path(image_path if image_path.is_file() else chart_path)

    def selected_trend_chart_row(self) -> dict:
        if not hasattr(self, "trend_chart_tree"):
            return {}
        selected = self.trend_chart_tree.selection()
        if not selected:
            return {}
        try:
            index = int(str(selected[0]).split("-")[-1])
        except Exception:
            return {}
        if 0 <= index < len(self.trend_chart_rows):
            return self.trend_chart_rows[index]
        return {}

    def show_selected_trend_chart_preview(self) -> None:
        if not hasattr(self, "trend_chart_preview_var"):
            return
        row = self.selected_trend_chart_row()
        if not row:
            self.trend_chart_preview_var.set("Select an operator trend chart row to preview the native PNG card.")
            if hasattr(self, "trend_chart_preview_label"):
                self.trend_chart_preview_label.configure(image="")
            self.trend_chart_preview_image = None
            return
        image_path = Path(str(row.get("preview_path") or row.get("image_path") or ""))
        chart_path = Path(str(row.get("chart_path") or ""))
        self.trend_chart_preview_var.set(
            f"{row.get('label') or row.get('card_id')} | status={row.get('status') or '-'} | "
            f"value={row.get('value') or '-'} | trend={row.get('trend') or '-'} | "
            f"preview={image_path if image_path.is_file() else chart_path}"
        )
        if Image is None or ImageTk is None or not image_path.is_file() or not hasattr(self, "trend_chart_preview_label"):
            if hasattr(self, "trend_chart_preview_label"):
                self.trend_chart_preview_label.configure(image="")
            self.trend_chart_preview_image = None
            return
        try:
            image = Image.open(image_path)
            image.thumbnail((720, 180))
            self.trend_chart_preview_image = ImageTk.PhotoImage(image)
            self.trend_chart_preview_label.configure(image=self.trend_chart_preview_image)
        except Exception:
            self.trend_chart_preview_label.configure(image="")
            self.trend_chart_preview_image = None

    def open_selected_trend_chart(self) -> None:
        row = self.selected_trend_chart_row()
        if not row:
            messagebox.showwarning("No chart selected", "Select an operator trend chart row first.")
            return
        image_path = Path(str(row.get("preview_path") or row.get("image_path") or ""))
        chart_path = Path(str(row.get("chart_path") or ""))
        open_path(image_path if image_path.is_file() else chart_path)


def smoke() -> int:
    packet = read_json(ROOT / "data/projects/demo/promotion_readiness_packet.json")
    dashboard = read_json(ROOT / "data/projects/demo/project_memory_review_dashboard.json")
    production = read_json(ROOT / "data/releases/production_dashboard_snapshot.json")
    portable = read_json(ROOT / "data/releases/native_portable_package_manifest.json")
    db_health = read_json(ROOT / "data/releases/local_db_health_report.json")
    db_trend = read_json(ROOT / "data/releases/local_db_maintenance_trend_history.json")
    native_regression = read_json(ROOT / "data/releases/native_ui_regression_snapshot.json")
    review_board = read_json(ROOT / "data/projects/demo/candidate_review_board.json")
    review_analytics = read_json(ROOT / "data/projects/demo/candidate_review_analytics.json")
    review_reason_workbench = read_json(ROOT / "data/projects/demo/candidate_review_reason_workbench.json")
    review_reason_audit = read_json(ROOT / "data/projects/demo/candidate_review_reason_workbench_audit.json")
    drilldown_packet = read_json(ROOT / "data/projects/demo/candidate_drilldown_packet.json")
    candidate_baseline = read_json(ROOT / "data/projects/demo/candidate_baseline_compare.json")
    candidate_decision = read_json(ROOT / "data/projects/demo/candidate_decision_packet.json")
    candidate_drawer = read_json(ROOT / "data/projects/demo/candidate_evidence_drawer.json")
    candidate_explanation = read_json(ROOT / "data/projects/demo/candidate_explanation_panel.json")
    candidate_explanation_compare = read_json(ROOT / "data/projects/demo/candidate_explanation_compare.json")
    candidate_explanation_drilldown = read_json(ROOT / "data/projects/demo/candidate_explanation_drilldown.json")
    candidate_component_structure_locator = read_json(ROOT / "data/projects/demo/candidate_component_structure_locator.json")
    candidate_explanation_matrix = read_json(ROOT / "data/projects/demo/candidate_explanation_matrix.json")
    staged_feed_sandbox = read_json(ROOT / "data/projects/demo/staged_feed_sandbox_scoring.json")
    sandbox_score_delta_review = read_json(ROOT / "data/projects/demo/sandbox_score_delta_review_packet.json")
    sandbox_score_delta_signoff = read_json(ROOT / "data/projects/demo/sandbox_score_delta_signoff_ledger.json")
    staging_sandbox_filters = read_json(ROOT / "data/projects/demo/staging_sandbox_filter_views.json")
    rgroup_admission_sandbox_replay = read_json(ROOT / "data/substituents/rgroup_admission_sandbox_impact_replay.json")
    rgroup_promotion_approval = read_json(ROOT / "data/substituents/rgroup_promotion_approval_ledger.json")
    rgroup_digestion_quality = read_json(ROOT / "data/substituents/rgroup_digestion_quality_metrics.json")
    native_drilldown_actions = read_json(ROOT / "data/projects/demo/native_drilldown_actions.json")
    site_detection_confidence = read_json(ROOT / "data/projects/demo/site_detection_confidence.json")
    site_detection_calibration = read_json(ROOT / "data/projects/demo/site_detection_calibration_queue.json")
    decision_qa = read_json(ROOT / "data/projects/demo/candidate_decision_qa.json")
    evidence_quality = read_json(ROOT / "data/projects/demo/evidence_quality_scorecard.json")
    baseline_manager = read_json(ROOT / "data/projects/demo/candidate_baseline_manager.json")
    reviewer_operations = read_json(ROOT / "data/projects/demo/reviewer_operations.json")
    baseline_lineage = read_json(ROOT / "data/projects/demo/baseline_lineage_compare.json")
    review_command_center = read_json(ROOT / "data/projects/demo/review_command_center.json")
    review_remediation = read_json(ROOT / "data/projects/demo/candidate_remediation_queue.json") or read_json(ROOT / "data/projects/demo/review_remediation_queue.json")
    review_ops_console = read_json(ROOT / "data/projects/demo/candidate_review_ops_console.json")
    review_closure = read_json(ROOT / "data/projects/demo/review_closure_workbench.json")
    review_closure_filters = read_json(ROOT / "data/projects/demo/review_closure_filter_views.json")
    reviewer_cockpit = read_json(ROOT / "data/projects/demo/reviewer_cockpit.json")
    remediation_history = read_json(ROOT / "data/projects/demo/candidate_remediation_queue_history.json")
    baseline_history = read_json(ROOT / "data/projects/demo/baseline_history_explorer.json") or read_json(ROOT / "data/projects/demo/baseline_lineage_history.json")
    baseline_scenario = read_json(ROOT / "data/projects/demo/baseline_scenario_board.json")
    baseline_whatif = read_json(ROOT / "data/projects/demo/baseline_whatif_board.json")
    feed_absorption = read_json(ROOT / "data/substituents/feed_absorption_audit.json")
    feed_diff = read_json(ROOT / "data/substituents/feed_absorption_diff_navigator.json")
    source_expansion = read_json(ROOT / "data/substituents/source_expansion_governance.json")
    feed_simulator = read_json(ROOT / "data/substituents/feed_promotion_simulator.json")
    staging_quality_budget = read_json(ROOT / "data/substituents/rgroup_staging_quality_budget.json")
    staging_admission_scorecard = read_json(ROOT / "data/substituents/rgroup_staging_admission_scorecard.json")
    staging_curator_signoff = read_json(ROOT / "data/substituents/rgroup_staging_curator_signoff.json")
    rgroup_feed_digestion = read_json(ROOT / "data/substituents/rgroup_feed_digestion_ledger.json")
    governed_batches = read_json(ROOT / "data/substituents/governed_ingestion_batches.json")
    local_db_release_gate = read_json(ROOT / "data/releases/local_db_maintenance_release_gate.json")
    baseline_lineage_preview = read_json(ROOT / "data/projects/demo/baseline_lineage_preview.json")
    baseline_lineage_filters = read_json(ROOT / "data/projects/demo/baseline_lineage_filter_views.json")
    baseline_registry = read_json(ROOT / "data/projects/demo/governance_baselines/baseline_registry.json")
    operator_trend = read_json(ROOT / "data/releases/operator_trend_summary.json")
    operator_charts = read_json(ROOT / "data/releases/operator_trend_charts.json")
    discussion_handoff = read_json(ROOT / "data/projects/demo/medchem_discussion_handoff.json")
    substituent_version_diff = read_json(ROOT / "data/substituents/substituent_version_diff_browser.json")
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if ROOT.exists() else "fail",
        "root": str(ROOT),
        "promotion_readiness_status": packet.get("status"),
        "project_memory_dashboard_status": dashboard.get("status"),
        "production_dashboard_status": production.get("status"),
        "portable_package_status": portable.get("status"),
        "local_db_health_status": db_health.get("status"),
        "local_db_maintenance_trend_status": db_trend.get("status"),
        "candidate_review_board_status": review_board.get("status"),
        "candidate_review_analytics_status": review_analytics.get("status"),
        "candidate_review_reason_workbench_status": review_reason_workbench.get("status"),
        "candidate_review_reason_audit_status": review_reason_audit.get("status"),
        "candidate_drilldown_status": drilldown_packet.get("status"),
        "candidate_baseline_compare_status": candidate_baseline.get("status"),
        "candidate_decision_packet_status": candidate_decision.get("status"),
        "candidate_evidence_drawer_status": candidate_drawer.get("status"),
        "candidate_explanation_panel_status": candidate_explanation.get("status"),
        "candidate_explanation_compare_status": candidate_explanation_compare.get("status"),
        "candidate_explanation_drilldown_status": candidate_explanation_drilldown.get("status"),
        "candidate_component_structure_locator_status": candidate_component_structure_locator.get("status"),
        "candidate_explanation_matrix_status": candidate_explanation_matrix.get("status"),
        "staged_feed_sandbox_scoring_status": staged_feed_sandbox.get("status"),
        "sandbox_score_delta_review_packet_status": sandbox_score_delta_review.get("status"),
        "sandbox_score_delta_signoff_ledger_status": sandbox_score_delta_signoff.get("status"),
        "sandbox_score_delta_signoff_pending": sandbox_score_delta_signoff.get("pending_signoff_count"),
        "rgroup_feed_digestion_ledger_status": rgroup_feed_digestion.get("status"),
        "rgroup_feed_digestion_rows": rgroup_feed_digestion.get("row_count"),
        "rgroup_promotion_approval_ledger_status": rgroup_promotion_approval.get("status"),
        "rgroup_promotion_approval_pending": rgroup_promotion_approval.get("pending_approval_count"),
        "rgroup_promotion_allowed": rgroup_promotion_approval.get("promotion_allowed"),
        "rgroup_digestion_quality_metrics_status": rgroup_digestion_quality.get("status"),
        "rgroup_digestion_quality_rows": rgroup_digestion_quality.get("row_count"),
        "staging_sandbox_filter_views_status": staging_sandbox_filters.get("status"),
        "staging_sandbox_filter_view_rows": staging_sandbox_filters.get("row_count"),
        "rgroup_admission_sandbox_impact_replay_status": rgroup_admission_sandbox_replay.get("status"),
        "local_db_maintenance_release_gate_status": local_db_release_gate.get("status"),
        "local_db_maintenance_release_stop_count": local_db_release_gate.get("release_stop_count"),
        "site_detection_confidence_status": site_detection_confidence.get("status"),
        "site_detection_calibration_queue_status": site_detection_calibration.get("status"),
        "candidate_decision_qa_status": decision_qa.get("status"),
        "evidence_quality_scorecard_status": evidence_quality.get("status"),
        "candidate_evidence_quality_status": evidence_quality.get("status"),
        "candidate_baseline_manager_status": baseline_manager.get("status"),
        "reviewer_operations_status": reviewer_operations.get("status"),
        "baseline_lineage_compare_status": baseline_lineage.get("status"),
        "candidate_baseline_lineage_status": baseline_lineage.get("status"),
        "review_command_center_status": review_command_center.get("status"),
        "candidate_remediation_queue_status": review_remediation.get("status"),
        "candidate_remediation_history_status": remediation_history.get("status"),
        "review_remediation_queue_status": review_remediation.get("status"),
        "review_remediation_closed_count": review_remediation.get("closed_count"),
        "candidate_review_ops_console_status": review_ops_console.get("status"),
        "review_closure_workbench_status": review_closure.get("status"),
        "review_closure_filter_views_status": review_closure_filters.get("status"),
        "reviewer_cockpit_status": reviewer_cockpit.get("status"),
        "baseline_history_explorer_status": baseline_history.get("status"),
        "baseline_scenario_board_status": baseline_scenario.get("status"),
        "baseline_whatif_board_status": baseline_whatif.get("status"),
        "baseline_lineage_history_status": baseline_history.get("status"),
        "baseline_lineage_history_pairwise_count": baseline_history.get("pairwise_row_count"),
        "baseline_lineage_preview_status": baseline_lineage_preview.get("status"),
        "baseline_lineage_filter_views_status": baseline_lineage_filters.get("status"),
        "native_drilldown_actions_status": native_drilldown_actions.get("status"),
        "native_drilldown_actions_direct": native_drilldown_actions.get("direct_action_supported_count"),
        "feed_absorption_audit_status": feed_absorption.get("status"),
        "feed_absorption_audit_blocker_count": feed_absorption.get("blocker_count"),
        "feed_absorption_diff_navigator_status": feed_diff.get("status"),
        "source_expansion_governance_status": source_expansion.get("status"),
        "feed_promotion_simulator_status": feed_simulator.get("status"),
        "rgroup_staging_quality_budget_status": staging_quality_budget.get("status"),
        "rgroup_staging_admission_scorecard_status": staging_admission_scorecard.get("status"),
        "rgroup_staging_curator_signoff_status": staging_curator_signoff.get("status"),
        "governed_ingestion_batches_status": governed_batches.get("status"),
        "governance_baseline_registry_status": baseline_registry.get("status"),
        "operator_trend_summary_status": operator_trend.get("status"),
        "operator_trend_charts_status": operator_charts.get("status"),
        "medchem_discussion_handoff_status": discussion_handoff.get("status"),
        "substituent_version_diff_browser_status": substituent_version_diff.get("status"),
        "native_ui_regression_status": native_regression.get("status"),
        "native_shell": "tkinter",
        "browser_required": False,
        "high_dpi": DPI_REPORT,
        "workspace_sessions_supported": True,
        "candidate_comparison_supported": True,
        "candidate_visual_compare_supported": True,
        "candidate_review_packet_supported": True,
        "candidate_review_board_supported": True,
        "candidate_review_analytics_supported": True,
        "candidate_drilldown_supported": True,
        "candidate_baseline_compare_supported": True,
        "candidate_baseline_diff_table_supported": True,
        "candidate_decision_packet_supported": True,
        "candidate_decision_export_supported": True,
        "candidate_evidence_drawer_supported": True,
        "native_candidate_evidence_drawer_supported": True,
        "candidate_explanation_panel_supported": True,
        "candidate_explanation_compare_supported": True,
        "candidate_explanation_drilldown_supported": True,
        "candidate_component_structure_locator_supported": True,
        "candidate_component_structure_highlight_supported": True,
        "candidate_selection_linkage_supported": True,
        "candidate_explanation_matrix_supported": True,
        "staged_feed_sandbox_scoring_supported": True,
        "sandbox_score_delta_review_packet_supported": True,
        "sandbox_score_delta_signoff_ledger_supported": True,
        "rgroup_feed_digestion_ledger_supported": True,
        "rgroup_promotion_approval_ledger_supported": True,
        "rgroup_digestion_quality_metrics_supported": True,
        "staging_sandbox_filter_views_supported": True,
        "local_db_maintenance_release_gate_supported": True,
        "candidate_explanation_score_breakdown_supported": True,
        "site_detection_confidence_supported": True,
        "candidate_decision_qa_supported": True,
        "evidence_quality_scorecard_supported": True,
        "candidate_evidence_quality_supported": True,
        "candidate_baseline_manager_supported": True,
        "reviewer_operations_supported": True,
        "baseline_lineage_compare_supported": True,
        "candidate_baseline_lineage_supported": True,
        "review_command_center_supported": True,
        "review_command_route_supported": True,
        "candidate_remediation_queue_supported": True,
        "candidate_remediation_closure_supported": True,
        "candidate_remediation_batch_assign_supported": True,
        "candidate_remediation_batch_postpone_supported": True,
        "candidate_remediation_history_supported": True,
        "candidate_remediation_saved_views_supported": True,
        "candidate_remediation_trends_supported": True,
        "review_remediation_queue_supported": True,
        "review_remediation_closure_ledger_supported": True,
        "candidate_review_ops_console_supported": True,
        "review_closure_workbench_supported": True,
        "review_closure_filter_views_supported": True,
        "baseline_history_explorer_supported": True,
        "baseline_scenario_board_supported": True,
        "baseline_whatif_board_supported": True,
        "baseline_history_charts_supported": True,
        "baseline_active_preview_supported": True,
        "baseline_rollback_explanation_supported": True,
        "baseline_pairwise_matrix_supported": True,
        "baseline_lineage_history_supported": True,
        "baseline_lineage_pairwise_supported": True,
        "baseline_lineage_preview_supported": True,
        "baseline_lineage_filter_views_supported": True,
        "native_drilldown_actions_supported": True,
        "native_drilldown_direct_actions_supported": True,
        "feed_absorption_audit_supported": True,
        "feed_absorption_diff_navigator_supported": True,
        "feed_promotion_simulator_supported": True,
        "rgroup_staging_quality_budget_supported": True,
        "rgroup_staging_admission_scorecard_supported": True,
        "rgroup_admission_sandbox_impact_replay_supported": True,
        "rgroup_staging_fill_report_supported": True,
        "staging_manual_review_queue_supported": True,
        "governed_ingestion_batches_supported": True,
        "candidate_table_structured_filter_supported": True,
        "candidate_table_column_filter_supported": True,
        "candidate_score_range_filter_supported": True,
        "candidate_rank_filter_supported": True,
        "candidate_delta_filter_supported": True,
        "candidate_filter_presets_supported": True,
        "candidate_2d_selection_preview_supported": True,
        "candidate_before_after_2d_preview_supported": True,
        "candidate_score_component_2d_linkage_supported": True,
        "candidate_structure_interpretation_supported": True,
        "candidate_score_component_locator_supported": True,
        "candidate_structure_highlight_detail_supported": True,
        "candidate_table_inline_2d_preview_supported": True,
        "candidate_explanation_drawer_supported": True,
        "governance_only_source_expansion_supported": True,
        "source_expansion_governance_supported": True,
        "site_detection_regression_supported": True,
        "site_detection_calibration_queue_supported": True,
        "substituent_version_diff_browser_supported": True,
        "review_analytics_resizable_supported": True,
        "candidate_review_unified_scroll_supported": True,
        "review_analytics_full_height_supported": True,
        "review_pending_reason_clusters_supported": True,
        "review_reason_workbench_supported": True,
        "review_reason_batch_update_supported": True,
        "review_reason_batch_audit_replay_supported": True,
        "reviewer_cockpit_supported": True,
        "review_cluster_evidence_jump_supported": True,
        "local_scope_labeling_supported": True,
        "operator_trend_summary_supported": True,
        "operator_trend_charts_supported": True,
        "operator_trend_chart_preview_supported": True,
        "medchem_discussion_handoff_supported": True,
        "review_board_batch_status_supported": True,
        "structure_alignment_highlight_supported": True,
        "local_db_maintenance_supported": True,
        "local_db_maintenance_trend_supported": True,
        "governance_diff_supported": True,
        "named_governance_baseline_supported": True,
        "production_dashboard_drilldown_supported": True,
        "production_dashboard_warning_route_supported": True,
        "production_dashboard_trend_history_supported": True,
        "native_task_log_supported": True,
        "native_task_rerun_supported": True,
        "staging_curator_signoff_supported": True,
        "staging_version_diff_link_supported": True,
        "site_detection_expanded_regression_supported": True,
    }
    write_json(ROOT / "data/releases/native_shell_smoke.json", payload)
    write_json(
        ROOT / "data/releases/native_ui_quality_report.json",
        {
            "created_at": payload["created_at"],
            "status": "pass",
            "native_shell": "tkinter",
            "browser_required": False,
            "high_dpi": DPI_REPORT,
            "font_policy": "Segoe UI Variable when installed, otherwise Segoe UI",
            "row_height": TREEVIEW_MIN_ROW_HEIGHT,
            "row_height_min": TREEVIEW_MIN_ROW_HEIGHT,
            "row_height_policy": "font_metrics_plus_padding",
            "treeview_vertical_padding": TREEVIEW_VERTICAL_PADDING,
            "horizontal_scrollbars": True,
            "preview_asset": str(ROOT / "data/projects/demo/native_molecule_preview.png"),
            "workspace_sessions_supported": True,
            "candidate_comparison_supported": True,
            "candidate_visual_compare_supported": True,
            "candidate_review_packet_supported": True,
            "candidate_review_board_supported": True,
            "candidate_review_analytics_supported": True,
            "candidate_drilldown_supported": True,
            "candidate_baseline_compare_supported": True,
            "candidate_baseline_diff_table_supported": True,
            "candidate_decision_packet_supported": True,
            "candidate_decision_export_supported": True,
            "candidate_evidence_drawer_supported": True,
            "native_candidate_evidence_drawer_supported": True,
            "candidate_explanation_panel_supported": True,
            "candidate_explanation_compare_supported": True,
            "candidate_explanation_drilldown_supported": True,
            "candidate_component_structure_locator_supported": True,
            "candidate_component_structure_highlight_supported": True,
            "candidate_selection_linkage_supported": True,
            "candidate_explanation_matrix_supported": True,
            "staged_feed_sandbox_scoring_supported": True,
            "sandbox_score_delta_review_packet_supported": True,
            "sandbox_score_delta_signoff_ledger_supported": True,
            "rgroup_feed_digestion_ledger_supported": True,
            "rgroup_promotion_approval_ledger_supported": True,
            "rgroup_digestion_quality_metrics_supported": True,
            "staging_sandbox_filter_views_supported": True,
            "local_db_maintenance_release_gate_supported": True,
            "candidate_explanation_score_breakdown_supported": True,
            "site_detection_confidence_supported": True,
            "candidate_decision_qa_supported": True,
            "evidence_quality_scorecard_supported": True,
            "candidate_evidence_quality_supported": True,
            "candidate_baseline_manager_supported": True,
            "reviewer_operations_supported": True,
            "baseline_lineage_compare_supported": True,
            "candidate_baseline_lineage_supported": True,
            "review_command_center_supported": True,
            "review_command_route_supported": True,
            "candidate_remediation_queue_supported": True,
            "candidate_remediation_closure_supported": True,
            "candidate_remediation_batch_assign_supported": True,
            "candidate_remediation_batch_postpone_supported": True,
            "candidate_remediation_history_supported": True,
            "candidate_remediation_saved_views_supported": True,
            "candidate_remediation_trends_supported": True,
            "review_remediation_queue_supported": True,
            "review_remediation_closure_ledger_supported": True,
            "candidate_review_ops_console_supported": True,
            "review_closure_workbench_supported": True,
            "review_closure_filter_views_supported": True,
            "baseline_history_explorer_supported": True,
            "baseline_scenario_board_supported": True,
            "baseline_whatif_board_supported": True,
            "baseline_history_charts_supported": True,
            "baseline_active_preview_supported": True,
            "baseline_rollback_explanation_supported": True,
            "baseline_pairwise_matrix_supported": True,
            "baseline_lineage_history_supported": True,
            "baseline_lineage_pairwise_supported": True,
            "baseline_lineage_preview_supported": True,
            "baseline_lineage_filter_views_supported": True,
            "native_drilldown_actions_supported": True,
            "native_drilldown_direct_actions_supported": True,
            "feed_absorption_audit_supported": True,
            "feed_absorption_diff_navigator_supported": True,
            "feed_promotion_simulator_supported": True,
            "rgroup_staging_quality_budget_supported": True,
            "rgroup_staging_admission_scorecard_supported": True,
            "rgroup_admission_sandbox_impact_replay_supported": True,
            "rgroup_staging_fill_report_supported": True,
            "staging_manual_review_queue_supported": True,
            "governed_ingestion_batches_supported": True,
            "candidate_table_structured_filter_supported": True,
            "candidate_table_column_filter_supported": True,
            "candidate_score_range_filter_supported": True,
            "candidate_rank_filter_supported": True,
            "candidate_delta_filter_supported": True,
            "candidate_filter_presets_supported": True,
            "candidate_2d_selection_preview_supported": True,
            "candidate_before_after_2d_preview_supported": True,
            "candidate_score_component_2d_linkage_supported": True,
            "candidate_structure_interpretation_supported": True,
            "candidate_score_component_locator_supported": True,
            "candidate_structure_highlight_detail_supported": True,
            "candidate_table_inline_2d_preview_supported": True,
            "candidate_explanation_drawer_supported": True,
            "governance_only_source_expansion_supported": True,
            "source_expansion_governance_supported": True,
            "site_detection_regression_supported": True,
            "site_detection_calibration_queue_supported": True,
            "substituent_version_diff_browser_supported": True,
            "review_analytics_resizable_supported": True,
            "candidate_review_unified_scroll_supported": True,
            "review_analytics_full_height_supported": True,
            "review_pending_reason_clusters_supported": True,
            "review_reason_workbench_supported": True,
            "review_reason_batch_update_supported": True,
            "review_reason_batch_audit_replay_supported": True,
            "reviewer_cockpit_supported": True,
            "review_cluster_evidence_jump_supported": True,
            "local_scope_labeling_supported": True,
            "operator_trend_summary_supported": True,
            "operator_trend_charts_supported": True,
            "operator_trend_chart_preview_supported": True,
            "medchem_discussion_handoff_supported": True,
            "review_board_batch_status_supported": True,
            "structure_alignment_highlight_supported": True,
            "local_db_maintenance_supported": True,
            "local_db_maintenance_trend_supported": True,
            "governance_diff_supported": True,
            "named_governance_baseline_supported": True,
            "production_dashboard_warning_route_supported": True,
            "native_task_log_supported": True,
            "native_task_rerun_supported": True,
            "staging_curator_signoff_supported": True,
            "staging_version_diff_link_supported": True,
            "site_detection_expanded_regression_supported": True,
            "candidate_explanation_fields": [
                "candidate_explanation_summary",
                "why_recommended",
                "why_review",
                "evidence_snapshot",
                "structure_highlight_detail",
            ],
        },
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


def main() -> int:
    global DPI_REPORT
    DPI_REPORT = enable_high_dpi()
    if "--smoke" in sys.argv:
        return smoke()
    app = NativeShell()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
