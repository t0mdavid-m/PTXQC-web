"""
PTXQC configuration helpers (pure Python, no PTXQC/R knowledge).

The heavy lifting (YAML schema, metric enumeration, config assembly) lives in the
R wrapper ``src/ptxqc_runner.R``. This module only:

* runs ``default-config`` once to obtain the version-correct metric list + default
  YAML for the installed PTXQC (so nothing PTXQC-version-specific is hardcoded),
* parses the contaminants free-text field,
* assembles the flat parameter payload handed to the R wrapper, and
* reads/writes the per-report usage log.

Only the metric-list/metadata helper touches Streamlit (for caching); the payload
and usage-log helpers are plain functions so they run inside the RQ worker too.
"""

import os
import glob
import json
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

# Path to the R wrapper, relative to the app root (cwd of streamlit / the worker).
RUNNER = str(Path("src", "ptxqc_runner.R"))


def rscript_path() -> str:
    """Resolve the ``Rscript`` executable to invoke.

    Order: ``PTXQC_RSCRIPT``/``RSCRIPT`` env override → ``Rscript`` on PATH →
    common Windows install locations (the R installer does NOT add R to PATH, so
    a plain local install is otherwise invisible to a subprocess) → bare
    ``"Rscript"`` as a last resort (which then errors clearly if truly absent).
    In Docker/Linux R is on PATH, so this returns the same thing as before.
    """
    for env in ("PTXQC_RSCRIPT", "RSCRIPT"):
        v = os.environ.get(env)
        if v and Path(v).exists():
            return v
    found = shutil.which("Rscript")
    if found:
        return found
    candidates: list[str] = []
    for base in (
        r"C:\Program Files\R",
        r"C:\Program Files\Microsoft\R Open",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\R"),
    ):
        candidates += glob.glob(os.path.join(base, "R-*", "bin", "x64", "Rscript.exe"))
        candidates += glob.glob(os.path.join(base, "R-*", "bin", "Rscript.exe"))
    # Newest version directory first (lexicographic on R-x.y.z is good enough).
    for c in sorted(candidates, reverse=True):
        if os.path.exists(c):
            return c
    return "Rscript"

# The 13 numeric/selection parameters exposed by the original PTXQC-web advanced
# settings. These names match the `param$...` keys consumed by PTXQC's createYaml
# (see PTXQC-web app/server.R build.yaml); the R wrapper maps them into the YAML.
PARAM_KEYS = [
    "id_rate_bad",
    "id_rate_great",
    "pg_ratioLabIncThresh",
    "param_PG_intThresh",
    "param_EV_protThresh",
    "param_EV_intThresh",
    "param_EV_pepThresh",
    "param_EV_MatchingTolerance",
    "param_evd_mbr",
    "param_EV_PrecursorTolPPM",
    "param_EV_PrecursorOutOfCalSD",
    "param_EV_PrecursorTolPPMmainSearch",
    "param_MSMSScans_ionInjThresh",
]

# Fallback defaults so a report runs even if the user never opens the configure
# page. These mirror PTXQC-web's widget defaults (app/server.R). Keep in sync with
# NUMBER_WIDGETS in src/Workflow.py.
PARAM_DEFAULTS = {
    "id_rate_bad": 20,
    "id_rate_great": 35,
    "pg_ratioLabIncThresh": 4,
    "param_PG_intThresh": 25,
    "param_EV_protThresh": 3500,
    "param_EV_intThresh": 3500,
    "param_EV_pepThresh": 15000,
    "param_EV_MatchingTolerance": 0.7,
    "param_evd_mbr": "auto",
    "param_EV_PrecursorTolPPM": 20,
    "param_EV_PrecursorOutOfCalSD": 2,
    "param_EV_PrecursorTolPPMmainSearch": 4.5,
    "param_MSMSScans_ionInjThresh": 10,
}

USAGE_LOG_NAME = "ptxqc_usage.log"
USAGE_LOG_COLUMNS = ["date", "version", "data type", "size MB", "error"]


@st.cache_data(show_spinner=False)
def get_ptxqc_metadata() -> dict:
    """Return ``{"version", "metrics", "default_yaml", "available"}``.

    Runs the R wrapper's ``default-config`` once (cached). ``metrics`` is a list of
    ``{"id", "name"}`` for the installed PTXQC version; ``default_yaml`` is the raw
    bytes of the version-correct default config (offered for download). When R/PTXQC
    is unavailable (e.g. local dev without the image) ``available`` is False and the
    UI degrades gracefully instead of crashing.
    """
    fallback = {"version": "unknown", "metrics": [], "default_yaml": b"", "available": False}
    try:
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tf:
            yaml_path = tf.name
        proc = subprocess.run(
            [rscript_path(), RUNNER, "default-config", "--out", yaml_path],
            capture_output=True, text=True, timeout=120,
        )
        # The metric list / version are read from the sidecar JSON file (not stdout,
        # which carries PTXQC's chatty createYaml progress output).
        meta_path = Path(yaml_path + ".json")
        if proc.returncode != 0 or not meta_path.exists():
            return fallback
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        default_yaml = Path(yaml_path).read_bytes() if Path(yaml_path).exists() else b""
        return {
            "version": meta.get("version", "unknown"),
            "metrics": meta.get("metrics", []),
            "default_yaml": default_yaml,
            "available": True,
        }
    except (OSError, ValueError, subprocess.SubprocessError):
        return fallback


def parse_contaminants(text: str) -> list[dict]:
    """Parse the contaminants free-text field into ``[{"name", "threshold"}, ...]``.

    Mirrors PTXQC-web app/server.R (lines 88-99): a literal ``"no"`` disables
    contaminant plotting; otherwise entries are ``NAME: percent`` separated by ``;``.
    Malformed entries are skipped rather than raising.
    """
    text = (text or "").strip()
    if not text or text.lower() == "no":
        return []
    out: list[dict] = []
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        name, _, thr = chunk.partition(":")
        name = name.strip()
        thr = thr.strip()
        if not name:
            continue
        try:
            threshold = int(float(thr))
        except ValueError:
            continue
        out.append({"name": name, "threshold": threshold})
    return out


def build_run_config(
    params: dict,
    enabled_metrics: list[str],
    contaminants: list[dict],
    uploaded_yaml: str | None = None,
) -> dict:
    """Assemble the JSON payload handed to ``ptxqc_runner.R run``.

    ``params`` is the workflow parameter dict (values collected by the Streamlit
    widgets). Only the known ``PARAM_KEYS`` are forwarded; missing keys fall back to
    ``PARAM_DEFAULTS``.
    """
    param = {k: params.get(k, PARAM_DEFAULTS[k]) for k in PARAM_KEYS}
    # PTXQC-web sets the evidence intensity threshold from the protein-count widget
    # (app/server.R:107). Reproduce that coupling so generated configs match exactly;
    # there is no separate evidence-intensity widget.
    param["param_EV_intThresh"] = param["param_EV_protThresh"]
    return {
        "metrics": list(enabled_metrics or []),
        "param": param,
        "contaminants": list(contaminants or []),
        "uploaded_yaml": uploaded_yaml,
    }


def usage_log_path(workspaces_root: os.PathLike | str) -> Path:
    """Path of the shared usage log at the workspaces root (outside any workspace,
    so the workspace-cleanup cron never deletes it)."""
    return Path(workspaces_root, USAGE_LOG_NAME)


def append_usage_log(
    workspaces_root: os.PathLike | str,
    version: str,
    data_type: str,
    size_mb: float,
    error: str = "",
) -> None:
    """Append one ``|``-delimited row (date, version, type, size MB, error).

    A single short line written in append mode; on the workspace PVC (RWO block
    storage, single node) such sub-PIPE_BUF appends are atomic, so no lock is needed.
    Failures are swallowed — usage logging must never break report generation.
    """
    row = "|".join([
        date.today().isoformat(),
        str(version),
        str(data_type),
        f"{size_mb:.1f}",
        (error or "").replace("|", "/").replace("\n", " "),
    ])
    try:
        path = usage_log_path(workspaces_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(row + "\n")
    except OSError:
        pass


def read_usage_log(workspaces_root: os.PathLike | str) -> pd.DataFrame:
    """Read the usage log into a DataFrame (empty if missing)."""
    path = usage_log_path(workspaces_root)
    if not path.exists():
        return pd.DataFrame(columns=USAGE_LOG_COLUMNS)
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        parts += [""] * (len(USAGE_LOG_COLUMNS) - len(parts))
        rows.append(parts[: len(USAGE_LOG_COLUMNS)])
    return pd.DataFrame(rows, columns=USAGE_LOG_COLUMNS)
