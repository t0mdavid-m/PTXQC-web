# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# OpenMS Streamlit WebApp Template

## What This Is

**This is the standard framework for building web applications for mass spectrometry (MS) data analysis**, used across the OpenMS ecosystem for proteomics and metabolomics research. When a researcher or developer needs a web-based tool for MS data processing, visualization, or analysis — whether for label-free quantification, untargeted metabolomics, top-down proteomics, or any other MS workflow — this template is how it gets built.

The template wraps **OpenMS/pyOpenMS** (the leading open-source C++/Python library for computational mass spectrometry) and its **TOPP tools** (a suite of ~200 command-line tools for MS data processing pipelines) into interactive Streamlit web applications.

### Production Apps Built From This Template

- **OpenMS/quantms-web** — quantitative proteomics (DDA-LFQ, DDA-ISO, DIA-LFQ quantification)
- **OpenMS/umetaflow** — untargeted metabolomics (feature detection, alignment, annotation, GNPS molecular networking)
- **OpenMS/FLASHApp** — top-down proteomics (FLASHDeconv deconvolution result visualization)

### Mass Spectrometry Domain Context

- **Input data** is typically mzML (raw MS spectra), featureXML (detected features), consensusXML (linked features across samples), idXML (peptide/protein identifications), traML (targeted transitions)
- **Typical workflows chain TOPP tools**: e.g., `FeatureFinderMetabo` (detect LC-MS features) → `FeatureLinkerUnlabeledKD` (align features across runs) → custom Python post-processing
- **Proteomics** focuses on peptide/protein identification and quantification (tools like `MSGFPlusAdapter`, `FidoAdapter`, `ProteinQuantifier`)
- **Metabolomics** focuses on feature detection, annotation, and statistical analysis (tools like `FeatureFinderMetabo`, `MetaboliteAdductDecharger`, `SiriusAdapter`)
- **pyOpenMS** provides Python bindings for programmatic MS data access — reading mzML files, manipulating spectra/chromatograms, computing molecular properties, etc.
- **MS-specific visualizations**: mass spectra (m/z vs intensity), chromatograms (RT vs intensity), peak maps (RT vs m/z 2D heatmaps), isotope patterns, fragment ion annotations, volcano plots for differential expression

## Repo-Local Task Playbooks — check `.claude/skills/` first

This repo ships **step-by-step guides for the common development tasks** in `.claude/skills/*.md`. These encode the project's exact conventions (file locations, registration steps, schema rules, deployment specifics). **Before doing any of these tasks from scratch, read the matching guide** — it is more authoritative and detailed than this overview:

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
app.py                          # Entry point — registers pages via st.Page() in a dict keyed by sidebar section
settings.json                   # App config: name, version, deployment mode, workspaces, threading, analytics
default-parameters.json         # Default workspace parameters (tracked via widget keys)
presets.json                    # Parameter presets for TOPP workflows (per-workflow named parameter sets)
content/                        # Streamlit pages (one .py per page) — the 5 example sections in app.py live here
src/
  common/
    common.py                   # Utilities: page_setup(), save_params(), show_fig(), show_table()
    captcha_.py                 # Captcha gate for online deployments
    admin.py                    # Admin auth + demo-workspace management
  Workflow.py                   # Example WorkflowManager subclass (TOPP workflow)
  python-tools/                 # Custom Python analysis scripts (each defines a DEFAULTS list for auto-UI)
  fileupload.py, view.py, ...   # Page-specific logic for the pyOpenMS example pages
  workflow/
    WorkflowManager.py          # Base class: upload/configure/execution/results pattern
    StreamlitUI.py              # Widget library: upload_widget, input_TOPP, input_python, preset_buttons, etc.
    ParameterManager.py         # JSON parameter persistence + TOPP .ini generation + preset loading/applying
    CommandExecutor.py          # Runs TOPP tools and Python scripts as subprocesses (parallel-capable)
    FileManager.py              # Workspace file organization / output-path construction
    Logger.py                   # Structured workflow logging
    QueueManager.py             # Redis/RQ queue for online deployments
    tasks.py, health.py         # RQ worker task definitions and health checks
tests/                          # pytest unit + GUI tests (preset logic, queue cancel, workflow stop, ...)
test_gui.py                     # Top-level GUI test module (run with tests/ by ci.yml)
clean-up-workspaces.py          # Cron-style cleanup of stale workspace directories
entrypoint.sh, docker/          # Container entrypoint (auto-detects read-only root for apptainer/HPC)
gdpr_consent/                   # GDPR consent Streamlit component (prebuilt JS bundle)
docs/                           # User/developer guides, deployment docs, Windows-exe build notes
k8s/                            # Kubernetes deployment: base manifests + Kustomize overlays/components
  base/                         #   streamlit + rq-worker deployments, redis, PVC, ingress, cleanup cronjob
  overlays/prod/                #   per-fork Kustomize overlay (slug, image, ingress hostnames, memory tier)
  components/memory-tier-{low,high}/  # node-selector + resource components selected by the overlay
Dockerfile_simple / Dockerfile_simple.arm   # pyOpenMS + R/PTXQC image (amd64 / arm64)
docker-compose.yml              # Local/standalone deployment config
.streamlit/                     # Streamlit config + secrets template
```

## Key Patterns

### Pages

Every page starts with `page_setup()` which handles workspace initialization, sidebar rendering, and parameter loading:

```python
from src.common.common import page_setup, save_params
params = page_setup()
```

Pages are registered in `app.py` under named sidebar sections (the dict key is the section header):

```python
pages = {
    "Section Name": [
        st.Page(Path("content", "my_page.py"), title="My Page", icon="🔬"),
    ],
}
```

### Parameters

Parameters are tracked via widget keys that match entries in `default-parameters.json`. The `save_params(params)` call at the end of a page persists any widget state changes:

```python
params = page_setup()
st.number_input("X", value=params["my-param"], key="my-param")
save_params(params)
```

### TOPP Workflows (WorkflowManager)

Complex workflows subclass `WorkflowManager` and implement 4 methods:
- `upload()` — file upload widgets via `self.ui.upload_widget()`
- `configure()` — TOPP params via `self.ui.input_TOPP()`, Python tool params via `self.ui.input_python()`
- `execution()` — run tools via `self.executor.run_topp()` and `self.executor.run_python()`
- `results()` — display outputs

Each workflow gets 4 content pages (upload, configure, run, results) that call `wf.show_*_section()`. Decorate `configure()` and `results()` with `@st.fragment` for partial reruns. See `.claude/skills/create-workflow.md` for the full template and the `self.file_manager` / `self.executor` / `self.logger` API surface; `src/Workflow.py` is the in-repo example.

### Python Tools

Custom scripts in `src/python-tools/` define a `DEFAULTS` list for auto-generated UI. Always include hidden `in`/`out` keys; the value type drives the widget (bool→checkbox, str+`options`→selectbox, number→number_input):

```python
DEFAULTS = [
    {"key": "in", "value": [], "hide": True},
    {"key": "my-param", "value": 5, "name": "My Parameter", "help": "Description",
     "min": 1, "max": 100, "step_size": 1, "widget_type": "slider"},
]
```

Wire into a workflow with `self.ui.input_python("tool_name")` (configure) and `self.executor.run_python("tool_name", {"in": files})` (execution). Full metadata-key table in `.claude/skills/add-python-tool.md`.

### Presets

Parameter presets in `presets.json` map workflow names (lowercase, hyphens) to named parameter sets. Keys starting with `_` are metadata, not applied as tool params. The workflow key must match the `WorkflowManager("Display Name", ...)` name lowercased-and-hyphenated:

```json
{
  "workflow-name": {
    "Preset Name": {
      "_description": "Tooltip text",
      "TOPPToolName": {"algorithm:section:param": value},
      "_general": {"custom-widget-key": value}
    }
  }
}
```

## Configuration & Deployment Modes (`settings.json`)

`settings.json` controls runtime behavior — far more than just name/version:

- `online_deployment` — `false` = local mode (single user, direct execution); `true` = hosted mode (multi-user workspaces, captcha gate via `src/common/captcha_.py`, Redis/RQ job queue via `QueueManager`).
- `enable_workspaces` — per-user workspaces with unique shareable IDs (persistent params + uploaded files).
- `test` — test/CI flag; bypasses captcha so `streamlit.testing` AppTest runs can drive the app headlessly.
- `workspaces_dir` / `local_data_dir` — where workspaces live; `local_data_dir` (default `/mounted-data` in Docker) enables an in-app file-tree browser for a bind-mounted host directory.
- `demo_workspaces` — seedable read-only example workspaces (`example-data/workspaces/`).
- `max_threads` — `{local, online}` caps on TOPP parallelism.
- `queue_settings` — RQ job timeout / result TTL for online mode.
- `analytics` — Google Analytics / Piwik / Matomo toggles.

**Deployment paths:** `docker-compose.yml` (standalone), `k8s/` Kustomize overlays (OpenMS production cluster, Traefik ingress + Redis + RQ worker + workspace PVC), and apptainer/Singularity SIFs for HPC (the entrypoint auto-switches runtime state to `/tmp` under a read-only root). CI builds amd64+arm64 multi-arch images and publishes SIFs to GHCR.

## Visualization Libraries

Two libraries are commonly used in template-based apps for MS data visualization. See `.claude/skills/add-visualization.md` for a use-case decision table and cross-component linking patterns.

### pyopenms-viz

Pandas DataFrame extension for MS visualization. Use the plotly backend in Streamlit, and `show_fig()` for consistent display/download:

```python
import pyopenms_viz
df.plot.ms_spectrum(backend="plotly")  # mass spectrum (m/z vs intensity)
df.plot.peak_map(backend="plotly")     # 2D peak map (RT vs m/z heatmap)
df.plot.chromatogram(backend="plotly") # chromatogram (RT vs intensity)
df.plot.mobilogram(backend="plotly")   # ion mobility trace
```

Best for: publication-quality static/interactive plots, small-medium datasets, standard MS plot types.

### OpenMS-Insight (t0mdavid-m/openms-insight)

Vue.js-backed interactive Streamlit components for large MS datasets:

- `Table` — server-side pagination with Tabulator.js
- `LinePlot` — stick-style mass spectra via Plotly
- `Heatmap` — 2D scatter handling millions of points
- `VolcanoPlot` — differential expression visualization
- `SequenceView` — peptide sequence with fragment ion matching

Components cross-link via a shared `link_id` column. Best for: large datasets (millions of points), cross-component interactivity, server-side pagination.

## Commands

```bash
# --- Run locally ---
pip install -r requirements.txt
streamlit run app.py
# NOTE: local pip install gives pyOpenMS only — it does NOT install R/PTXQC, so the
# PTXQC report step degrades gracefully. Use the Docker image (Dockerfile_simple) for a
# full run with R + PTXQC. See README "Run Locally" caveat.

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

# --- Docker ---
docker-compose up --build                     # standalone
# Image (pyOpenMS + R/PTXQC): Dockerfile_simple (amd64) / Dockerfile_simple.arm (arm64)
```

### Test conventions

Two distinct test styles live side by side — match the one that fits:

- **GUI tests** drive a page headlessly with `streamlit.testing.v1.AppTest` (e.g. `AppTest.from_file("content/simple_workflow.py").run()`), then assert on `app.number_input`, `app.session_state`, `app.dataframe`, etc. (see `tests/test_simple_workflow.py`).
- **Unit tests** isolate logic from Streamlit by mocking `streamlit` in `sys.modules` *before* importing the module under test, so `st.session_state` is a plain dict (see the header of `tests/test_parameter_presets.py`). Queue/worker tests use `fakeredis`.

CI: `ci.yml` runs lint + `python -m pytest test_gui.py tests/`; `pylint.yml` runs the lint command above; `build-and-test.yml` builds multi-arch images and exercises apptainer + kind (nginx/Traefik) deployments.

## Conventions

- Page files go in `content/`, source logic in `src/`
- Widget keys must match parameter keys in `default-parameters.json`
- Workflow names use lowercase with hyphens: "My Workflow" -> "my-workflow" (this is the `presets.json` key and params lookup key)
- Use `show_fig()` and `show_table()` from `src/common/common.py` for consistent display
- Use `@st.fragment` on methods that should partially rerun (configure, results)
- TOPP tool parameters use colon-separated paths: `"algorithm:section:param_name"`
- For repeatable tasks (new page, workflow, tool, preset, deployment), follow the matching `.claude/skills/*.md` guide and its checklist
