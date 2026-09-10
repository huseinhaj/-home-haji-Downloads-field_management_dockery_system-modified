/* Scoresheet Scanner — in-app multi-page document capture with
 * CamScanner-style auto edge detection, perspective correction and
 * enhancement.
 *
 * Flow: photograph each page with the phone's real camera -> the widget
 * finds the paper's four corners (adjustable by hand) -> warps it to a
 * straight rectangle and cleans it up (deskew + crop + contrast, or a
 * hard black & white "scan" look) -> stitches every page into ONE PDF
 * (jsPDF) -> hands that File to a callback for the existing OCR upload
 * path. Nothing on the server changes.
 *
 * Both heavy libraries (OpenCV.js, jsPDF) are served from this app's own
 * static files and loaded lazily the first time a scan is opened, so a
 * user who never scans pays nothing and there is no external CDN.
 *
 * Usage:
 *   ScoresheetScanner.open({
 *     lang: 'sw',
 *     filename: 'scoresheet',
 *     jspdfUrl:  '{% static "results/vendor/jspdf.umd.min.js" %}',
 *     opencvUrl: '{% static "results/vendor/opencv.js" %}',
 *     onComplete: function (pdfFile) { ... }
 *   });
 */
(function () {
  'use strict';
  if (window.ScoresheetScanner) return;

  var STYLE_ID = 'scoresheet-scanner-style';
  var WORK_EDGE = 2400;   // working resolution of the source photo (px)
  var DETECT_EDGE = 900;  // downscale used only for corner detection
  var OUT_EDGE = 2200;    // final per-page image long edge in the PDF
  var JPEG_QUALITY = 0.9;

  var STR = {
    sw: {
      title: 'Scan Scoresheet (kurasa nyingi)',
      hint: 'Bonyeza "Piga picha ya ukurasa" — kamera ya simu yako itafunguka. Piga picha ya ukurasa mzima kwenye mwanga wa kutosha. Mfumo utakata pembe na kunyoosha kama scanner.',
      capture: '📸 Piga picha ya ukurasa',
      addMore: '📸 Ongeza ukurasa mwingine',
      finish: 'Maliza',
      cancel: 'Ghairi',
      pagesLabel: 'Kurasa',
      empty: 'Bado hakuna ukurasa. Bonyeza kitufe hapo juu upige picha ya ukurasa wa kwanza.',
      building: 'Inaunganisha kurasa kuwa PDF moja…',
      needPage: 'Piga angalau ukurasa mmoja kwanza.',
      close: 'Funga',
      pdfError: 'Imeshindwa kuandaa PDF. Jaribu tena.',
      imgError: 'Picha haikusomeka. Jaribu tena.',
      deletePage: 'Futa ukurasa huu',
      loadingCv: 'Inapakia kifaa cha kuboresha picha (mara ya kwanza tu)…',
      cvFailed: 'Kifaa cha kuboresha hakikupakia — picha itatumika bila kukatwa.',
      editTitle: 'Rekebisha pembe za karatasi',
      editHint: 'Vuta viduara kwenye pembe nne za karatasi. Kisha bonyeza "Tumia".',
      bw: 'Nyeusi–nyeupe (kama scan)',
      use: '✓ Tumia',
      noCrop: 'Bila kukata',
      retake: '↻ Rudia',
      processing: 'Inachakata…'
    },
    en: {
      title: 'Scan Scoresheet (multi-page)',
      hint: 'Tap "Capture page" — your phone camera opens. Photograph the whole page in good light. The system crops and straightens it like a scanner.',
      capture: '📸 Capture page',
      addMore: '📸 Add another page',
      finish: 'Done',
      cancel: 'Cancel',
      pagesLabel: 'Pages',
      empty: 'No pages yet. Tap the button above to photograph the first page.',
      building: 'Combining pages into one PDF…',
      needPage: 'Capture at least one page first.',
      close: 'Close',
      pdfError: 'Could not build the PDF. Please try again.',
      imgError: 'Could not read the image. Try again.',
      deletePage: 'Delete this page',
      loadingCv: 'Loading the image-enhancement engine (first time only)…',
      cvFailed: 'Enhancement engine did not load — the photo will be used without cropping.',
      editTitle: 'Adjust the paper corners',
      editHint: 'Drag the dots to the four corners of the paper, then tap "Use".',
      bw: 'Black & white (scan look)',
      use: '✓ Use',
      noCrop: 'Keep full photo',
      retake: '↻ Retake',
      processing: 'Processing…'
    }
  };

  /* ---------- lazy library loading ------------------------------------ */

  function loadScript(url) {
    return new Promise(function (resolve, reject) {
      if (!url) { reject(new Error('missing url')); return; }
      var s = document.createElement('script');
      s.src = url;
      s.async = true;
      s.onload = function () { resolve(); };
      s.onerror = function () { reject(new Error('load failed: ' + url)); };
      document.head.appendChild(s);
    });
  }

  var jspdfP = null;
  function loadJsPDF(url) {
    if (window.jspdf && window.jspdf.jsPDF) return Promise.resolve(window.jspdf.jsPDF);
    if (!jspdfP) {
      jspdfP = loadScript(url).then(function () {
        if (window.jspdf && window.jspdf.jsPDF) return window.jspdf.jsPDF;
        throw new Error('jsPDF global missing');
      }).catch(function (e) { jspdfP = null; throw e; });
    }
    return jspdfP;
  }

  var cvP = null;
  function loadOpenCV(url) {
    if (window.cv && window.cv.Mat) return Promise.resolve(window.cv);
    if (!cvP) {
      cvP = loadScript(url).then(function () {
        return new Promise(function (resolve, reject) {
          var tries = 0;
          (function wait() {
            if (window.cv && window.cv.Mat) { resolve(window.cv); return; }
            if (window.cv && typeof window.cv.then === 'function') {
              window.cv.then(function (c) { resolve(c || window.cv); }, reject);
              return;
            }
            if (tries++ > 800) { reject(new Error('OpenCV init timeout')); return; }
            setTimeout(wait, 50);
          })();
        });
      }).catch(function (e) { cvP = null; throw e; });
    }
    return cvP;
  }

  /* ---------- geometry + OpenCV helpers ----------------------------- */

  function orderCorners(pts) {
    var bySum = pts.slice().sort(function (a, b) { return (a.x + a.y) - (b.x + b.y); });
    var byDiff = pts.slice().sort(function (a, b) { return (a.y - a.x) - (b.y - b.x); });
    return { tl: bySum[0], br: bySum[3], tr: byDiff[0], bl: byDiff[3] };
  }

  // Returns [{x,y}*4] in srcMat pixel coords, or null.
  function detectQuad(cv, srcMat) {
    var ratio = DETECT_EDGE / Math.max(srcMat.cols, srcMat.rows);
    if (ratio > 1) ratio = 1;
    var small = new cv.Mat();
    cv.resize(srcMat, small, new cv.Size(Math.round(srcMat.cols * ratio), Math.round(srcMat.rows * ratio)), 0, 0, cv.INTER_AREA);

    var gray = new cv.Mat(), blur = new cv.Mat(), edges = new cv.Mat();
    cv.cvtColor(small, gray, cv.COLOR_RGBA2GRAY);
    cv.GaussianBlur(gray, blur, new cv.Size(5, 5), 0);
    cv.Canny(blur, edges, 50, 150);
    var k = cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(5, 5));
    cv.dilate(edges, edges, k);

    var contours = new cv.MatVector(), hier = new cv.Mat();
    cv.findContours(edges, contours, hier, cv.RETR_LIST, cv.CHAIN_APPROX_SIMPLE);
    var imgArea = small.rows * small.cols;
    var best = null, bestArea = 0;
    for (var i = 0; i < contours.size(); i++) {
      var c = contours.get(i);
      var area = cv.contourArea(c);
      if (area > imgArea * 0.15) {
        var peri = cv.arcLength(c, true);
        var approx = new cv.Mat();
        cv.approxPolyDP(c, approx, 0.02 * peri, true);
        if (approx.rows === 4 && cv.isContourConvex(approx) && area > bestArea) {
          if (best) best.delete();
          best = approx; bestArea = area;
        } else {
          approx.delete();
        }
      }
      c.delete();
    }

    var pts = null;
    if (best) {
      pts = [];
      for (var j = 0; j < 4; j++) {
        pts.push({ x: best.intAt(j, 0) / ratio, y: best.intAt(j, 1) / ratio });
      }
      best.delete();
    }
    small.delete(); gray.delete(); blur.delete(); edges.delete(); k.delete();
    contours.delete(); hier.delete();
    return pts;
  }

  // Warp the quad to a straight rectangle and clean it up. Returns a canvas.
  function warpAndEnhance(cv, srcMat, quad, bw) {
    var o = orderCorners(quad);
    var wA = Math.hypot(o.br.x - o.bl.x, o.br.y - o.bl.y);
    var wB = Math.hypot(o.tr.x - o.tl.x, o.tr.y - o.tl.y);
    var hA = Math.hypot(o.tr.x - o.br.x, o.tr.y - o.br.y);
    var hB = Math.hypot(o.tl.x - o.bl.x, o.tl.y - o.bl.y);
    var W = Math.max(1, Math.round(Math.max(wA, wB)));
    var H = Math.max(1, Math.round(Math.max(hA, hB)));

    var srcTri = cv.matFromArray(4, 1, cv.CV_32FC2,
      [o.tl.x, o.tl.y, o.tr.x, o.tr.y, o.br.x, o.br.y, o.bl.x, o.bl.y]);
    var dstTri = cv.matFromArray(4, 1, cv.CV_32FC2, [0, 0, W, 0, W, H, 0, H]);
    var M = cv.getPerspectiveTransform(srcTri, dstTri);
    var warped = new cv.Mat();
    cv.warpPerspective(srcMat, warped, M, new cv.Size(W, H),
      cv.INTER_LINEAR, cv.BORDER_CONSTANT, new cv.Scalar(255, 255, 255, 255));

    var gray = new cv.Mat();
    cv.cvtColor(warped, gray, cv.COLOR_RGBA2GRAY);
    var out = new cv.Mat();
    if (bw) {
      cv.adaptiveThreshold(gray, out, 255, cv.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv.THRESH_BINARY, 25, 12);
    } else {
      var clahe = new cv.CLAHE(2.0, new cv.Size(8, 8));
      clahe.apply(gray, out);
      clahe.delete();
      cv.normalize(out, out, 0, 255, cv.NORM_MINMAX);
    }

    var canvas = document.createElement('canvas');
    cv.imshow(canvas, out);

    srcTri.delete(); dstTri.delete(); M.delete(); warped.delete();
    gray.delete(); out.delete();
    return canvas;
  }

  function enhanceOnly(cv, srcMat, bw) {
    var gray = new cv.Mat(), out = new cv.Mat();
    cv.cvtColor(srcMat, gray, cv.COLOR_RGBA2GRAY);
    if (bw) {
      cv.adaptiveThreshold(gray, out, 255, cv.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv.THRESH_BINARY, 25, 12);
    } else {
      var clahe = new cv.CLAHE(2.0, new cv.Size(8, 8));
      clahe.apply(gray, out);
      clahe.delete();
      cv.normalize(out, out, 0, 255, cv.NORM_MINMAX);
    }
    var canvas = document.createElement('canvas');
    cv.imshow(canvas, out);
    gray.delete(); out.delete();
    return canvas;
  }

  /* ---------- generic canvas helpers -------------------------------- */

  function imageFromFile(file) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () { URL.revokeObjectURL(url); resolve(img); };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error('decode failed')); };
      img.src = url;
    });
  }

  function imageToCanvas(img, maxEdge) {
    var w = img.naturalWidth || img.width;
    var h = img.naturalHeight || img.height;
    var s = Math.min(1, maxEdge / Math.max(w, h));
    var c = document.createElement('canvas');
    c.width = Math.max(1, Math.round(w * s));
    c.height = Math.max(1, Math.round(h * s));
    c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
    return c;
  }

  function canvasToJpeg(canvas, maxEdge) {
    var c = canvas;
    if (Math.max(canvas.width, canvas.height) > maxEdge) {
      var s = maxEdge / Math.max(canvas.width, canvas.height);
      c = document.createElement('canvas');
      c.width = Math.round(canvas.width * s);
      c.height = Math.round(canvas.height * s);
      c.getContext('2d').drawImage(canvas, 0, 0, c.width, c.height);
    }
    return { dataUrl: c.toDataURL('image/jpeg', JPEG_QUALITY), w: c.width, h: c.height };
  }

  /* ---------- styles ---------------------------------------------- */

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var css = '' +
      '.ssc-overlay{position:fixed;inset:0;z-index:2147483000;background:rgba(8,12,18,0.92);display:flex;align-items:stretch;justify-content:center;font-family:inherit;}' +
      '.ssc-panel{background:#fff;color:#1a1a1a;width:100%;max-width:640px;display:flex;flex-direction:column;max-height:100%;}' +
      '.ssc-head{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:#1F7A3D;color:#fff;}' +
      '.ssc-head h3{margin:0;font-size:0.98rem;font-weight:700;}' +
      '.ssc-x{background:none;border:none;color:#fff;font-size:1.5rem;line-height:1;padding:2px 6px;cursor:pointer;}' +
      '.ssc-body{padding:14px 16px;overflow-y:auto;flex:1;}' +
      '.ssc-hint{font-size:0.86rem;line-height:1.5;color:#333;margin-bottom:12px;}' +
      '.ssc-cap{position:relative;display:flex;align-items:center;justify-content:center;width:100%;min-height:54px;box-sizing:border-box;border:none;border-radius:6px;padding:15px;font-size:1rem;font-weight:700;background:#24508a;color:#fff;text-align:center;cursor:pointer;overflow:hidden;-webkit-tap-highlight-color:rgba(0,0,0,0.15);}' +
      '.ssc-cap input[type=file]{position:absolute;top:0;left:0;width:100%;height:100%;margin:0;padding:0;opacity:0;font-size:0;cursor:pointer;z-index:2;}' +
      '.ssc-cap .ssc-cap-t{position:relative;z-index:1;pointer-events:none;}' +
      '.ssc-cap.is-busy{opacity:0.5;pointer-events:none;}' +
      '.ssc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(88px,1fr));gap:10px;margin-top:14px;}' +
      '.ssc-empty{margin-top:14px;font-size:0.82rem;color:#888;text-align:center;padding:18px 8px;border:1px dashed #ccc;border-radius:6px;}' +
      '.ssc-thumb{position:relative;border:1px solid #d5dbe0;border-radius:6px;overflow:hidden;background:#f4f6f8;aspect-ratio:3/4;}' +
      '.ssc-thumb img{width:100%;height:100%;object-fit:cover;display:block;}' +
      '.ssc-thumb .n{position:absolute;left:3px;bottom:3px;font-size:0.7rem;font-weight:700;color:#fff;background:rgba(0,0,0,0.6);padding:0 6px;border-radius:3px;}' +
      '.ssc-thumb .del{position:absolute;top:2px;right:2px;width:20px;height:20px;border:none;border-radius:50%;background:rgba(192,57,43,0.95);color:#fff;font-size:0.8rem;line-height:20px;padding:0;cursor:pointer;}' +
      '.ssc-foot{display:flex;align-items:center;gap:10px;padding:12px 16px;border-top:1px solid #e6e6e6;flex-wrap:wrap;}' +
      '.ssc-count{font-size:0.88rem;font-weight:700;color:#333;flex:1;}' +
      '.ssc-btn{border:none;border-radius:6px;padding:11px 18px;font-size:0.9rem;font-weight:700;cursor:pointer;}' +
      '.ssc-btn[disabled]{opacity:0.45;cursor:default;}' +
      '.ssc-ok{background:#1F7A3D;color:#fff;}' +
      '.ssc-no{background:#eceff1;color:#333;}' +
      '.ssc-busy{margin-top:14px;font-size:0.9rem;color:#24508a;font-weight:700;text-align:center;}' +
      /* editor */
      '.ssc-editwrap{position:relative;width:100%;touch-action:none;background:#222;border-radius:6px;overflow:hidden;}' +
      '.ssc-editwrap canvas.pic{display:block;width:100%;height:auto;}' +
      '.ssc-editwrap canvas.lines{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;}' +
      '.ssc-handle{position:absolute;width:30px;height:30px;margin:-15px 0 0 -15px;border:3px solid #24508a;border-radius:50%;background:rgba(255,255,255,0.55);box-shadow:0 0 0 2px rgba(0,0,0,0.35);cursor:grab;touch-action:none;}' +
      '.ssc-editbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:12px;}' +
      '.ssc-editbar .ssc-btn{padding:10px 14px;font-size:0.86rem;}' +
      '.ssc-toggle{display:flex;align-items:center;gap:6px;font-size:0.82rem;color:#333;margin-top:10px;}';
    var st = document.createElement('style');
    st.id = STYLE_ID;
    st.textContent = css;
    document.head.appendChild(st);
  }

  /* ---------- per-photo editor ------------------------------------ */

  // Resolves with {dataUrl,w,h} for one accepted page, or null if the
  // user chose to retake.
  function editPage(cv, file, t, defaultBw) {
    return new Promise(function (resolve, reject) {
      imageFromFile(file).then(function (img) {
        var work = imageToCanvas(img, WORK_EDGE);        // source canvas
        var srcMat = cv ? cv.imread(work) : null;

        // initial corners (image coords)
        var quad = null;
        if (srcMat) {
          try { quad = detectQuad(cv, srcMat); } catch (e) { quad = null; }
        }
        if (!quad) {
          var mx = work.width * 0.06, my = work.height * 0.06;
          quad = [
            { x: mx, y: my },
            { x: work.width - mx, y: my },
            { x: work.width - mx, y: work.height - my },
            { x: mx, y: work.height - my }
          ];
        } else {
          var oc = orderCorners(quad);
          quad = [oc.tl, oc.tr, oc.br, oc.bl];
        }

        // ---- build editor DOM ----
        var wrap = document.createElement('div');
        wrap.className = 'ssc-editwrap';
        var pic = document.createElement('canvas');
        pic.className = 'pic';
        pic.width = work.width; pic.height = work.height;
        pic.getContext('2d').drawImage(work, 0, 0);
        var lines = document.createElement('canvas');
        lines.className = 'lines';
        lines.width = work.width; lines.height = work.height;
        wrap.appendChild(pic);
        wrap.appendChild(lines);

        var handles = quad.map(function () {
          var h = document.createElement('div');
          h.className = 'ssc-handle';
          wrap.appendChild(h);
          return h;
        });

        var box = document.createElement('div');
        box.innerHTML =
          '<p class="ssc-hint" style="margin:0 0 8px;"><strong>' + t.editTitle + '</strong><br>' + t.editHint + '</p>';
        box.appendChild(wrap);
        var toggle = document.createElement('label');
        toggle.className = 'ssc-toggle';
        toggle.innerHTML = '<input type="checkbox"' + (defaultBw ? ' checked' : '') + '> ' + t.bw;
        box.appendChild(toggle);
        var bar = document.createElement('div');
        bar.className = 'ssc-editbar';
        bar.innerHTML =
          '<button type="button" class="ssc-btn ssc-no ssc-retake">' + t.retake + '</button>' +
          '<button type="button" class="ssc-btn ssc-no ssc-nocrop">' + t.noCrop + '</button>' +
          '<button type="button" class="ssc-btn ssc-ok ssc-use">' + t.use + '</button>' +
          '<span class="ssc-busy" style="display:none;margin:0 0 0 6px;">' + t.processing + '</span>';
        box.appendChild(bar);

        // ---- positioning: image coords -> displayed CSS px ----
        function scale() { return wrap.clientWidth / work.width; }
        function placeHandles() {
          var s = scale();
          handles.forEach(function (h, i) {
            h.style.left = (quad[i].x * s) + 'px';
            h.style.top = (quad[i].y * s) + 'px';
          });
          drawLines();
        }
        function drawLines() {
          var ctx = lines.getContext('2d');
          ctx.clearRect(0, 0, lines.width, lines.height);
          ctx.lineWidth = Math.max(2, work.width / 400);
          ctx.strokeStyle = 'rgba(36,80,138,0.95)';
          ctx.fillStyle = 'rgba(36,80,138,0.12)';
          ctx.beginPath();
          ctx.moveTo(quad[0].x, quad[0].y);
          for (var i = 1; i < 4; i++) ctx.lineTo(quad[i].x, quad[i].y);
          ctx.closePath();
          ctx.fill();
          ctx.stroke();
        }

        var dragIdx = -1;
        function onDown(i, ev) {
          ev.preventDefault();
          dragIdx = i;
          handles[i].style.cursor = 'grabbing';
        }
        function onMove(ev) {
          if (dragIdx < 0) return;
          ev.preventDefault();
          var pt = ev.touches ? ev.touches[0] : ev;
          var r = wrap.getBoundingClientRect();
          var s = scale();
          var x = (pt.clientX - r.left) / s;
          var y = (pt.clientY - r.top) / s;
          quad[dragIdx] = {
            x: Math.min(work.width, Math.max(0, x)),
            y: Math.min(work.height, Math.max(0, y))
          };
          placeHandles();
        }
        function onUp() {
          if (dragIdx > -1) handles[dragIdx].style.cursor = 'grab';
          dragIdx = -1;
        }
        handles.forEach(function (h, i) {
          h.addEventListener('mousedown', function (e) { onDown(i, e); });
          h.addEventListener('touchstart', function (e) { onDown(i, e); }, { passive: false });
        });
        document.addEventListener('mousemove', onMove);
        document.addEventListener('touchmove', onMove, { passive: false });
        document.addEventListener('mouseup', onUp);
        document.addEventListener('touchend', onUp);

        function cleanup() {
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('touchmove', onMove);
          document.removeEventListener('mouseup', onUp);
          document.removeEventListener('touchend', onUp);
          if (srcMat) srcMat.delete();
        }

        var busyEl = bar.querySelector('.ssc-busy');
        function finish(useCrop) {
          bar.querySelectorAll('button').forEach(function (b) { b.disabled = true; });
          busyEl.style.display = '';
          // let the browser paint the busy state
          setTimeout(function () {
            try {
              var bw = toggle.querySelector('input').checked;
              var outCanvas;
              if (!cv || !srcMat) {
                outCanvas = work; // no engine: raw photo
              } else if (useCrop) {
                outCanvas = warpAndEnhance(cv, srcMat, quad.map(function (p) { return { x: p.x, y: p.y }; }), bw);
              } else {
                outCanvas = enhanceOnly(cv, srcMat, bw);
              }
              var page = canvasToJpeg(outCanvas, OUT_EDGE);
              page.bw = bw;
              cleanup();
              resolve(page);
            } catch (err) {
              cleanup();
              reject(err);
            }
          }, 30);
        }

        bar.querySelector('.ssc-use').addEventListener('click', function () { finish(true); });
        bar.querySelector('.ssc-nocrop').addEventListener('click', function () { finish(false); });
        bar.querySelector('.ssc-retake').addEventListener('click', function () {
          cleanup();
          resolve(null);
        });

        // expose the built DOM to the caller via a temporary event
        editPage._mount(box, placeHandles);
      }).catch(reject);
    });
  }
  // set by open() so editPage can drop its UI into the panel
  editPage._mount = function () {};

  /* ---------- PDF ------------------------------------------------- */

  function buildPdf(jsPDF, pages) {
    var doc = new jsPDF({ unit: 'pt', format: 'a4', orientation: 'portrait' });
    var pw = doc.internal.pageSize.getWidth();
    var ph = doc.internal.pageSize.getHeight();
    for (var i = 0; i < pages.length; i++) {
      if (i > 0) doc.addPage();
      var p = pages[i];
      var s = Math.min(pw / p.w, ph / p.h);
      var dw = p.w * s, dh = p.h * s;
      doc.addImage(p.dataUrl, 'JPEG', (pw - dw) / 2, (ph - dh) / 2, dw, dh, undefined, 'FAST');
    }
    return doc.output('blob');
  }

  /* ---------- main --------------------------------------------- */

  function open(opts) {
    opts = opts || {};
    var lang = opts.lang === 'en' ? 'en' : 'sw';
    var t = STR[lang];
    var baseName = (opts.filename || 'scoresheet').replace(/[^\w.-]+/g, '_');
    var S = window.ScoresheetScanner;
    var jspdfUrl = opts.jspdfUrl || (S && S.jspdfUrl);
    var opencvUrl = opts.opencvUrl || (S && S.opencvUrl);
    var onComplete = typeof opts.onComplete === 'function' ? opts.onComplete : function () {};

    injectStyle();
    loadJsPDF(jspdfUrl).catch(function () {});
    var cvReady = loadOpenCV(opencvUrl); // may reject; handled at capture time
    cvReady.catch(function () {});

    var pages = [];
    var prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    var overlay = document.createElement('div');
    overlay.className = 'ssc-overlay';
    overlay.innerHTML = '' +
      '<div class="ssc-panel">' +
        '<div class="ssc-head"><h3>' + t.title + '</h3>' +
          '<button type="button" class="ssc-x" aria-label="' + t.close + '">&times;</button></div>' +
        '<div class="ssc-body">' +
          '<div class="ssc-main">' +
            '<p class="ssc-hint">' + t.hint + '</p>' +
            '<label class="ssc-cap"><span class="ssc-cap-t">' + t.capture + '</span>' +
              '<input type="file" accept="image/*" capture="environment"></label>' +
            '<div class="ssc-empty">' + t.empty + '</div>' +
            '<div class="ssc-grid" hidden></div>' +
            '<div class="ssc-busy" hidden></div>' +
          '</div>' +
          '<div class="ssc-edit" hidden></div>' +
        '</div>' +
        '<div class="ssc-foot">' +
          '<span class="ssc-count"></span>' +
          '<button type="button" class="ssc-btn ssc-no ssc-cancel">' + t.cancel + '</button>' +
          '<button type="button" class="ssc-btn ssc-ok ssc-done" disabled>' + t.finish + '</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);

    var mainSec = overlay.querySelector('.ssc-main');
    var editSec = overlay.querySelector('.ssc-edit');
    var capBtn = overlay.querySelector('.ssc-cap');          // the <label>
    var capText = overlay.querySelector('.ssc-cap-t');       // its text span
    var fileInput = overlay.querySelector('.ssc-cap input'); // real, tap-through
    var capBusyTimer = null;

    // A <label> has no "disabled"; use a class for the visual/blocking
    // state. Auto-clears after 45s so the button can never latch stuck.
    function setCapBusy(busy) {
      capBtn.classList.toggle('is-busy', !!busy);
      if (capBusyTimer) { clearTimeout(capBusyTimer); capBusyTimer = null; }
      if (busy) capBusyTimer = setTimeout(function () { capBtn.classList.remove('is-busy'); }, 45000);
    }

    // Swap the file input for a fresh clone after every pick. Some mobile
    // browsers will not re-open the camera for a second tap on the same
    // <input> element even after value='' — a pristine node always works.
    function armInput() {
      var fresh = fileInput.cloneNode(false);
      fresh.value = '';
      fresh.disabled = false;
      fileInput.parentNode.replaceChild(fresh, fileInput);
      fileInput = fresh;
      fileInput.addEventListener('change', onPick);
    }
    var grid = overlay.querySelector('.ssc-grid');
    var emptyEl = overlay.querySelector('.ssc-empty');
    var busyEl = mainSec.querySelector('.ssc-busy');
    var countEl = overlay.querySelector('.ssc-count');
    var doneBtn = overlay.querySelector('.ssc-done');
    var cancelBtn = overlay.querySelector('.ssc-cancel');
    var closeX = overlay.querySelector('.ssc-x');
    var lastBw = false;

    function close() {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }
    function onKey(e) { if (e.key === 'Escape') close(); }
    document.addEventListener('keydown', onKey);

    function redraw() {
      grid.innerHTML = '';
      pages.forEach(function (p, i) {
        var d = document.createElement('div');
        d.className = 'ssc-thumb';
        d.innerHTML = '<img alt=""><span class="n"></span>' +
          '<button type="button" class="del" title="' + t.deletePage + '">&times;</button>';
        d.querySelector('img').src = p.dataUrl;
        d.querySelector('.n').textContent = i + 1;
        d.querySelector('.del').addEventListener('click', function () {
          var idx = pages.indexOf(p);
          if (idx > -1) pages.splice(idx, 1);
          redraw();
        });
        grid.appendChild(d);
      });
      var has = pages.length > 0;
      grid.hidden = !has;
      emptyEl.hidden = has;
      countEl.textContent = t.pagesLabel + ': ' + pages.length;
      doneBtn.disabled = !has;
      doneBtn.textContent = t.finish + (has ? ' (' + pages.length + ')' : '');
      capText.textContent = has ? t.addMore : t.capture;
    }

    function showMain() { editSec.hidden = true; editSec.innerHTML = ''; mainSec.hidden = false; }
    function showEdit() { mainSec.hidden = true; editSec.hidden = false; }

    editPage._mount = function (dom, afterMount) {
      editSec.innerHTML = '';
      editSec.appendChild(dom);
      showEdit();
      // afterMount needs layout to have happened
      requestAnimationFrame(function () { afterMount(); });
    };

    // The real <input> sits transparently on top of the label, so the
    // user's tap opens the camera natively — no programmatic .click(),
    // which several mobile browsers ignore on a hidden input. After each
    // pick the input is swapped for a fresh clone (see armInput).
    function onPick() {
      var file = this.files && this.files[0];
      if (!file) { armInput(); return; }
      setCapBusy(true);
      busyEl.hidden = false;
      busyEl.textContent = t.processing;

      cvReady.then(function (cv) { return cv; }, function () {
        if (!open._warnedCv) { open._warnedCv = true; alert(t.cvFailed); }
        return null;
      }).then(function (cv) {
        busyEl.hidden = true;
        return editPage(cv, file, t, lastBw);
      }).then(function (page) {
        setCapBusy(false);
        showMain();
        if (page) { lastBw = !!page.bw; pages.push(page); }
        redraw();
        armInput();
      }).catch(function (err) {
        setCapBusy(false);
        busyEl.hidden = true;
        showMain();
        redraw();
        armInput();
        alert(t.imgError + '\n\n' + (err && err.message ? err.message : err));
      });
    }
    fileInput.addEventListener('change', onPick);

    cancelBtn.addEventListener('click', close);
    closeX.addEventListener('click', close);

    doneBtn.addEventListener('click', function () {
      if (!pages.length) { alert(t.needPage); return; }
      busyEl.hidden = false;
      busyEl.textContent = t.building;
      setCapBusy(true);
      doneBtn.disabled = true;
      cancelBtn.disabled = true;
      loadJsPDF(jspdfUrl).then(function (jsPDF) {
        var blob = buildPdf(jsPDF, pages);
        var f = new File([blob], baseName + '_' + Date.now() + '.pdf', { type: 'application/pdf' });
        close();
        onComplete(f);
      }).catch(function (err) {
        busyEl.hidden = true;
        setCapBusy(false);
        doneBtn.disabled = false;
        cancelBtn.disabled = false;
        alert(t.pdfError + '\n\n' + (err && err.message ? err.message : err));
      });
    });

    redraw();
  }

  window.ScoresheetScanner = { open: open, jspdfUrl: null, opencvUrl: null };
})();
