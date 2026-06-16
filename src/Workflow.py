"""PTXQC report workflow.

A WorkflowManager subclass that wraps the PTXQC R package as a thin subprocess
tool (``src/ptxqc_runner.R``) to reproduce the PTXQC-web R-Shiny app on top of the
OpenMS streamlit-template. The four sections (upload / configure / run / results)
map onto the original app's single-screen flow.
"""

import os
import json
import shutil
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from src.workflow.WorkflowManager import WorkflowManager
from src import ptxqc_config as cfg

# Map the data-type selector to (input-files key, accepted extensions, upload mode).
INPUT_TYPES = {
    "MaxQuant directory": ("txt-files", ["txt", "xml"], "directory"),
    "MaxQuant files": ("txt-files", ["txt", "xml"], "multi"),
    "mzTab file": ("mztab-file", ["mzTab"], "single"),
}

# Advanced-settings widgets: (key, default, label, help). Mirrors PTXQC-web
# app/server.R adv.set1/2/3. Numeric type follows the default's Python type.
NUMBER_WIDGETS = [
    ("id_rate_bad", 20, "ID rate – bad threshold (%)", "MS/MS identification rate below which a Raw file is flagged.", 0, 100),
    ("id_rate_great", 35, "ID rate – great threshold (%)", "MS/MS identification rate above which a Raw file is considered great.", 0, 100),
    ("pg_ratioLabIncThresh", 4, "Protein groups: label incorporation", "Threshold for label incorporation ratio.", None, None),
    ("param_PG_intThresh", 25, "Protein groups: log2-intensity", "Target threshold for protein intensities.", None, None),
    ("param_EV_protThresh", 3500, "Evidence: protein count", "Target threshold for protein counts (also used as the evidence intensity threshold, as in PTXQC-web).", None, None),
    ("param_EV_pepThresh", 15000, "Evidence: peptide count", "Target threshold for peptide counts.", None, None),
    ("param_EV_MatchingTolerance", 0.7, "Evidence: matching time window [min]", "Match-between-runs matching tolerance (MaxQuant parameter).", None, None),
    ("param_EV_PrecursorTolPPM", 20, "Evidence: first search tol [ppm]", "Uncalibrated mass error tolerance (MaxQuant parameter).", None, None),
    ("param_EV_PrecursorOutOfCalSD", 2, "Evidence: out-of-cal warn SD", "Max standard deviation for the uncalibrated mass error distribution [ppm].", None, None),
    ("param_EV_PrecursorTolPPMmainSearch", 4.5, "Evidence: main search tol [ppm]", "Calibrated mass error tolerance (MaxQuant parameter).", None, None),
    ("param_MSMSScans_ionInjThresh", 10, "MS/MS scans: ion injection time [ms]", "Threshold for ion injection time.", None, None),
]


class Workflow(WorkflowManager):
    def __init__(self) -> None:
        super().__init__("PTXQC", st.session_state["workspace"])
        # Replace the OpenMS-specific "method summary" (which shells out to FileFilter
        # and emits OpenMS citation text) with a PTXQC-appropriate one.
        self.ui.export_parameters_markdown = self._method_summary

    # ----- helpers -------------------------------------------------------
    def _pk(self, key: str) -> str:
        """Session-state key the ParameterManager uses for a custom widget."""
        return f"{self.parameter_manager.param_prefix}{key}"

    def _workspaces_root(self) -> Path:
        env = os.environ.get("WORKSPACES_DIR")
        return Path(env) if env else self.workflow_dir.parent.parent

    def _method_summary(self) -> str:
        meta = cfg.get_ptxqc_metadata()
        md = [
            f"QC reports were generated with **PTXQC** (version {meta.get('version', '?')}) "
            "via the [PTXQC web application](https://github.com/cbielow/PTXQC). "
            "Non-default parameters are listed below.\n",
            self.ui.non_default_params_summary(),
        ]
        return "\n".join(md)

    def _gather_files(self, files_dir: Path) -> list[str]:
        """Return absolute paths of input files in a workspace upload dir,
        including in-place (external_files.txt) references that still exist."""
        out: list[str] = []
        if files_dir.exists():
            out += [str(f) for f in files_dir.iterdir() if f.name != "external_files.txt"]
        ext = files_dir / "external_files.txt"
        if ext.exists():
            out += [line.strip() for line in ext.read_text().splitlines()
                    if line.strip() and os.path.exists(line.strip())]
        return out

    # ----- sections ------------------------------------------------------
    def upload(self) -> None:
        self.ui.input_widget(
            "input-type",
            default="MaxQuant directory",
            name="Data type",
            widget_type="selectbox",
            options=list(INPUT_TYPES.keys()),
            reactive=True,
            help="MaxQuant directory: upload a whole txt folder. "
                 "MaxQuant files: upload individual .txt files. "
                 "mzTab file: a single OpenMS .mzTab file.",
        )
        selected = st.session_state.get(self._pk("input-type"), "MaxQuant directory")
        key, ftypes, mode = INPUT_TYPES[selected]

        if mode == "directory":
            st.info(
                "Select your MaxQuant **txt** folder — your browser uploads its files "
                "and only the PTXQC-relevant ones (Evidence, msms, summary, parameters, "
                "proteinGroups, msmsScans, mqpar.xml) are used."
            )
            self.ui.upload_widget(key=key, name="MaxQuant txt folder", file_types=ftypes, directory=True)
        elif mode == "multi":
            self.ui.upload_widget(key=key, name="MaxQuant txt files", file_types=ftypes)
        else:
            self.ui.upload_widget(key=key, name="mzTab file", file_types=ftypes)

    @st.fragment
    def configure(self) -> None:
        meta = cfg.get_ptxqc_metadata()
        if not meta["available"]:
            st.warning(
                "PTXQC (R) is not available in this environment, so the live metric "
                "list and config preview are disabled. Reports will still use sensible "
                "defaults when run in the full (Docker) image."
            )

        use_yaml = st.checkbox(
            "Upload a PTXQC YAML config instead of setting parameters manually",
            key="ptxqc-use-yaml",
        )

        if use_yaml:
            self.ui.upload_widget(key="yaml-config", name="PTXQC YAML config", file_types=["yaml", "yml"])
            return

        st.markdown("##### Advanced settings")
        cols = st.columns(3)
        for i, (key, default, label, help_text, lo, hi) in enumerate(NUMBER_WIDGETS):
            with cols[i % 3]:
                self.ui.input_widget(
                    key, default=default, name=label, help=help_text,
                    widget_type="number", min_value=lo, max_value=hi,
                    step_size=(0.1 if isinstance(default, float) else 1),
                )
        # Match between runs (selectbox)
        self.ui.input_widget(
            "param_evd_mbr", default="auto", name="Evidence: match between runs",
            widget_type="selectbox", options=["yes", "no", "auto"],
            help="Whether match-between-runs should be used (auto = heuristic).",
        )
        # Contaminants free-text (NAME: percent; ...)
        self.ui.input_widget(
            "contaminants", default="MYCOPLASMA: 1", name="Contaminants (NAME: %, ';'-separated)",
            widget_type="text",
            help="Additional contaminants to plot, e.g. 'MYCOPLASMA: 1; ECOLI: 2'. Enter 'no' to disable.",
        )
        # QC metrics (dynamic list from the installed PTXQC version)
        metric_ids = [m["id"] for m in meta["metrics"]]
        if metric_ids:
            self.ui.input_widget(
                "metrics", default=metric_ids, name="Compute metrics",
                widget_type="multiselect", options=metric_ids,
                help="QC metrics to compute. All are enabled by default.",
            )

    def execution(self) -> bool:
        params = self.params
        selected = params.get("input-type", "MaxQuant directory")
        key, _ftypes, mode = INPUT_TYPES[selected]

        in_files = self._gather_files(Path(self.workflow_dir, "input-files", key))
        if not in_files:
            self.logger.log("ERROR: No input files provided.")
            raise RuntimeError("No input files provided.")

        # Stage inputs into the results dir; PTXQC writes its outputs alongside them.
        rundir = Path(self.workflow_dir, "results", "qc-report")
        rundir.mkdir(parents=True, exist_ok=True)
        for f in in_files:
            shutil.copy(f, rundir / Path(f).name)

        # Optional uploaded YAML config overrides the manual settings.
        uploaded_yaml = self._gather_files(Path(self.workflow_dir, "input-files", "yaml-config"))
        uploaded_yaml = uploaded_yaml[0] if uploaded_yaml else None

        contaminants = cfg.parse_contaminants(params.get("contaminants", ""))
        run_cfg = cfg.build_run_config(
            params, params.get("metrics", []), contaminants, uploaded_yaml
        )
        cfg_path = Path(self.workflow_dir, "ptxqc_run_config.json")
        cfg_path.write_text(json.dumps(run_cfg), encoding="utf-8")

        if mode == "single":
            in_arg = str(rundir / Path(in_files[0]).name)
            rtype = "mztab"
        else:
            in_arg = str(rundir)
            rtype = "maxquant"

        size_mb = sum(os.path.getsize(f) for f in in_files) / 1e6

        # Best-effort: update PTXQC to the latest release before generating the report.
        # Runs as its own Rscript process so the `run` below freshly loads the updated
        # version. run_command returns False (never raises) on failure, so a missing
        # network / read-only library just falls through to the installed version.
        self.logger.log("Updating PTXQC to the latest release (Posit PPM)...")
        if not self.executor.run_command(["Rscript", cfg.RUNNER, "update"]):
            self.logger.log("WARNING: PTXQC update failed; using the currently installed version.")

        self.logger.log(f"Generating PTXQC report for {len(in_files)} input file(s) ({selected})...")
        ok = self.executor.run_command(
            ["Rscript", cfg.RUNNER, "run",
             "--config", str(cfg_path), "--in", in_arg, "--type", rtype, "--out", str(rundir)]
        )

        # Read version/error written by the R wrapper (best effort).
        version, error = "unknown", ""
        result_file = rundir / "ptxqc_result.json"
        if result_file.exists():
            try:
                res = json.loads(result_file.read_text())
                version = res.get("version", "unknown")
                error = res.get("error") or ""
            except (ValueError, OSError):
                pass
        if not ok and not error:
            error = "PTXQC createReport failed (see log)."

        # Per-report usage log (parity with PTXQC-web's persisted logfile).
        cfg.append_usage_log(self._workspaces_root(), version, selected, size_mb, error)

        if not ok or error:
            raise RuntimeError(error or "PTXQC createReport failed.")
        return True

    @st.fragment
    def results(self) -> None:
        rundir = Path(self.workflow_dir, "results", "qc-report")
        result_file = rundir / "ptxqc_result.json"
        if not result_file.exists():
            st.info("No report yet. Upload data, configure settings, then run the workflow.")
            return
        try:
            res = json.loads(result_file.read_text())
        except (ValueError, OSError):
            st.error("Could not read the report result. Please re-run the workflow.")
            return

        if res.get("error"):
            st.error(
                f"PTXQC reported an error: {res['error']}\n\n"
                "Please contact the PTXQC authors: https://github.com/cbielow/PTXQC"
            )

        html_path = res.get("html")
        if html_path and Path(html_path).exists():
            report_html = Path(html_path).read_text(encoding="utf-8", errors="replace")
            st.caption(
                "Interactive QC report below. Use **⤢ Open in a new tab** (top-right of the "
                "report) or the **HTML report** download to view it full-screen."
            )
            # The PTXQC report is a self-contained HTML document, so embed it directly.
            # (Streamlit static serving returns text/plain + nosniff for .html, which makes
            # browsers show the source instead of rendering it — both in-page and in a new
            # tab — so a served URL is not usable here.) A small injected button pops the
            # rendered report into a new browser tab via a blob: URL.
            popout = """
<script>
(function () {
  var b = document.createElement('button');
  b.textContent = '⤢ Open in a new tab';
  b.style.cssText = 'position:fixed;top:8px;right:8px;z-index:99999;padding:6px 10px;'
    + 'font:14px sans-serif;cursor:pointer;background:#29379b;color:#fff;'
    + 'border:none;border-radius:6px;';
  b.onclick = function () {
    var blob = new Blob([document.documentElement.outerHTML], {type: 'text/html'});
    window.open(URL.createObjectURL(blob), '_blank');
  };
  document.body.appendChild(b);
})();
</script>
"""
            components.html(report_html + popout, height=900, scrolling=True)

        st.markdown("##### Downloads")
        d_cols = st.columns(4)
        for col, (label, path) in zip(d_cols, [
            ("PDF report", res.get("pdf")),
            ("HTML report", res.get("html")),
            ("YAML config", res.get("yaml")),
            ("Log file", res.get("log")),
        ]):
            if path and Path(path).exists():
                with open(path, "rb") as f:
                    col.download_button(label, f, file_name=Path(path).name, use_container_width=True)

        if st.button("Create new report"):
            shutil.rmtree(rundir, ignore_errors=True)
            st.rerun()
