# mq_dir_upload — MaxQuant folder-picker shim

A tiny bidirectional Streamlit custom component that lets the user pick a whole
MaxQuant `txt` folder but upload **only** the PTXQC-relevant files
(`evidence.txt`, `msms.txt`, `msmsScans.txt`, `parameters.txt`,
`proteinGroups.txt`, `summary.txt`, `mqpar.xml`). The large irrelevant MaxQuant
outputs (`allPeptides.txt`, `peptides.txt`, …) never leave the user's machine.

## How it works (and why it's a *shim*)

Streamlit's built-in `st.file_uploader` directory mode filters by file
**extension** only, so it can't drop `allPeptides.txt` (it's a `.txt`).
Filtering by file *name* must happen in the browser — which needs JavaScript.

The naive custom-component approach (read the files, base64-encode them, and
return them to Python via `setComponentValue`) **does not scale**: that value
travels over the websocket, which chokes on the hundreds-of-MB sizes real
MaxQuant files reach (the value is silently dropped → nothing uploads). The
relevant files (`evidence`/`msms`/`msmsScans`) are themselves the big ones, so
this isn't avoidable by filtering.

So this component is a **shim**, not an uploader. On a folder pick it:

1. filters the browser `FileList` down to the allow-listed names (in JS), then
2. injects *only* those `File` objects into the page's native
   `st.file_uploader` (`DataTransfer` → set `input.files` → dispatch a bubbling
   `change` event).

Streamlit's native uploader then transfers them over its **HTTP** endpoint
(handles GBs, shows a file list / sizes / progress / per-file remove). The shim
**never calls `setComponentValue`** — the heavy bytes never touch the websocket.

It must be a *declared* component (not `components.html`) so it runs
**same-origin** and can reach `window.parent.document` to find that native
uploader input. The Python side (`src/common/mq_dir_upload.py`) renders the
native uploader (drag-drop area hidden via CSS), mirrors its files into the
workspace dir, and passes `hidden=True` to the shim once files are staged
(uploading more into an existing set is disallowed; the user clears first).

## Files

- `index.html` — loads `main.js`.
- `main.js` — **hand-written, no build step.** Speaks the Streamlit iframe
  `postMessage` protocol directly (`componentReady` / `render` /
  `setFrameHeight`) — there is nothing to `npm build`. Edit `main.js` and reload.

## Args (from Python)

- `allowed`: list of relevant file names (matched case-insensitively on basename).
- `hidden`: when true, the picker button is hidden (files already staged).
