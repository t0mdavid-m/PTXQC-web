# Proteomics Quality Control

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://ptxqc.webapps.openms.org)

A deployable **[Streamlit](https://streamlit.io/)** web app that generates
**[PTXQC](https://github.com/cbielow/PTXQC)** quality-control reports for mass-spectrometry
proteomics data. Upload an OpenMS `.mzTab` file or MaxQuant `.txt` output, optionally tune the
thresholds, and the app produces an interactive, self-contained HTML/PDF QC report.

PTXQC is an R package — this app does not reimplement it. It collects your inputs, assembles a
PTXQC configuration, and runs `PTXQC::createReport` to build the report.

It is a port of the original PTXQC-web R-Shiny app
([Webserver-for-Quality-Control-Reports](https://github.com/koehlek99/Webserver-for-Quality-Control-Reports))
onto the [OpenMS streamlit-template](https://github.com/OpenMS/streamlit-template) for better
long-term maintainability.

## Features

- Upload a single OpenMS `mzTab`, a whole MaxQuant `txt` folder, or individual MaxQuant files
  (`evidence.txt`, `msms.txt`, `msmsScans.txt`, `parameters.txt`, `proteinGroups.txt`,
  `summary.txt`, `mqpar.xml`). The more files you provide, the more metrics you get —
  `evidence.txt` is the most important.
- Produces a self-contained PTXQC **HTML** report (plus PDF, the resolved YAML config, and a
  log), viewable in-page and downloadable.
- Tune ~13 thresholds (ID-rate bands, protein/peptide count targets, mass-error tolerances,
  match-between-runs, ion-injection time, …) and a contaminants list — or upload a full PTXQC
  **YAML** config to override the manual settings. Toggle individual metrics on or off.
- Per-user workspaces with unique, shareable IDs (persistent parameters and uploaded files).
- Always-current PTXQC: before each run the app makes a best-effort update to the latest PTXQC
  release into a staging library, verifies it loads, and auto-reverts to the built-in version if
  anything is wrong — so a bad release can never break your reports.

## 🔗 Web App

A hosted instance is available at **[ptxqc.webapps.openms.org](https://ptxqc.webapps.openms.org)**.

## 💻 Run locally (without Docker)

You can run the app straight from a checkout. Two layers are involved: the **Python/Streamlit**
front end and the **R/PTXQC** engine that actually builds the reports.

### 1. Python front end (minimum to launch the app)

```bash
git clone https://github.com/BioinformaticsSolutionCenter/PTXQC-web.git
cd PTXQC-web
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py                                # opens http://localhost:8501
```

This is enough to launch every page. The committed `settings.json` runs in **local mode**
(single user, no captcha, no Redis), so nothing else is required to start.

> **Note:** `pip install` only gives you **pyOpenMS** — it does **not** install R or PTXQC. Without
> them the app still loads and degrades gracefully: the *Configure* page warns, the live metric
> list is empty, and actually running a report fails. To generate reports, install the R engine
> below.

### 2. R engine (needed to generate reports)

Install **R** (4.x) and **pandoc** (used for the HTML report), then install the PTXQC package and
the two helper packages the runner uses:

```bash
Rscript -e 'install.packages(c("PTXQC", "jsonlite", "yaml"), repos = "https://cloud.r-project.org")'
```

- **Windows / macOS** get precompiled CRAN binaries, so this is quick and needs no extra system
  libraries. Install R from <https://cran.r-project.org> and pandoc from
  <https://pandoc.org/installing.html> (or `winget install RProject.R pandoc` /
  `brew install r pandoc`).
- **Linux** compiles PTXQC's dependencies from source unless you use precompiled binaries. The
  fast path (same one the Docker build uses) is Posit Public Package Manager plus the system
  `-dev` libraries — see the `install.packages` step and the `apt-get install` list in
  [`Dockerfile_simple`](Dockerfile_simple) for the exact repository URL and package names.

Make sure `Rscript` is on your `PATH` (the app shells out to `Rscript src/ptxqc_runner.R …`).
Verify the engine is visible to the app with:

```bash
Rscript src/ptxqc_runner.R default-config --out /tmp/ptxqc-default.yaml
```

If that writes a YAML file, the *Configure* page will show the live metric list and report
generation will work.

## 🐳 Run with Docker

The app ships as a single prebuilt image (linux/amd64) on the GitHub Container Registry, so you
don't need to clone or build anything to run it.

1. **Pull the image**

   ```bash
   docker pull ghcr.io/bioinformaticssolutioncenter/ptxqc-web:latest
   ```

2. **Run it** and open <http://localhost:8501>

   ```bash
   docker run -p 8501:8501 ghcr.io/bioinformaticssolutioncenter/ptxqc-web:latest
   ```

### Mount a local data directory

To make a directory of MS files on the host available to the app without uploading or copying
them, bind-mount it at `/mounted-data` (the path `local_data_dir` points to in `settings.json`):

```bash
docker run -p 8501:8501 \
  -v /path/on/host:/mounted-data:ro \
  ghcr.io/bioinformaticssolutioncenter/ptxqc-web:latest
```

The upload page auto-detects the mount: when the directory exists at runtime it shows an in-app
file browser, and selected files are referenced in place (no copy into the workspace), so the
mount can safely be read-only.

### Build from source (optional)

To build the image yourself, you need a GitHub token with package-read access for the build step:

```bash
git clone https://github.com/BioinformaticsSolutionCenter/PTXQC-web.git
cd PTXQC-web
GITHUB_TOKEN=<your-token> docker compose up -d --build
# or build directly:
# docker build -f Dockerfile_simple --build-arg GITHUB_TOKEN=<your-token> -t ptxqc-web:latest .
```

The image bundles pyOpenMS (via pip) plus R and the PTXQC package.

## 🛰️ Run with Apptainer / Singularity (HPC)

Apptainer (formerly Singularity) is the dominant container runtime on HPC clusters. Prebuilt
SIFs are published to GHCR via ORAS, so you can pull a ready-to-run image — no on-the-fly
OCI→SIF conversion — and run it as your user (no root, no `--writable-tmpfs` required):

```bash
apptainer pull --name ptxqc-web.sif \
  oras://ghcr.io/bioinformaticssolutioncenter/ptxqc-web/sif:latest
apptainer run \
  --bind /path/to/data:/mounted-data:ro \
  --bind /path/to/workspaces:/workspaces-streamlit-template \
  ptxqc-web.sif
```

If a tag hasn't been prebuilt yet, fall back to on-the-fly conversion:
`apptainer pull docker://ghcr.io/bioinformaticssolutioncenter/ptxqc-web:latest`. Requires
apptainer 1.1+ or singularity-ce 3.10+ for the `oras://` transport.

The entrypoint auto-detects the read-only root filesystem (apptainer's default) and switches its
runtime state — Redis data directory, nginx config, PID files — to `/tmp`, which is always
writable inside an apptainer container.

## License

Distributed under the 3-clause BSD license. See [`LICENSE`](LICENSE).

## Acknowledgements

The QC reports are generated with the **[PTXQC](https://github.com/cbielow/PTXQC)** R package.
PTXQC-web was originally developed as a bachelor thesis at the
**[Bioinformatics Solution Center, Freie Universität Berlin](https://www.bsc.fu-berlin.de/)** by
Kristin Köhler, supervised by Dr. Chris Bielow and Dr. Sandro Andreotti, with contributions from
Kilian Malek (2023). The port onto the
[OpenMS streamlit-template](https://github.com/OpenMS/streamlit-template) was done by Tom David
Müller.

Questions or feedback: **mail@bsc.fu-berlin.de**.

## Citation

If you use this app, please cite PTXQC:

- Bielow C., Mastrobuoni G., Kempa S. *Proteomics Quality Control: Quality Control Software for
  MaxQuant Results.* Journal of Proteome Research 2016, 15(3), 777–787.
  [https://doi.org/10.1021/acs.jproteome.5b00780](https://doi.org/10.1021/acs.jproteome.5b00780)

And the OpenMS WebApps framework it is built on:

- Müller, T. D., Siraj, A., et al. *OpenMS WebApps: Building User-Friendly Solutions for MS
  Analysis.* Journal of Proteome Research (2025).
  [https://doi.org/10.1021/acs.jproteome.4c00872](https://doi.org/10.1021/acs.jproteome.4c00872)
