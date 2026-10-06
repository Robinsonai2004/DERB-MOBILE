/* ==========================================================================
   DERB MOBILE - CV editor behaviour
   Adds/removes repeatable entries and keeps counters in sync.
   No dependencies.
   ========================================================================== */
(function () {
  "use strict";

  function sectionOf(el) {
    return el.closest(".form-section");
  }

  function refresh(section) {
    if (!section) return;
    var entries = section.querySelector("[data-entries]");
    var count = section.querySelector("[data-count]");
    var note = section.querySelector("[data-empty-note]");
    if (!entries) return;
    var n = entries.querySelectorAll(".entry-card").length;
    if (count) count.textContent = String(n);
    if (note) note.style.display = n ? "none" : "";
  }

  function addEntry(key) {
    var section = document.querySelector('.form-section[data-section-key="' + key + '"]');
    if (!section) return;
    var entries = section.querySelector("[data-entries]");
    var tpl = section.querySelector('template[data-template="' + key + '"]');
    if (!entries || !tpl) return;

    var index = parseInt(entries.getAttribute("data-next") || "0", 10);
    var html = tpl.innerHTML
      .replace(/__i__/g, String(index))
      .replace(/__n__/g, String(index + 1));

    var holder = document.createElement("div");
    holder.innerHTML = html;
    var card = holder.querySelector(".entry-card");
    if (!card) return;
    entries.appendChild(card);

    entries.setAttribute("data-next", String(index + 1));
    refresh(section);

    // Focus the first field of the new entry so typing can start immediately.
    var first = card.querySelector("input, textarea, select");
    if (first) {
      try { first.focus(); } catch (e) { /* ignore */ }
      if (card.scrollIntoView) {
        card.scrollIntoView({ block: "center", behavior: "smooth" });
      }
    }
  }

  function removeEntry(card) {
    var section = sectionOf(card);
    card.parentNode.removeChild(card);
    refresh(section);
  }

  document.addEventListener("click", function (event) {
    var addBtn = event.target.closest("[data-add]");
    if (addBtn) {
      event.preventDefault();
      addEntry(addBtn.getAttribute("data-add"));
      return;
    }
    var removeBtn = event.target.closest("[data-remove]");
    if (removeBtn) {
      event.preventDefault();
      var card = removeBtn.closest(".entry-card");
      if (card) removeEntry(card);
    }
  });

  // Passport photograph preview.
  document.addEventListener("change", function (event) {
    var input = event.target;
    if (!input.matches || !input.matches("[data-photo-input]")) return;
    var preview = document.getElementById("photo-preview");
    if (!preview || !input.files || !input.files[0]) return;
    try {
      var url = URL.createObjectURL(input.files[0]);
      preview.innerHTML = '<img alt="Passport photograph">';
      preview.querySelector("img").src = url;
    } catch (e) { /* older WebView: leave the placeholder */ }
  });

  // Print / Save-as-PDF buttons (Phases 6 will add real PDF output).
  document.addEventListener("click", function (event) {
    var printBtn = event.target.closest("[data-print]");
    if (printBtn) {
      event.preventDefault();
      window.print();
    }
  });
})();
