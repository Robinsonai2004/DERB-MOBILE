/* DERB MOBILE - Document editor helpers.
   Dependency-free, page-scoped; drives the contenteditable paper and the
   hidden size/align fields that the server's normaliser understands. */
(function () {
  "use strict";

  var form = document.getElementById("doc-editor-form");
  var area = document.getElementById("doc-area");
  var titleInput = document.getElementById("doc-title");

  /* ------------------------------------------- submit serialisation ---- */
  /* The workspace is contenteditable, so the typed text must be copied
     into a plain field before the form posts; core/doc_model.py then
     normalises it (and keeps blank lines as paragraph spacing). */
  function serialise() {
    var hidden = document.getElementById("doc-body");
    if (!hidden || !area) return;
    // innerText renders <br> and block boundaries as real newlines on every
    // engine we target (Chromium/WebView; Firefox keeps the same contract).
    var raw = (area.innerText || area.textContent || "").replace(/\u00a0/g, " ");
    var lines = raw.replace(/\r/g, "").split("\n");
    hidden.value = lines.join("\n").replace(/\n{3,}/g, "\n\n");
  }

  if (form && area) {
    form.addEventListener("submit", serialise);
  }

  /* --------------------------------------------------------- toolbar ---- */
  var toolbar = document.getElementById("doc-toolbar");

  function exec(cmd, value) {
    if (document.execCommand) {
      document.execCommand(cmd, false, value || null);
      if (area) { area.focus(); }
      refreshStates();
    }
  }

  function refreshStates() {
    if (!toolbar || typeof document.queryCommandState !== "function") return;
    ["bold", "italic", "underline", "insertUnorderedList", "insertOrderedList"]
      .forEach(function (cmd) {
        var btn = toolbar.querySelector('[data-cmd="' + cmd + '"]');
        if (!btn) return;
        var on = false;
        try { on = document.queryCommandState(cmd); } catch (err) { on = false; }
        btn.classList.toggle("is-on", on);
      });
  }

  if (toolbar) {
    toolbar.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-cmd]");
      if (!btn || !btn.dataset.cmd) return;
      e.preventDefault();
      exec(btn.dataset.cmd);
    });
  }

  /* ---------------------------------------------------------- size ------ */
  var sizeSelect = document.getElementById("doc-size-select");
  var sizeField = document.getElementById("doc-size");

  function applySize(sizeKey) {
    if (sizeField) { sizeField.value = String(sizeKey); }
    if (area) { area.setAttribute("data-size", String(sizeKey)); }
  }

  if (sizeSelect) {
    sizeSelect.addEventListener("change", function () {
      applySize(sizeSelect.value);
    });
    applySize(sizeSelect.value);
  }

  /* ---------------------------------------------------------- align ----- */
  var alignField = document.getElementById("doc-align");

  function applyAlign(alignment) {
    if (!alignField) return;
    alignField.value = alignment;
    if (area) { area.setAttribute("data-align", alignment); }
    if (toolbar) {
      toolbar.querySelectorAll(".doc-tool--align").forEach(function (btn) {
        btn.classList.toggle("is-on", btn.dataset.align === alignment);
      });
    }
  }

  if (alignField) {
    document.querySelectorAll(".doc-tool--align").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        applyAlign(btn.dataset.align);
      });
    });
    applyAlign(alignField.value || "left");
  }

  /* ------------------------------------------------------- print/clear - */
  document.querySelectorAll("[data-role='print']").forEach(function (btn) {
    btn.addEventListener("click", function () { window.print(); });
  });

  var clearBtn = document.getElementById("doc-clear-btn");
  if (clearBtn && form) {
    clearBtn.addEventListener("click", function (e) {
      e.preventDefault();
      if (area && area.textContent.trim()
          && !window.confirm("Clear this document? Unsaved typing will be lost.")) {
        return;
      }
      if (area) {
        area.innerHTML = "";
        area.removeAttribute("data-size");
      }
      var hidden = document.getElementById("doc-body");
      if (hidden) { hidden.value = ""; }
      if (titleInput) { titleInput.value = ""; }
      if (form.querySelector("[name='project_id']")) {
        // Clear means "start a brand new document": drop the saved id so the
        // next Save creates a fresh one instead of overwriting.
        form.removeChild(form.querySelector("[name='project_id']"));
      }
      if (area) { area.focus(); }
    });
  }
})();
