# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Proteomics Quality Control (PTXQC) WebApp

## What This Is

**This repo is a deployable Streamlit web app — "Proteomics Quality Control" — that generates [PTXQC](https://github.com/cbielow/PTXQC) quality-control reports for mass-spectrometry proteomics data.** A user uploads MaxQuant `txt` output (or an OpenMS `mzTab` file), optionally tunes thresholds, and the app produces an interactive HTML/PDF QC report. It is a port of the original **PTXQC-web** R-Shiny app onto the **OpenMS streamlit-template** framework.

PTXQC itself is an **R package**. This app does not reimplement it — it shells out to R: `src/ptxqc_runner.R` is a thin CLI wrapper around `PTXQC::createReport`, and the Python/Streamlit layer only collects inputs, assembles the config, runs the wrapper as a subprocess, and embeds the resulting report.

### Built on the OpenMS streamlit-template

The app inherits its skeleton from the **OpenMS streamlit-template** — the standard framework for building MS web apps across the OpenMS ecosystem (other apps built from it: quantms-web, umetaflow, FLASHApp). That ancestry is why the repo carries a full generic workflow framework (`src/workflow/`), template task guides (`.claude/skills/`), and deployment machinery (Docker / k8s / apptainer) that this particular app uses only a slice of. When **extending** the app — adding pages, TOPP-tool workflows, Python tools, presets, or visualizations — the template's patterns and skill guides still apply.

### Domain Context (what the app actually processes)

- **Inputs:** MaxQuant `txt` output (the PTXQC-relevant files: `evidence.txt`, `msms.txt`, `summary.txt`, `parameters.txt`, `proteinGroups.txt`, `msmsScans.txt`, `mqpar.xml`) uploaded either as a whole folder or as individual files; **or** a single OpenMS `mzTab` file.
- **Output:** a self-contained PTXQC HTML report (plus PDF, the resolved YAML config, and a log), surfaced for in-page viewing and download.
- **Configuration** mirrors PTXQC-web's advanced settings: ~13 numeric/selection thresholds (ID-rate bands, protein/peptide count targets, mass-error tolerances, match-between-runs, ion-injection time…), a free-text contaminants field (`NAME: percent; …`), and a metric on/off multiselect. Power users can instead upload a full PTXQC **YAML** config that overrides the manual settings.
- **pyOpenMS** is a dependency (the template imports it; `mzTab` is an OpenMS format) but the QC computation is done by PTXQC in R, not by pyOpenMS.

## Repo-Local Task Playbooks — check `.claude/skills/` first

This repo ships **step-by-step guides for common template development tasks** in `.claude/skills/*.md`. They encode the framework's exact conventions (file locations, registration steps, schema rules, deployment specifics). They are written for the generic template — this app currently uses **no** presets and **no** Python tools — but they remain the authoritative way to add those things. **Before doing any of these tasks from scratch, read the matching guide:**

| Task | Guide |
|------|-------|
| Add a new Streamlit page | `.claude/skills/create-page.md` |
| Build a TOPP workflow (WorkflowManager subclass + 4 pages) | `.claude/skills/create-workflow.md` |
| Add a custom Python analysis tool with auto-generated UI | `.claude/skills/add-python-tool.md` |
| Add MS data visualizations (pyopenms-viz / OpenMS-Insight) | `.claude/skills/add-visualization.md` |
| Add/modify parameter presets in `presets.json` | `.claude/skills/add-presets.md` |
| Configure app settings / Dockerfile for a fork | `.claude/skills/configure-app-settings.md` |
| Set up docker-compose deployment | `.claude/skills/configure-docker-compose-deployment.md` |
| Set up Kubernetes (Kustomize) deployment | `.claude/skills/configure-k8s-deployment.md` |

Each guide ends with a checklist. The deployment guides describe an interview-driven flow and define what is *your* job (editing YAML) vs. a human operator's (running `kubectl`).

## Architecture

```
app.py                          # Entry point — registers the 4 PTXQC pages + Info pages via st.Page();
                                #   reveals a hidden "Admin > Logfile" page when ?logfile is in the URL
settings.json                   # App config (name, version, deployment mode, workspaces, threading, analytics).
                                #   Committed as LOCAL mode + "test": true; the Dockerfile flips online_deployment=true
default-parameters.json         # Global widget defaults only: {"image-format": "svg", "controllo": false}.
                                #   PTXQC parameters are workflow-scoped (defined in src/Workflow.py), NOT here
presets.json                    # Empty ({}) — this app ships no presets. (Framework still supports them.)
content/                        # Streamlit pages (one .py per nav entry)
  ptxqc_upload.py               #   PTXQC workflow sections — each just calls wf.show_*_section()
  ptxqc_configure.py
  ptxqc_run.py
  ptxqc_results.py
  help.py, about.py             #   "Info" section pages
  logfile.py                    #   hidden admin page: views the shared PTXQC usage log
src/
  Workflow.py                   # THE app: class Workflow(WorkflowManager) named "PTXQC". Wraps the PTXQC R
                                #   package via `Rscript src/ptxqc_runner.R run ...` (run_command, not run_topp)
  ptxqc_config.py               # Pure-Python helpers (no R knowledge): cached metric/version discovery via
                                #   `ptxqc_runner.R default-config`, contaminants parsing, run-config assembly,
                                #   usage-log read/write. Most functions are Streamlit-free so they run in the RQ worker
  ptxqc_runner.R                # R subprocess wrapper: `default-config` (emit metric list + default YAML) and
                                #   `run` (PTXQC::createReport -> HTML/PDF/YAML/log + a result JSON sidecar)
  common/
    common.py                   # Utilities: page_setup(), save_params(), show_fig(), show_table()
    captcha_.py                 # Captcha gate for online deployments
    admin.py                    # Admin auth + demo-workspace management
  workflow/                     # Generic template workflow framework (inherited)
    WorkflowManager.py          #   Base class: upload/configure/execution/results pattern
    StreamlitUI.py              #   Widget library: upload_widget, input_widget, input_TOPP, input_python, ...
    ParameterManager.py         #   JSON parameter persistence + TOPP .ini generation + preset loading
    CommandExecutor.py          #   Runs subprocesses — TOPP tools, Python scripts, OR arbitrary commands
                                #     (run_command, used here for Rscript) — parallel-capable
    FileManager.py, Logger.py, QueueManager.py, tasks.py, health.py, _log_status.py
hooks/hook-analytics.py         # Build-time analytics patch (run during the Docker build)
utils/                          # digest.py, fasta.py helpers
assets/                         # Images (e.g. BSC.png)
tests/                          # pytest unit/logic tests + an R-side parity check (see Test conventions)
test_gui.py                     # Top-level AppTest GUI test — launches every page; CI runs it with tests/
clean-up-workspaces.py          # Cron-style cleanup of stale workspace directories
docker/entrypoint.sh            # Canonical container entrypoint (copied to /app/entrypoint.sh in the image);
entrypoint.sh                   #   auto-detects a read-only root (apptainer/HPC) and moves runtime state to /tmp
gdpr_consent/                   # GDPR consent Streamlit component (prebuilt JS bundle)
docs/                           # User/developer + deployment docs
k8s/                            # Kustomize: base/ + components/memory-tier-{low,high}/ + overlays/prod/
Dockerfile_simple               # The single shipped image (linux/amd64): pyOpenMS (pip) + R + PTXQC + pandoc
docker-compose.yml              # Standalone deployment config
```

## Key Patterns

### Pages

Every page starts with `page_setup()` (workspace init, sidebar, parameter loading). The PTXQC content pages are deliberately thin — they instantiate the workflow and delegate to it:

```python
from src.common.common import page_setup
from src.Workflow import Workflow

page_setup()
wf = Workflow()
wf.show_execution_section()   # or show_upload_section / show_configure_section / show_results_section
```

Pages are registered in `app.py` under named sidebar sections (the dict key is the section header). The section header here is the app name from `settings.json`. A hidden Admin section is appended only when `?logfile` is in the URL query (parity with PTXQC-web's usage log).

### The PTXQC Workflow (`src/Workflow.py`)

The whole app is one `WorkflowManager` subclass implementing the four template methods. This is the example to copy when changing app behavior:

- `upload()` — a reactive **Data type** selector (`MaxQuant directory` / `MaxQuant files` / `mzTab file`) drives which `self.ui.upload_widget(...)` is shown (folder upload vs. multi-file vs. single).
- `configure()` (`@st.fragment`) — either an "upload a YAML config" path, or the manual advanced-settings grid built from the module-level `NUMBER_WIDGETS` list + a contaminants text field + a metrics multiselect populated from the installed PTXQC version. Degrades gracefully (a warning, defaults only) when R/PTXQC is unavailable.
- `execution()` — gathers inputs, writes a JSON run-config (via `ptxqc_config.build_run_config`), then runs **R**: `self.executor.run_command(["Rscript", cfg.RUNNER, "run", "--config", ..., "--in", ..., "--type", "maxquant"|"mztab", "--out", ...])`. Appends a row to the shared usage log afterward.
- `results()` (`@st.fragment`) — reads the wrapper's `ptxqc_result.json`, embeds the report HTML via `st.components.v1.html(...)` (with an injected "open in new tab" button), and offers PDF/HTML/YAML/log downloads.

Note: this app uses `run_command` (arbitrary subprocess) rather than the template's `run_topp` / `run_python`. The framework supports all three — see `.claude/skills/create-workflow.md` for the `self.file_manager` / `self.executor` / `self.logger` API surface.

### Parameters

Template parameters are tracked via widget keys. `default-parameters.json` holds only the two **global** UI defaults (`image-format`, `controllo`). The PTXQC-specific parameters are **workflow-scoped**: declared with `self.ui.input_widget(key, default=..., widget_type=...)` in `configure()`, persisted by `ParameterManager` under a `param_prefix`, and read back in `execution()` via `self.params`. `ptxqc_config.PARAM_DEFAULTS` provides fallbacks so a report still runs if the user never opens the configure page. Keep `NUMBER_WIDGETS` (in `Workflow.py`) and `PARAM_DEFAULTS` (in `ptxqc_config.py`) in sync.

### R wrapper contract (`src/ptxqc_runner.R`)

Subcommands, all invoked as `Rscript src/ptxqc_runner.R <cmd> ...` from Python. PTXQC is attached **lazily per-subcommand** (`load_ptxqc()`), not at the top of the script, so `update` can (re)install it cleanly:
- `default-config --out <yaml>` → writes the version-correct default YAML and a `<yaml>.json` sidecar (`{version, metrics:[{id,name}]}`). `ptxqc_config.get_ptxqc_metadata()` caches this (via `@st.cache_data`) to populate the UI without hardcoding anything PTXQC-version-specific.
- `run --config <json> --in <path> --type maxquant|mztab --out <dir>` → builds the YAML from the payload, runs `createReport`, and writes outputs + a `ptxqc_result.json` (`{version, html, pdf, yaml, log, error}`).
- `update` → updates **PTXQC and its required dependencies** (`dependencies = NA`) to the latest release from Posit PPM (precompiled jammy binaries, same source as the Docker build), into a **staging library** (`PTXQC_LIB`, default `/tmp/ptxqc-lib`, prepended to `.libPaths()`) — **never overwriting the image's built-in PTXQC**. It first checks PPM and **skips the install when already current** (a cheap version check, not a per-run reinstall); when a newer release exists it installs and then **verifies the staged PTXQC loads** and, if it doesn't, **wipes the stage to auto-revert** to the built-in version, so a bad release can't break reports. `Workflow.execution()` calls this **best-effort before every `run`** (its own Rscript process, so `run` loads the staged-then-verified version, else the built-in); outcomes are logged and the report always proceeds on a loadable version.
- `build-config --config <json> --out <yaml>` → writes the PTXQC config YAML a run would use (preview/download and the R-side parity audit) without running a report.

`ptxqc_config.py` is the only Python that knows the payload shape; it forwards just the keys in `PARAM_KEYS` and reproduces PTXQC-web's coupling (`param_EV_intThresh = param_EV_protThresh`).

### Python Tools & Presets (framework features, not used here)

There is **no `src/python-tools/`** directory and `presets.json` is **empty (`{}`)** — this app uses neither. Both remain first-class template capabilities: wire a Python tool with `self.ui.input_python(...)` / `self.executor.run_python(...)` (see `.claude/skills/add-python-tool.md`), and add presets keyed by the lowercase-hyphenated workflow name (here that would be `ptxqc`) following `.claude/skills/add-presets.md`.

## Configuration & Deployment Modes (`settings.json`)

`settings.json` controls runtime behavior far beyond name/version:

- `online_deployment` — `false` = local mode (single user, direct execution); `true` = hosted mode (multi-user workspaces, captcha gate via `src/common/captcha_.py`, Redis/RQ job queue via `QueueManager`). **The committed file is `false`; `Dockerfile_simple` flips it to `true` at build time (`jq '.online_deployment = true'`).** So the shipped image runs in online/queued mode.
- `test` — committed as `true`; bypasses captcha so `streamlit.testing` AppTest runs (and `test_gui.py`) can drive the app headlessly.
- `enable_workspaces` — per-user workspaces with unique shareable IDs (persistent params + uploaded files). `workspaces_dir` is `..` here (workspaces live beside the app dir).
- `local_data_dir` — when set (the Docker image defaults it to `/mounted-data`), a bind-mounted host directory becomes browsable in the upload widget; selected files are referenced in place via `external_files.txt` (no copy), so the mount can be read-only.
- `demo_workspaces` — seedable read-only example workspaces from `example-data/workspaces/` (the dir ships empty, just a `.gitkeep`).
- `max_threads` — `{local: 4, online: 2}` caps on subprocess parallelism.
- `queue_settings` — RQ job timeout / result TTL for online mode.
- `analytics` — Matomo is enabled (OpenMS Matomo cloud); Google Analytics / Piwik are off. `hooks/hook-analytics.py` patches analytics into the build.

The shared **usage log** (`ptxqc_usage.log`) is written at the workspaces root — outside any single workspace, so the cleanup cron never deletes it — and is viewed via the hidden `?logfile` admin page.

**Deployment paths:** `docker-compose.yml` (standalone), `k8s/` Kustomize overlays (`overlays/prod/` selects a memory-tier component and sets slug/image/ingress; Traefik IngressRoute + Redis + RQ worker + workspace PVC), and apptainer/Singularity SIFs for HPC (the entrypoint auto-switches runtime state to `/tmp` under a read-only root).

## Visualization

The QC report itself is a **self-contained PTXQC HTML document** produced by R and embedded with `st.components.v1.html` — not built from a Python plotting library. (Streamlit's static file serving returns `text/plain` + nosniff for `.html`, so the report is embedded inline rather than linked; a small injected button pops it into a new tab via a `blob:` URL.)

For *additional* MS visualizations you might add, the template's two options are available — though only the first is installed here:

- **pyopenms-viz** (in `requirements.txt`): pandas DataFrame extension — `df.plot.ms_spectrum/peak_map/chromatogram/mobilogram(backend="plotly")`. Use `show_fig()` for consistent display/download. Best for publication-quality plots on small–medium data.
- **OpenMS-Insight** (NOT currently a dependency): Vue.js-backed components (`Table`, `LinePlot`, `Heatmap`, `VolcanoPlot`, `SequenceView`) for large datasets with server-side pagination and cross-component linking via a shared `link_id`. Add it to dependencies first.

See `.claude/skills/add-visualization.md` for the decision table and linking patterns.

## Commands

```bash
# --- Run locally ---
pip install -r requirements.txt
streamlit run app.py
# CAVEAT: local pip install gives pyOpenMS only — it does NOT install R or the PTXQC
# package. ptxqc_config.get_ptxqc_metadata() then reports unavailable and the app
# degrades gracefully (configure page warns; the live metric list is empty; running a
# report fails). For a full run with R + PTXQC, use the Docker image (Dockerfile_simple).

# --- Tests (pytest) ---
# requirements.txt does NOT include the test deps; install them first:
pip install pytest fakeredis
python -m pytest test_gui.py tests/          # full suite as CI runs it (ci.yml)
python -m pytest tests/                       # just the tests/ package
python -m pytest tests/test_ptxqc_config.py::test_parse_contaminants_default   # a single test

# --- Lint (matches the Pylint CI job) ---
pip install pylint
pylint $(git ls-files '*.py') --errors-only \
  --disable=C0103,C0114,C0301,C0411,W0212,W0631,W0602,W1514,W2402,E0401,E1101,F0001,R1732

# --- Docker (the only shipped image; linux/amd64) ---
docker-compose up --build                     # standalone
# Build directly (needs a GitHub token + outbound network for the R/PTXQC install step):
docker build -f Dockerfile_simple --build-arg GITHUB_TOKEN=<token> -t ptxqc:latest .
```

### Test conventions

Three styles live side by side — match the one that fits:

- **GUI tests** (`test_gui.py`) drive each page headlessly with `streamlit.testing.v1.AppTest.from_file(...)`, inject `settings` + a `test` workspace into session state, run, and assert `not app.exception`. The parametrized `test_launch` launches all six pages (the 4 PTXQC pages + help + about) and verifies they render even though **R/PTXQC is absent in CI** (the graceful-degradation contract).
- **Pure-logic unit tests** (`tests/test_ptxqc_config.py`) import `src.ptxqc_config` directly and exercise the R-free helpers: contaminants parser, run-config assembly (incl. the intensity/protein-threshold coupling), usage-log round-trip.
- **Streamlit-mocked unit tests** (`tests/test_parameter_presets.py`) mock `streamlit` in `sys.modules` *before* importing the module under test, so `st.session_state` is a plain dict. Queue/worker tests (`test_queue_manager_cancel.py`) use `fakeredis`. `test_workflow_manager_stop.py` and `test_log_status.py` cover workflow control + logging.
- `tests/ptxqc_yaml_parity.R` is an **R-side** parity check (not run by pytest) asserting the generated YAML matches PTXQC-web's.

**CI workflows:**
- `ci.yml` — installs `requirements.txt` + `pytest fakeredis`, runs `python -m pytest test_gui.py tests/` (Ubuntu, Python 3.10 to match the image).
- `pylint.yml` — the lint command above.
- `build-and-test.yml` — validates k8s manifests (kubeconform), builds the **single linux/amd64** `simple` image, health-checks it under **apptainer** (read-only root, host UID, bind-mount contract) then publishes the SIF to GHCR via ORAS, and exercises **kind**-based **nginx** and **Traefik** k8s deploys against both ingress hostnames.
- `ghcr-cleanup.yml` — prunes old GHCR images.

> History note: arm64 multi-arch images and the standalone Windows executable build were intentionally dropped; the repo now ships **one amd64 image**. Don't reintroduce them without a reason.

## Conventions

- Page files go in `content/`, source logic in `src/`.
- Widget keys must match parameter keys (global defaults in `default-parameters.json`; workflow params declared via `input_widget`).
- Workflow names use lowercase with hyphens: `"PTXQC"` -> `ptxqc` (the `presets.json` key and params lookup key).
- Keep `NUMBER_WIDGETS` (`src/Workflow.py`) and `PARAM_DEFAULTS` (`src/ptxqc_config.py`) in sync; the parameter names mirror PTXQC-web's `param$...` keys.
- Use `show_fig()` and `show_table()` from `src/common/common.py` for consistent display.
- Use `@st.fragment` on methods that should partially rerun (`configure`, `results`).
- TOPP tool parameters (if you add a TOPP workflow) use colon-separated paths: `"algorithm:section:param_name"`.
- For repeatable tasks (new page, workflow, tool, preset, deployment), follow the matching `.claude/skills/*.md` guide and its checklist.
```