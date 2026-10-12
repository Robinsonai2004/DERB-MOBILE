/* DERB MOBILE - Graphic Design workspace.
   Offline only: no network calls. Handles the image preview, the print
   button and the PNG/JPG export (drawn on a <canvas> from the element spec
   the server embeds, so the download matches the preview). */
(function () {
  "use strict";

  var FONT_STACK = 'Arial, Helvetica, sans-serif';

  // ----------------------------------------------------------- print ----
  document.querySelectorAll('[data-role="print"]').forEach(function (btn) {
    btn.addEventListener("click", function () { window.print(); });
  });

  // ------------------------------------------------- image preview ------
  var input = document.getElementById("design-images");
  var previews = document.getElementById("design-previews");
  if (input && previews) {
    input.addEventListener("change", function () {
      previews.innerHTML = "";
      var files = input.files || [];
      for (var i = 0; i < files.length; i++) {
        var file = files[i];
        if (!file.type || file.type.indexOf("image/") !== 0) continue;
        var fig = document.createElement("figure");
        fig.className = "design-preview";
        var img = document.createElement("img");
        img.alt = file.name;
        img.src = URL.createObjectURL(file);
        fig.appendChild(img);
        previews.appendChild(fig);
      }
    });
  }

  // ------------------------------------------------- canvas export ------
  var dataEl = document.getElementById("design-layout-json");
  if (!dataEl) return;

  function loadImages(layout, done) {
    var map = {};
    var files = [];
    layout.elements.forEach(function (e) {
      if (e.kind === "photo" && e.url && files.indexOf(e.url) < 0) files.push(e.url);
    });
    if (!files.length) { done(map); return; }
    var remaining = files.length;
    files.forEach(function (url) {
      var img = new Image();
      img.onload = img.onerror = function () {
        map[url] = img;
        if (--remaining === 0) done(map);
      };
      img.src = url;
    });
  }

  function path(ctx, x, y, w, h, r) {
    if (r > 0 && ctx.roundRect) { ctx.beginPath(); ctx.roundRect(x, y, w, h, r); return; }
    ctx.beginPath();
    ctx.rect(x, y, w, h);
  }

  function fillRect(ctx, e, W) {
    ctx.save();
    if (e.opacity !== undefined) ctx.globalAlpha = e.opacity;
    path(ctx, e.x, e.y, e.w, e.h, e.radius || 0);
    if (e.fill2) {
      var g = e.grad_dir === "to right"
        ? ctx.createLinearGradient(e.x, 0, e.x + e.w, 0)
        : ctx.createLinearGradient(0, e.y, 0, e.y + e.h);
      g.addColorStop(0, e.fill);
      g.addColorStop(1, e.fill2);
      ctx.fillStyle = g;
    } else {
      ctx.fillStyle = e.fill;
    }
    ctx.fill();
    if (e.stroke) {
      ctx.lineWidth = e.stroke_w || 1;
      ctx.strokeStyle = e.stroke;
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawEllipse(ctx, e) {
    ctx.save();
    if (e.opacity !== undefined) ctx.globalAlpha = e.opacity;
    ctx.beginPath();
    ctx.ellipse(e.x + e.w / 2, e.y + e.h / 2, e.w / 2, e.h / 2, 0, 0, Math.PI * 2);
    ctx.fillStyle = e.fill;
    ctx.fill();
    if (e.stroke) {
      ctx.lineWidth = e.stroke_w || 1;
      ctx.strokeStyle = e.stroke;
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawPhoto(ctx, e, images) {
    var img = images[e.url];
    ctx.save();
    path(ctx, e.x, e.y, e.w, e.h, e.shape === "circle" ? Math.min(e.w, e.h) / 2 : (e.radius || 0));
    ctx.clip();
    if (img && img.width) {
      var scale = Math.max(e.w / img.width, e.h / img.height);
      var dw = img.width * scale;
      var dh = img.height * scale;
      ctx.drawImage(img, e.x + (e.w - dw) / 2, e.y + (e.h - dh) / 2, dw, dh);
    } else {
      ctx.fillStyle = "rgba(15,37,69,.12)";
      ctx.fillRect(e.x, e.y, e.w, e.h);
    }
    ctx.restore();
    if (e.border) {
      ctx.save();
      ctx.lineWidth = e.border_w || 2;
      ctx.strokeStyle = e.border;
      path(ctx, e.x, e.y, e.w, e.h, e.shape === "circle" ? Math.min(e.w, e.h) / 2 : (e.radius || 0));
      ctx.stroke();
      ctx.restore();
    }
  }

  function drawText(ctx, e, W) {
    var size = e.size;
    var lh = e.line_h || size * 1.16;
    var half = (lh - size) / 2;
    ctx.save();
    ctx.fillStyle = e.color;
    ctx.font = (e.weight === "700" || e.weight === "800" ? "bold " : "") +
               size + "px " + FONT_STACK;
    ctx.textAlign = e.align || "left";
    ctx.textBaseline = "alphabetic";
    if (e.tracking && "letterSpacing" in ctx) ctx.letterSpacing = e.tracking + "px";
    var x = e.align === "center" ? e.x + e.w / 2
          : e.align === "right" ? e.x + e.w
          : e.x;
    (e.lines || []).forEach(function (line, i) {
      var y = e.y + half + i * lh + size * 0.80;
      ctx.fillText(line, x, y);
    });
    ctx.restore();
  }

  function draw(layout, canvas, images) {
    var W = layout.width;
    var H = layout.height;
    canvas.width = W;
    canvas.height = H;
    var ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, W, H);
    layout.elements.forEach(function (e) {
      if (e.kind === "rect") fillRect(ctx, e, W);
      else if (e.kind === "ellipse") drawEllipse(ctx, e);
      else if (e.kind === "photo") drawPhoto(ctx, e, images);
      else if (e.kind === "text") drawText(ctx, e, W);
    });
  }

  function download(dataUrl, name) {
    var a = document.createElement("a");
    a.href = dataUrl;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  document.querySelectorAll("[data-export]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var fmt = btn.getAttribute("data-export");
      var layout;
      try { layout = JSON.parse(dataEl.textContent); } catch (e) { return; }
      var canvas = document.getElementById("design-canvas");
      if (!canvas) return;
      btn.disabled = true;
      loadImages(layout, function (map) {
        draw(layout, canvas, map);
        var mime = fmt === "jpg" ? "image/jpeg" : "image/png";
        var ext = fmt === "jpg" ? "jpg" : "png";
        download(canvas.toDataURL(mime, 0.94), "derb-design." + ext);
        btn.disabled = false;
      });
    });
  });
})();
