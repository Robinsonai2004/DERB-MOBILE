/* DERB MOBILE - Graphic Design workspace.
   Offline only: no network calls. Handles the image preview, the print
   button and the PNG/JPG export (drawn on a <canvas> from the layout JSON
   the server embeds, so the download matches the preview). */
(function () {
  "use strict";

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

  function wrapLines(ctx, text, maxWidth) {
    var lines = [];
    (text || "").split("\n").forEach(function (para) {
      var words = para.split(/\s+/);
      var line = "";
      words.forEach(function (word) {
        var test = line ? line + " " + word : word;
        if (ctx.measureText(test).width > maxWidth && line) {
          lines.push(line);
          line = word;
        } else {
          line = test;
        }
      });
      lines.push(line);
    });
    return lines;
  }

  function loadImages(images, done) {
    var map = {};
    if (!images.length) { done(map); return; }
    var remaining = images.length;
    images.forEach(function (rec) {
      var img = new Image();
      img.onload = img.onerror = function () {
        map[rec.filename] = img;
        if (--remaining === 0) done(map);
      };
      img.src = rec.url;
    });
  }

  function drawCover(ctx, img, x, y, w, h) {
    if (!img || !img.width) return;
    var scale = Math.max(w / img.width, h / img.height);
    var dw = img.width * scale;
    var dh = img.height * scale;
    ctx.save();
    ctx.beginPath();
    ctx.rect(x, y, w, h);
    ctx.clip();
    ctx.drawImage(img, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh);
    ctx.restore();
  }

  function draw(layout, canvas, images) {
    var W = layout.width;
    var H = layout.height;
    canvas.width = W;
    canvas.height = H;
    var ctx = canvas.getContext("2d");
    var p = layout.palette;
    var grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, p.bg1);
    grad.addColorStop(1, p.bg2);
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);

    var total = layout.blocks.reduce(function (s, b) { return s + b.flex; }, 0) || 1;
    var y = 0;
    layout.blocks.forEach(function (block) {
      var h = (block.flex / total) * H;
      drawBlock(ctx, block, 0, y, W, h, images);
      y += h;
    });
  }

  function drawBlock(ctx, block, x, y, W, h, images) {
    var pad = W * 0.06;
    ctx.save();
    ctx.beginPath();
    ctx.rect(x, y, W, h);
    ctx.clip();
    ctx.textBaseline = "top";

    if (block.kind === "header") {
      ctx.fillStyle = block.fill;
      ctx.fillRect(x, y, W, h);
      ctx.fillStyle = block.ink;
      ctx.textAlign = "center";
      var titleSize = W * 0.08;
      ctx.font = "800 " + titleSize + "px system-ui, Arial, sans-serif";
      var lines = wrapLines(ctx, block.title, W - pad * 2);
      var lineH = titleSize * 1.08;
      var subSize = W * 0.036;
      var blockH = lines.length * lineH + (block.subtitle ? subSize * 1.4 : 0);
      var ty = y + Math.max(pad * 0.6, (h - blockH) / 2);
      lines.forEach(function (line) {
        ctx.fillText(line, x + W / 2, ty);
        ty += lineH;
      });
      if (block.subtitle) {
        ctx.font = "600 " + subSize + "px system-ui, Arial, sans-serif";
        ctx.fillText(block.subtitle, x + W / 2, ty);
      }
    } else if (block.kind === "info") {
      ctx.textAlign = "left";
      var ly = y + pad * 0.5;
      block.rows.forEach(function (row) {
        ctx.fillStyle = block.muted;
        ctx.font = "700 " + W * 0.022 + "px system-ui, Arial, sans-serif";
        ctx.fillText(row.label.toUpperCase(), x + pad, ly);
        ly += W * 0.03;
        ctx.fillStyle = block.ink;
        ctx.font = "600 " + W * 0.034 + "px system-ui, Arial, sans-serif";
        wrapLines(ctx, row.value, W - pad * 2).forEach(function (ln) {
          ctx.fillText(ln, x + pad, ly);
          ly += W * 0.042;
        });
        ly += W * 0.012;
      });
    } else if (block.kind === "paragraph") {
      ctx.textAlign = "left";
      var py = y + pad * 0.4;
      if (block.heading) {
        ctx.fillStyle = block.muted;
        ctx.font = "700 " + W * 0.026 + "px system-ui, Arial, sans-serif";
        ctx.fillText(block.heading.toUpperCase(), x + pad, py);
        py += W * 0.036;
      }
      ctx.fillStyle = block.ink;
      ctx.font = "400 " + W * 0.032 + "px system-ui, Arial, sans-serif";
      wrapLines(ctx, block.text, W - pad * 2).forEach(function (ln) {
        ctx.fillText(ln, x + pad, py);
        py += W * 0.042;
      });
    } else if (block.kind === "gallery") {
      var cols = Math.max(1, block.columns);
      var gap = W * 0.02;
      var cellW = (W - pad * 2 - gap * (cols - 1)) / cols;
      var cellH = h - W * 0.04;
      block.images.forEach(function (rec, i) {
        var col = i % cols;
        var rowIdx = Math.floor(i / cols);
        drawCover(ctx, images[rec.filename], x + pad + col * (cellW + gap),
                  y + W * 0.02 + rowIdx * (cellH + gap), cellW, cellH);
      });
    } else if (block.kind === "footer") {
      ctx.fillStyle = block.fill;
      ctx.fillRect(x, y, W, h);
      ctx.fillStyle = block.ink;
      ctx.textAlign = "center";
      ctx.font = "700 " + W * 0.026 + "px system-ui, Arial, sans-serif";
      ctx.fillText((block.lines || []).join("  ·  "), x + W / 2, y + h / 2 - W * 0.015);
    }
    ctx.restore();
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
      var images = [];
      layout.blocks.forEach(function (b) { (b.images || []).forEach(function (im) { images.push(im); }); });
      btn.disabled = true;
      loadImages(images, function (map) {
        draw(layout, canvas, map);
        var mime = fmt === "jpg" ? "image/jpeg" : "image/png";
        var ext = fmt === "jpg" ? "jpg" : "png";
        download(canvas.toDataURL(mime, 0.92), "derb-design." + ext);
        btn.disabled = false;
      });
    });
  });
})();
