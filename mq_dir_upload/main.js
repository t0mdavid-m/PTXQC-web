/*
 * mq_dir_upload — MaxQuant "txt" folder-picker shim.
 *
 * The user picks a whole MaxQuant txt folder; this shim filters the browser's
 * FileList down to the PTXQC-relevant files (by name) and injects ONLY those
 * into the page's native st.file_uploader (via DataTransfer + a change event).
 * Streamlit then uploads them over its HTTP endpoint — so large files work and
 * the irrelevant files (allPeptides.txt, …) never leave the machine.
 *
 * Why a shim instead of returning the bytes: a custom component can only send
 * data back over the websocket (setComponentValue), which chokes on hundreds of
 * MB. The native uploader uses a separate HTTP transport that scales. This shim
 * deliberately never calls setComponentValue — it only orchestrates the native
 * widget. It must be a *declared* component (not components.html) so it runs
 * same-origin and can reach window.parent.document.
 */
(function () {
  "use strict";

  function post(t, d) {
    var m = { isStreamlitMessage: true, type: t };
    for (var k in d) m[k] = d[k];
    window.parent.postMessage(m, "*");
  }
  function h(px) { post("streamlit:setFrameHeight", { height: px }); }
  function basename(n) { return (n || "").split(/[\\/]/).pop(); }

  var built = false, allowed = [], hidden = false, label, input, status;

  // The native st.file_uploader's file input, in the parent document. On the
  // upload page there is exactly one file_uploader, so this is unambiguous.
  function nativeInput() {
    var pdoc = window.parent.document;
    return (
      pdoc.querySelector('[data-testid="stFileUploader"] input[type="file"]') ||
      pdoc.querySelector('section[data-testid="stFileUploaderDropzone"] input[type="file"]') ||
      pdoc.querySelector('input[type="file"]')
    );
  }

  function onPick(ev) {
    var all = Array.prototype.slice.call(ev.target.files || []);
    if (!all.length) return;

    var allow = {};
    allowed.forEach(function (n) { allow[n.toLowerCase()] = true; });

    // De-dupe by basename (a MaxQuant export may nest combined/txt).
    var picked = {}, order = [];
    all.forEach(function (f) {
      var lc = basename(f.name).toLowerCase();
      if (allow[lc] && !picked[lc]) { picked[lc] = f; order.push(lc); }
    });
    var matched = order.map(function (lc) { return picked[lc]; });

    if (!matched.length) {
      status.style.color = "#b00";
      status.textContent =
        "No PTXQC-relevant files found in that folder (scanned " + all.length + ").";
      ev.target.value = "";
      h(90);
      return;
    }

    var nat = nativeInput();
    if (!nat) {
      status.style.color = "#b00";
      status.textContent = "Could not find the upload target — please reload the page.";
      h(90);
      return;
    }

    // Hand the filtered File objects to the native uploader and let Streamlit
    // upload them over HTTP. react-dropzone listens for a bubbling change event.
    var dt = new DataTransfer();
    matched.forEach(function (f) { dt.items.add(f); });
    nat.files = dt.files;
    nat.dispatchEvent(new Event("input", { bubbles: true }));
    nat.dispatchEvent(new Event("change", { bubbles: true }));

    status.style.color = "#444";
    status.textContent = "Uploading " + matched.length + " file(s)…";
    ev.target.value = "";
    h(90);
  }

  function build() {
    label = document.createElement("label");
    label.textContent = "📁 Select MaxQuant txt folder";
    label.style.cssText =
      "display:inline-block;padding:.5rem 1rem;background:#ff4b4b;color:#fff;" +
      "border-radius:.5rem;cursor:pointer;font-weight:600;line-height:1.4;" +
      "font-family:'Source Sans Pro',sans-serif;";

    input = document.createElement("input");
    input.type = "file";
    input.multiple = true;
    input.setAttribute("webkitdirectory", "");
    input.setAttribute("directory", "");
    input.webkitdirectory = true;
    input.style.display = "none";
    input.addEventListener("change", onPick);
    label.appendChild(input);

    status = document.createElement("div");
    status.style.cssText =
      "margin-top:.5rem;font-size:.85rem;color:#444;line-height:1.4;" +
      "font-family:'Source Sans Pro',sans-serif;";

    document.body.style.margin = "0";
    document.body.appendChild(label);
    document.body.appendChild(status);
    built = true;
  }

  function apply() {
    if (!built) return;
    // Hidden once files are staged: uploading more into an existing set is not
    // allowed — the user must clear first.
    label.style.display = hidden ? "none" : "inline-block";
    status.textContent = hidden
      ? ""
      : "Only the PTXQC-relevant files are uploaded; everything else stays on your machine.";
    h(hidden ? 1 : 90);
  }

  window.addEventListener("message", function (ev) {
    var d = ev.data;
    if (!d || d.type !== "streamlit:render") return;
    if (!built) build();
    var a = d.args || {};
    if (Array.isArray(a.allowed)) allowed = a.allowed;
    hidden = !!a.hidden;
    apply();
  });

  post("streamlit:componentReady", { apiVersion: 1 });
  h(90);
})();
