/* DERB MOBILE - Letters & Documents helpers.
   Dependency-free; instant search runs entirely offline in the browser. */
(function () {
  "use strict";

  /* ------------------------------------------------ instant search ---- */
  var input = document.getElementById("letter-search");
  if (input) {
    var clearBtn = document.getElementById("letter-search-clear");
    var noResults = document.getElementById("letter-noresults");
    var cards = Array.prototype.slice.call(document.querySelectorAll(".lt-card"));
    var categories = Array.prototype.slice.call(document.querySelectorAll(".lt-category"));

    var applyFilter = function () {
      var q = (input.value || "").trim().toLowerCase();
      var terms = q.split(/\s+/);
      var anyVisible = false;

      cards.forEach(function (card) {
        var hay = card.getAttribute("data-search") || "";
        var hit = !q || terms.every(function (t) { return hay.indexOf(t) !== -1; });
        card.hidden = !hit;
        if (hit) { anyVisible = true; }
      });

      categories.forEach(function (section) {
        var visibleCards = section.querySelectorAll(".lt-card:not([hidden])");
        section.hidden = q !== "" && visibleCards.length === 0;
      });

      // Searching should surface matches from collapsed "View all" sections.
      document.querySelectorAll("[data-more]").forEach(function (d) {
        if (q) { d.open = true; }
      });

      if (noResults) { noResults.hidden = !q || anyVisible; }
      if (clearBtn) { clearBtn.hidden = !q; }
    };

    input.addEventListener("input", applyFilter);
    input.addEventListener("search", applyFilter);

    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        input.value = "";
        applyFilter();
        input.focus();
      });
    }

    if (input.value) { applyFilter(); }
  }

  /* ------------------------------------------------ print (preview) ---- */
  document.querySelectorAll("[data-print]").forEach(function (btn) {
    btn.addEventListener("click", function () { window.print(); });
  });
})();
