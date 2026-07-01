"""Filtered MaxQuant directory upload (folder shim + native uploader).

The user picks a whole MaxQuant ``txt`` folder via the ``mq_dir_upload``
JavaScript shim (repo-root ``mq_dir_upload/``). The shim filters the folder down
to the PTXQC-relevant files and injects ONLY those into a native
``st.file_uploader`` rendered here, which uploads them over Streamlit's HTTP
endpoint. The large irrelevant outputs (``allPeptides.txt``, …) never leave the
user's machine, and — unlike sending bytes back through the component websocket
— this scales to the hundreds-of-MB sizes real MaxQuant files reach.

The uploaded files are mirrored into the same workspace upload directory that
``StreamlitUI.upload_widget(directory=True)`` would populate
(``<workflow>/input-files/txt-files/``), so the rest of the workflow
(``Workflow.execution`` / ``_gather_files``) is unchanged.
"""

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# PTXQC-relevant MaxQuant files. Matched case-insensitively on the basename in
# the JS shim; the canonical casing here is what users see in the UI.
PTXQC_FILES = [
    "evidence.txt",
    "msms.txt",
    "msmsScans.txt",
    "parameters.txt",
    "proteinGroups.txt",
    "summary.txt",
    "mqpar.xml",
]

# Resolve from this file so the declaration works regardless of CWD.
_COMPONENT_DIR = Path(__file__).resolve().parents[2] / "mq_dir_upload"

# Declare the component at MODULE IMPORT (top level), NOT lazily inside a
# function. A lazy declare_component() can raise
# "RuntimeError: module is None. This should never happen." when Streamlit
# reloads this module on a source change: declare_component's _get_module_name()
# walks the *caller* stack frame and inspect.getmodule() then fails to resolve
# the in-function frame. At module level the caller frame is this module's body,
# which resolves reliably (and re-resolves cleanly on reload).
mq_dir_component = components.declare_component("mq_dir_upload", path=str(_COMPONENT_DIR))


def _fmt_size(num: float) -> str:
    """Human-readable byte size."""
    if num < 1024:
        return f"{int(num)} B"
    for unit in ("KB", "MB", "GB"):
        num /= 1024
        if num < 1024 or unit == "GB":
            return f"{num:.1f} {unit}"
    return f"{num:.1f} GB"


def _staged_files(files_dir: Path) -> list[Path]:
    """Staged input files (excludes the external_files.txt sidecar)."""
    if not files_dir.exists():
        return []
    return sorted(
        (p for p in files_dir.iterdir()
         if p.is_file() and p.name != "external_files.txt"),
        key=lambda p: p.name,
    )


def filtered_directory_upload(files_dir: Path, key: str = "mq_dir_upload") -> None:
    """Render the folder picker + native uploader and mirror files to ``files_dir``.

    The native ``st.file_uploader`` provides the file list, per-file sizes, the
    upload progress bar and per-file removal for free. Its drag-and-drop area is
    hidden — the folder shim is the only entry point — and the picker is hidden
    once files are staged so a second pick cannot merge into an existing set.
    """
    files_dir.mkdir(parents=True, exist_ok=True)

    # Hide the entire native uploader: we use it purely as the HTTP transport
    # (the shim injects files into its input) and render our own complete file
    # list below — Streamlit's built-in list paginates at 3/page, which is silly
    # for <=7 files.
    #
    # NOTE: this selector is page-global — it hides EVERY stFileUploader on the
    # page, not just the one below. That is fine because in "MaxQuant directory"
    # mode this is the only uploader rendered (the multi-file / mzTab / YAML
    # uploaders live in other data-type branches or on other pages). If a second
    # uploader is ever added to the upload page, scope this rule instead.
    st.markdown(
        "<style>[data-testid='stFileUploader']{display:none;}</style>",
        unsafe_allow_html=True,
    )

    # Shim button sits above the file list; its `hidden` state depends on what
    # is staged, so render it into a slot filled after the uploader is read.
    shim_slot = st.container()

    # `key` carries a counter so removals can reset the uploader widget.
    ctr = st.session_state.setdefault(f"{key}-ctr", 0)
    uploaded = st.file_uploader(
        "MaxQuant txt files",
        accept_multiple_files=True,
        type=["txt", "xml"],
        key=f"{key}-native-{ctr}",
        label_visibility="collapsed",
    )

    # `files_dir` is the durable source of truth. The uploader only ADDS files —
    # its widget state resets when the user navigates away and back, so we must
    # NOT delete staged files just because it returns empty (that was the
    # "upload disappeared on going back" bug). Removal is explicit (below).
    for f in (uploaded or []):
        dest = files_dir / Path(f.name).name
        if not dest.exists() or dest.stat().st_size != getattr(f, "size", -1):
            dest.write_bytes(f.getbuffer())

    staged = _staged_files(files_dir)

    with shim_slot:
        mq_dir_component(
            allowed=PTXQC_FILES, hidden=bool(staged), key=f"{key}-shim", default=None
        )

    if staged:
        total = sum(p.stat().st_size for p in staged)
        st.success(f"✅ {len(staged)} file(s) uploaded ({_fmt_size(total)}):")
        for p in staged:
            row = st.columns([6, 2, 1])
            row[0].markdown(f"📄 {p.name}")
            row[1].markdown(
                f"<div style='text-align:right;color:#666'>{_fmt_size(p.stat().st_size)}</div>",
                unsafe_allow_html=True,
            )
            if row[2].button("✕", key=f"rm-{key}-{p.name}", help=f"Remove {p.name}"):
                p.unlink()
                st.session_state[f"{key}-ctr"] = ctr + 1  # reset uploader so it won't re-add
                st.rerun()
        if st.button(
            "🗑️ Clear all", key=f"clear-{key}", use_container_width=True
        ):
            for p in staged:
                p.unlink()
            st.session_state[f"{key}-ctr"] = ctr + 1  # fresh, empty uploader
            st.rerun()
