/* DERB MOBILE - small, dependency-free UI helpers.
   Kept minimal on purpose: the app must stay fast on low-spec phones. */
(function () {
  "use strict";

  // Mark standalone (added-to-home-screen) mode so CSS can tune the app bar.
  if (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) {
    document.documentElement.classList.add("is-standalone");
  }

  // Tapping a tile/link twice quickly should not zoom the page mid-workflow.
  var lastTouch = 0;
  document.addEventListener(
    "touchend",
    function (e) {
      var now = Date.now();
      if (now - lastTouch < 300 && e.target.closest("a, .tile, .btn")) {
        e.preventDefault();
      }
      lastTouch = now;
    },
    { passive: false }
  );

  // Tiny toast helper used by later phases (save/export feedback).
  window.DERB = {
    toast: function (message, ms) {
      var el = document.getElementById("derb-toast");
      if (!el) {
        el = document.createElement("div");
        el.id = "derb-toast";
        el.setAttribute("role", "status");
        el.style.cssText =
          "position:fixed;left:50%;bottom:calc(20px + env(safe-area-inset-bottom));" +
          "transform:translateX(-50%);background:#0b2545;color:#fff;padding:11px 16px;" +
          "border-radius:12px;font:600 14px/1.3 system-ui,sans-serif;box-shadow:0 6px 20px rgba(0,0,0,.28);" +
          "z-index:100;max-width:88%;text-align:center;transition:opacity .2s ease;opacity:0";
        document.body.appendChild(el);
      }
      el.textContent = message;
      el.style.opacity = "1";
      clearTimeout(el._t);
      el._t = setTimeout(function () {
        el.style.opacity = "0";
      }, ms || 2200);
    },
  };
})();
