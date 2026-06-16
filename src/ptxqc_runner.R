#!/usr/bin/env Rscript
# Thin PTXQC command-line wrapper for the streamlit-template port.
#
# PTXQC is kept as a version-pinned R subprocess tool: the Streamlit app never
# imports R, it only shells out to this script via CommandExecutor.run_command.
# All PTXQC-specific config assembly lives here (mirroring the original
# PTXQC-web app/server.R build.yaml), so the Python side needs no knowledge of
# PTXQC's YAML schema or its unexported internals.
#
# Subcommands:
#   default-config --out <file>
#       Write the version-correct default PTXQC config YAML to <file> and print a
#       JSON object {version, metrics:[{id,name}, ...]} to stdout. The metric list
#       drives the "Compute metrics" UI and is therefore always correct for the
#       installed PTXQC version (no hardcoding in Python).
#
#   run --config <params.json> --in <txt-dir|mztab-file> --type <maxquant|mztab> --out <dir>
#       Build the PTXQC config from the user parameters (identical to PTXQC-web's
#       build.yaml) or use an uploaded YAML verbatim, run createReport(), and write
#       <out>/ptxqc_result.json describing the produced files. Exits non-zero on
#       failure (run_command then reports the failure to the workflow log).

# PTXQC update staging library. Runtime PTXQC updates (the `update` subcommand) are
# installed *here* — never over the image's built-in PTXQC — and this directory is
# prepended to .libPaths() so a verified staged update shadows the built-in copy for
# every subcommand. When the stage is empty (fresh container, or after a bad update is
# reverted) every subcommand transparently falls back to the built-in site library.
# /tmp is writable under docker, k8s and apptainer alike, so this needs no Dockerfile or
# entrypoint change; set PTXQC_LIB to relocate it (e.g. a PVC path to persist updates).
local({
  stage <- Sys.getenv("PTXQC_LIB")
  if (!nzchar(stage)) stage <- "/tmp/ptxqc-lib"
  dir.create(stage, showWarnings = FALSE, recursive = TRUE)
  if (dir.exists(stage)) .libPaths(c(stage, .libPaths()))
})

# PTXQC is attached lazily (per subcommand) rather than here: the `update`
# subcommand must not require the package to load before it can (re)install it.
suppressPackageStartupMessages({
  library(yaml)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
cmd <- if (length(args) >= 1) args[[1]] else ""

get_opt <- function(flag, default = NULL) {
  i <- match(flag, args)
  if (is.na(i) || i == length(args)) return(default)
  args[[i + 1]]
}

# Attach PTXQC. Only the subcommands that actually build/run a report need it; the
# `update` subcommand deliberately skips this so it can (re)install PTXQC cleanly.
load_ptxqc <- function() suppressPackageStartupMessages(library(PTXQC))

# Ordered QC metric list, mirroring PTXQC-web app/global.R.
metric_table <- function() {
  lst <- PTXQC:::getMetricsObjects(FALSE)
  meta <- PTXQC:::getMetaData(lst_qcMetrics = lst)
  ids <- gsub("qcMetric_", "", names(lst[meta$.id]))
  data.frame(id = ids, name = ids, stringsAsFactors = FALSE)
}

# Assemble the PTXQC `param` list from the user values, mirroring
# PTXQC-web app/server.R build.yaml (lines 83-122).
build_param_list <- function(cfg) {
  p <- cfg$param
  contaminants <- list()
  if (!is.null(cfg$contaminants) && length(cfg$contaminants) > 0) {
    for (c in cfg$contaminants) {
      key <- paste0("cont_", c$name)
      contaminants[[key]] <- c(name = c$name, threshold = as.integer(c$threshold))
    }
  }
  param <- list()
  param$id_rate_bad <- p$id_rate_bad
  param$id_rate_great <- p$id_rate_great
  param$pg_ratioLabIncThresh <- p$pg_ratioLabIncThresh
  param$param_PG_intThresh <- p$param_PG_intThresh
  param$param_EV_protThresh <- p$param_EV_protThresh
  param$param_EV_intThresh <- p$param_EV_intThresh
  param$param_EV_pepThresh <- p$param_EV_pepThresh
  param$yaml_contaminants <- if (length(contaminants) > 0) contaminants else FALSE
  param$param_EV_MatchingTolerance <- p$param_EV_MatchingTolerance
  param$param_evd_mbr <- p$param_evd_mbr
  param$param_EV_PrecursorTolPPM <- p$param_EV_PrecursorTolPPM
  param$param_EV_PrecursorOutOfCalSD <- p$param_EV_PrecursorOutOfCalSD
  param$param_EV_PrecursorTolPPMmainSearch <- p$param_EV_PrecursorTolPPMmainSearch
  param$param_MSMSScans_ionInjThresh <- p$param_MSMSScans_ionInjThresh
  param
}

# Build the PTXQC YAMLClass object from the user config (mirrors server.R build.yaml).
build_yc <- function(cfg) {
  # Empty selection means "all metrics" (PTXQC-web defaults to all selected).
  if (is.null(cfg$metrics) || length(cfg$metrics) == 0) {
    mets <- paste0("qcMetric_", metric_table()$id)
  } else {
    mets <- paste0("qcMetric_", cfg$metrics)
  }
  param <- build_param_list(cfg)
  yc <- YAMLClass$new(list())
  PTXQC:::createYaml(yc = yc, DEBUG_PTXQC = FALSE, metrics = mets, param = param)
  yc
}

# Produce the yaml_obj (a nested list) that createReport() consumes.
make_yaml_obj <- function(cfg) {
  if (!is.null(cfg$uploaded_yaml) && nzchar(cfg$uploaded_yaml)) {
    # User uploaded a full PTXQC config YAML -> use verbatim (server.R:194 short-circuit).
    return(yaml.load_file(cfg$uploaded_yaml))
  }
  tmp <- tempfile(fileext = ".yaml")
  invisible(capture.output(build_yc(cfg)$writeYAML(tmp), type = "output"))
  yaml.load_file(tmp)
}

if (cmd == "default-config") {
  load_ptxqc()
  out <- get_opt("--out")
  meta_out <- paste0(out, ".json")
  mt <- metric_table()
  # createYaml/writeYAML print progress to stdout; capture it so the JSON contract
  # stays clean. The metric list is essential for the UI, so never let a YAML-write
  # failure fail this subcommand (the default YAML is only a download/reference).
  invisible(capture.output(
    tryCatch({
      yc <- YAMLClass$new(list())
      PTXQC:::createYaml(yc = yc, DEBUG_PTXQC = FALSE,
                         metrics = paste0("qcMetric_", mt$id), param = list())
      yc$writeYAML(out)
    }, error = function(e) {
      message(paste0("default-config: could not write default YAML: ", conditionMessage(e)))
    }),
    type = "output"
  ))
  # Python reads the metric list / version from this sidecar file (not stdout).
  writeLines(toJSON(list(
    version = as.character(packageVersion("PTXQC")),
    metrics = mt
  ), dataframe = "rows", auto_unbox = TRUE), con = meta_out)

} else if (cmd == "run") {
  load_ptxqc()
  config <- get_opt("--config")
  input  <- get_opt("--in")
  type   <- get_opt("--type", "maxquant")
  out    <- get_opt("--out")
  # Resolve to absolute paths up front: createReport() renders an Rmd via rmarkdown, which
  # changes the working directory mid-render, so a relative txt_folder/out gets re-resolved
  # against the wrong cwd and fails ("directory does not exist"). Surfaced once a runtime
  # update moved PTXQC to 1.1.5; absolute paths are cwd-independent.
  if (!is.null(config)) config <- normalizePath(config, mustWork = FALSE)
  if (!is.null(input))  input  <- normalizePath(input, mustWork = FALSE)
  if (!is.null(out))    out    <- normalizePath(out, mustWork = FALSE)

  cfg <- fromJSON(config, simplifyVector = TRUE, simplifyDataFrame = FALSE)
  version <- as.character(packageVersion("PTXQC"))
  result_file <- file.path(out, "ptxqc_result.json")

  write_result <- function(lst) {
    writeLines(toJSON(lst, auto_unbox = TRUE, null = "null"), result_file)
  }

  glob_one <- function(dir, pattern) {
    hits <- list.files(dir, pattern = pattern, full.names = TRUE)
    if (length(hits) > 0) normalizePath(hits[[1]]) else NULL
  }

  tryCatch({
    yaml_obj <- make_yaml_obj(cfg)
    if (type == "mztab") {
      createReport(txt_folder = NULL, mztab_file = input,
                   yaml_obj = yaml_obj, enable_log = TRUE)
    } else {
      createReport(txt_folder = input, mztab_file = NULL,
                   yaml_obj = yaml_obj, enable_log = TRUE)
    }
    write_result(list(
      version = version,
      html = glob_one(out, "report.*\\.html$"),
      pdf  = glob_one(out, "report.*\\.pdf$"),
      yaml = glob_one(out, "report.*\\.yaml$"),
      log  = glob_one(out, "report.*\\.log$"),
      error = NULL
    ))
  }, error = function(e) {
    msg <- conditionMessage(e)
    write_result(list(version = version, error = msg))
    message(paste0("PTXQC createReport failed: ", msg))
    quit(status = 1)
  })

} else if (cmd == "build-config") {
  # Write the PTXQC config YAML that a run would use (for preview/download and the
  # parity audit) without running a report.
  load_ptxqc()
  config <- get_opt("--config")
  out <- get_opt("--out")
  cfg <- fromJSON(config, simplifyVector = TRUE, simplifyDataFrame = FALSE)
  invisible(capture.output({
    if (!is.null(cfg$uploaded_yaml) && nzchar(cfg$uploaded_yaml)) {
      file.copy(cfg$uploaded_yaml, out, overwrite = TRUE)
    } else {
      build_yc(cfg)$writeYAML(out)
    }
  }, type = "output"))

} else if (cmd == "update") {
  # Update PTXQC AND its required dependencies to the latest release before a report runs,
  # into the staging library ONLY — never over the image's built-in copy. Uses the same
  # Posit PPM binary source as the Docker build, so deps install as precompiled binaries.
  # Best-effort by contract: the caller (Workflow.execution) never aborts the run on a
  # non-zero exit, and a staged update that fails to load is reverted to the built-in copy.
  repo <- "https://packagemanager.posit.co/cran/__linux__/jammy/latest"
  options(repos = c(PPM = repo),
          HTTPUserAgent = sprintf("R/%s R (%s)", getRversion(),
            paste(getRversion(), R.version$platform, R.version$arch, R.version$os)),
          timeout = max(getOption("timeout"), 300))  # a hung mirror must not stall the report
  stage <- Sys.getenv("PTXQC_LIB")
  if (!nzchar(stage)) stage <- "/tmp/ptxqc-lib"
  dir.create(stage, showWarnings = FALSE, recursive = TRUE)
  # Refuse to install into / wipe a built-in library: the stage must be a dedicated,
  # writable directory so the built-in PTXQC is always preserved as the fallback.
  protected <- normalizePath(c(.Library, .Library.site), winslash = "/", mustWork = FALSE)
  stage_ok <- dir.exists(stage) &&
              !(normalizePath(stage, winslash = "/", mustWork = FALSE) %in% protected) &&
              file.access(stage, mode = 2) == 0
  before <- tryCatch(as.character(packageVersion("PTXQC")), error = function(e) "none")
  if (!stage_ok) {
    message(sprintf("PTXQC update: no usable staging library (PTXQC_LIB=%s); keeping built-in version %s",
                    stage, before))
  } else {
    .libPaths(c(stage, .libPaths()))  # ensure stage on path before checking/installing
    # Skip the (otherwise per-run) reinstall when already on the latest release. The PPM
    # PACKAGES index fetch is far cheaper than downloading + installing the dependency tree.
    latest <- tryCatch(available.packages()["PTXQC", "Version"], error = function(e) NA_character_)
    if (is.na(latest)) {
      # PPM unreachable: a full install would fail too, so don't attempt one — keep current.
      message(sprintf("PTXQC update: could not reach PPM to check for updates; keeping current version %s", before))
    } else if (before != "none" && package_version(before) >= package_version(latest)) {
      message(sprintf("PTXQC update: already current (%s)", before))
    } else {
      # A newer release exists (or PTXQC is missing): stage it. dependencies = NA also
      # (re)installs PTXQC's required deps (Depends/Imports/LinkingTo) so a release needing
      # newer deps actually loads; deps already satisfied by the built-in library are untouched.
      withCallingHandlers(
        tryCatch(install.packages("PTXQC", lib = stage, dependencies = NA),
                 error = function(e) message("PTXQC install error: ", conditionMessage(e))),
        warning = function(w) {
          message("PTXQC install warning: ", conditionMessage(w))
          invokeRestart("muffleWarning")
        }
      )
      # Verify the staged PTXQC actually loads (deps resolved across the stage + built-in libs).
      ok <- tryCatch({
        suppressPackageStartupMessages(loadNamespace("PTXQC"))
        TRUE
      }, error = function(e) {
        message("staged PTXQC failed to load: ", conditionMessage(e))
        FALSE
      })
      if (!ok) {
        unlink(list.files(stage, full.names = TRUE), recursive = TRUE, force = TRUE)
        message("PTXQC update: staged update unusable, reverted to built-in version")
      } else {
        message(sprintf("PTXQC update: %s -> %s", before, as.character(packageVersion("PTXQC"))))
      }
    }
  }
  # Hard-fail only if PTXQC is now entirely unavailable (neither stage nor built-in loads).
  if (!requireNamespace("PTXQC", quietly = TRUE)) quit(status = 1)

} else {
  message("Usage: ptxqc_runner.R [default-config|run|build-config|update] ...")
  quit(status = 2)
}
