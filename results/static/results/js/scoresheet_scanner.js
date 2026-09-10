/* Scoresheet Scanner — in-app multi-page document capture.
 *
 * Photograph each page with the phone's real camera. The widget
 * auto-detects the paper, straightens it (perspective warp) and cleans
 * it up like a scanner, adds it to a page list, then stitches every page
 * into ONE PDF (jsPDF) and hands that File to a callback for the
 * existing OCR upload path. Nothing on the server changes.
 *
 * Robustness rules:
 *  - A captured page is ALWAYS added. If OpenCV is unavailable or throws,
 *    the plain (downscaled) photo is used instead — never a dead end.
 *  - The camera input is replaced with a fresh node after every shot so
 *    a second tap reliably re-opens the camera on mobile.
 *  - Both heavy libs (OpenCV.js, jsPDF) are served from this app's own
 *    static files and loaded lazily; there is no external CDN.
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
  var WORK_EDGE = 2200;
  var DETECT_EDGE = 900;
  var OUT_EDGE = 2000;
  var JPEG_QUALITY = 0.88;

  var STR = {
    sw: {
      title: 'Scan Scoresheet (kurasa nyingi)',
      hint: 'Bonyeza "Piga picha ya ukurasa" — kamera itafunguka. Piga picha ya ukurasa mzima kwenye mwanga mzuri. Mfumo utakata na kunyoosha wenyewe. Rudia kwa kila ukurasa, kisha "Maliza".',
      capture: '📸 Piga picha ya ukurasa',
      addMore: '📸 Ongeza ukurasa mwingine',
      finish: 'Maliza',
      cancel: 'Ghairi',
      pagesLabel: 'Kurasa',
      empty: 'Bado hakuna ukurasa.',
      processing: 'Inachakata ukurasa…',
      building: 'Inaunganisha kurasa kuwa PDF moja…',
      needPage: 'Piga angalau ukurasa mmoja kwanza.',
      close: 'Funga',
      pdfError: 'Imeshindwa kuandaa PDF. Jaribu tena.',
      imgError: 'Picha haikusomeka. Jaribu tena.',
      deletePage: 'Futa ukurasa huu',
      loadingCv: 'Inapakia kifaa cha kuboresha picha (mara ya kwanza tu)…',
      bw: 'Nyeusi–nyeupe (kama scan)'
    },
    en: {
      title: 'Scan Scoresheet (multi-page)',
      hint: 'Tap "Capture page" — the camera opens. Photograph the whole page in good light. The system crops and straightens it. Repeat for every page, then "Done".',
      capture: '📸 Capture page',
      addMore: '📸 Add another page',
      finish: 'Done',
      cancel: 'Cancel',
      pagesLabel: 'Pages',
      empty: 'No pages yet.',
      processing: 'Processing page…',
      building: 'Combining pages into one PDF…',
      needPage: 'Capture at least one page first.',
      close: 'Close',
      pdfError: 'Could not build the PDF. Please try again.',
      imgError: 'Could not read the image. Try again.',
      deletePage: 'Delete this page',
      loadingCv: 'Loading the image-enhancement engine (first time only)…',
      bw: 'Black & white (scan look)'
    }
  };

  /* ---------- lazy library loading -------------------------------- */

  function loadScript(url) {
    return new Promise(function (resolve, reject) {
      if (!url) { reject(new Error('missing url')); return; }
      var s = document.createElement('script');
      s.src = url; s.async = true;
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

  /* ---------- OpenCV image pipeline ------------------------------- */

  function orderCorners(pts) {
    var bySum = pts.slice().sort(function (a, b) { return (a.x + a.y) - (b.x + b.y); });
    var byDiff = pts.slice().sort(function (a, b) { return (a.y - a.x) - (b.y - b.x); });
    return { tl: bySum[0], br: bySum[3], tr: byDiff[0], bl: byDiff[3] };
  }

  function detectQuad(cv, srcMat) {
    var ratio = Math.min(1, DETECT_EDGE / Math.max(srcMat.cols, srcMat.rows));
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
    var imgArea = small.rows * small.cols, best = null, bestArea = 0;
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
        } else { approx.delete(); }
      }
      c.delete();
    }
    var pts = null;
    if (best) {
      pts = [];
      for (var j = 0; j < 4; j++) pts.push({ x: best.intAt(j, 0) / ratio, y: best.intAt(j, 1) / ratio });
      best.delete();
    }
    small.delete(); gray.delete(); blur.delete(); edges.delete(); k.delete();
    contours.delete(); hier.delete();
    return pts;
  }

  function cleanupMat(cv, gray, bw) {
    var out = new cv.Mat();
    if (bw) {
      cv.adaptiveThreshold(gray, out, 255, cv.ADAPTIVE_THRESH_GAUSSIAN_C, cv.THRESH_BINARY, 25, 12);
    } else {
      var clahe = new cv.CLAHE(2.0, new cv.Size(8, 8));
      clahe.apply(gray, out);
      clahe.delete();
      cv.normalize(out, out, 0, 255, cv.NORM_MINMAX);
    }
    return out;
  }

  function warpAndEnhance(cv, srcMat, quad, bw) {
    var o = orderCorners(quad);
    var W = Math.max(1, Math.round(Math.max(
      Math.hypot(o.br.x - o.bl.x, o.br.y - o.bl.y),
      Math.hypot(o.tr.x - o.tl.x, o.tr.y - o.tl.y))));
    var H = Math.max(1, Math.round(Math.max(
      Math.hypot(o.tr.x - o.br.x, o.tr.y - o.br.y),
      Math.hypot(o.tl.x - o.bl.x, o.tl.y - o.bl.y))));
    var srcTri = cv.matFromArray(4, 1, cv.CV_32FC2,
      [o.tl.x, o.tl.y, o.tr.x, o.tr.y, o.br.x, o.br.y, o.bl.x, o.bl.y]);
    var dstTri = cv.matFromArray(4, 1, cv.CV_32FC2, [0, 0, W, 0, W, H, 0, H]);
    var M = cv.getPerspectiveTransform(srcTri, dstTri);
    var warped = new cv.Mat();
    cv.warpPerspective(srcMat, warped, M, new cv.Size(W, H),
      cv.INTER_LINEAR, cv.BORDER_CONSTANT, new cv.Scalar(255, 255, 255, 255));
    var gray = new cv.Mat();
    cv.cvtColor(warped, gray, cv.COLOR_RGBA2GRAY);
    var out = cleanupMat(cv, gray, bw);
    var canvas = document.createElement('canvas');
    cv.imshow(canvas, out);
    srcTri.delete(); dstTri.delete(); M.delete(); warped.delete(); gray.delete(); out.delete();
    return canvas;
  }

  function enhanceOnly(cv, srcMat, bw) {
    var gray = new cv.Mat();
    cv.cvtColor(srcMat, gray, cv.COLOR_RGBA2GRAY);
    var out = cleanupMat(cv, gray, bw);
    var canvas = document.createElement('canvas');
    cv.imshow(canvas, out);
    gray.delete(); out.delete();
    return canvas;
  }

  /* ---------- canvas helpers ------------------------------------- */

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
    var w = img.naturalWidth || img.width, h = img.naturalHeight || img.height;
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

  /* ---------- process one captured photo ----------------------- */

  // Always resolves with {dataUrl,w,h}. OpenCV is best-effort; any
  // failure falls back to the plain downscaled photo.
  function processPage(cv, file, bw) {
    return imageFromFile(file).then(function (img) {
      var work = imageToCanvas(img, WORK_EDGE);
      var outCanvas = work;
      if (cv && cv.Mat) {
        var srcMat = null;
        try {
          srcMat = cv.imread(work);
          var quad = null;
          try { quad = detectQuad(cv, srcMat); } catch (e) { quad = null; }
          if (quad) {
            var oc = orderCorners(quad);
            outCanvas = warpAndEnhance(cv, srcMat, [oc.tl, oc.tr, oc.br, oc.bl], bw);
          } else {
            outCanvas = enhanceOnly(cv, srcMat, bw);
          }
        } catch (e) {
          outCanvas = work; // give up on enhancement, keep the raw photo
        } finally {
          if (srcMat) { try { srcMat.delete(); } catch (e2) {} }
        }
      }
      return canvasToJpeg(outCanvas, OUT_EDGE);
    });
  }

  /* ---------- PDF --------------------------------------------- */

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

  /* ---------- styles ---------------------------------------- */

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var css = '' +
      '.ssc-overlay{position:fixed;inset:0;z-index:2147483000;background:rgba(8,12,18,0.92);display:flex;align-items:stretch;justify-content:center;font-family:inherit;}' +
      '.ssc-panel{background:#fff;color:#1a1a1a;width:100%;max-width:640px;display:flex;flex-direction:column;max-height:100%;}' +
      '.ssc-head{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:#1F7A3D;color:#fff;}' +
      '.ssc-head h3{margin:0;font-size:0.98rem;font-weight:700;}' +
      '.ssc-x{background:none;border:none;color:#fff;font-size:1.5rem;line-height:1;padding:2px 6px;cursor:pointer;}' +
      '.ssc-body{padding:14px 16px;overflow-y:auto;flex:1;}' +
      '.ssc-hint{font-size:0.86rem;line-height:1.5;color:#333;margin:0 0 12px;}' +
      '.ssc-toggle{display:flex;align-items:center;gap:7px;font-size:0.86rem;color:#333;margin:0 0 12px;}' +
      '.ssc-cap{position:relative;display:flex;align-items:center;justify-content:center;width:100%;min-height:56px;box-sizing:border-box;border:none;border-radius:6px;padding:15px;font-size:1rem;font-weight:700;background:#24508a;color:#fff;text-align:center;cursor:pointer;overflow:hidden;-webkit-tap-highlight-color:rgba(0,0,0,0.15);}' +
      '.ssc-cap input[type=file]{position:absolute;top:0;left:0;width:100%;height:100%;margin:0;padding:0;opacity:0;font-size:0;cursor:pointer;z-index:2;}' +
      '.ssc-cap .ssc-cap-t{position:relative;z-index:1;pointer-events:none;}' +
      '.ssc-cap.is-busy{opacity:0.5;pointer-events:none;}' +
      '.ssc-note{font-size:0.8rem;color:#24508a;font-weight:700;margin:10px 0 0;text-align:center;}' +
      '.ssc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(88px,1fr));gap:10px;margin-top:14px;}' +
      '.ssc-empty{margin-top:14px;font-size:0.82rem;color:#888;text-align:center;padding:18px 8px;border:1px dashed #ccc;border-radius:6px;}' +
      '.ssc-thumb{position:relative;border:1px solid #d5dbe0;border-radius:6px;overflow:hidden;background:#f4f6f8;aspect-ratio:3/4;}' +
      '.ssc-thumb img{width:100%;height:100%;object-fit:cover;display:block;}' +
      '.ssc-thumb .n{position:absolute;left:3px;bottom:3px;font-size:0.7rem;font-weight:700;color:#fff;background:rgba(0,0,0,0.6);padding:0 6px;border-radius:3px;}' +
      '.ssc-thumb .del{position:absolute;top:2px;right:2px;width:22px;height:22px;border:none;border-radius:50%;background:rgba(192,57,43,0.95);color:#fff;font-size:0.85rem;line-height:22px;padding:0;cursor:pointer;}' +
      '.ssc-foot{display:flex;align-items:center;gap:10px;padding:12px 16px;border-top:1px solid #e6e6e6;flex-wrap:wrap;}' +
      '.ssc-count{font-size:0.9rem;font-weight:700;color:#333;flex:1;}' +
      '.ssc-btn{border:none;border-radius:6px;padding:11px 18px;font-size:0.9rem;font-weight:700;cursor:pointer;}' +
      '.ssc-btn[disabled]{opacity:0.45;cursor:default;}' +
      '.ssc-ok{background:#1F7A3D;color:#fff;}' +
      '.ssc-no{background:#eceff1;color:#333;}' +
      '.ssc-busy{margin-top:14px;font-size:0.9rem;color:#24508a;font-weight:700;text-align:center;}';
    var st = document.createElement('style');
    st.id = STYLE_ID;
    st.textContent = css;
    document.head.appendChild(st);
  }

  /* ---------- main ----------------------------------------- */

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

    var cvInstance = null;
    var cvSettled = false;
    var cvReady = loadOpenCV(opencvUrl).then(function (cv) {
      cvInstance = cv; cvSettled = true; return cv;
    }, function () { cvSettled = true; return null; });

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
          '<p class="ssc-hint">' + t.hint + '</p>' +
          '<label class="ssc-toggle"><input type="checkbox" class="ssc-bw"> ' + t.bw + '</label>' +
          '<label class="ssc-cap"><span class="ssc-cap-t">' + t.capture + '</span>' +
            '<input type="file" accept="image/*" capture="environment"></label>' +
          '<div class="ssc-note" hidden></div>' +
          '<div class="ssc-busy" hidden></div>' +
          '<div class="ssc-empty">' + t.empty + '</div>' +
          '<div class="ssc-grid" hidden></div>' +
        '</div>' +
        '<div class="ssc-foot">' +
          '<span class="ssc-count"></span>' +
          '<button type="button" class="ssc-btn ssc-no ssc-cancel">' + t.cancel + '</button>' +
          '<button type="button" class="ssc-btn ssc-ok ssc-done" disabled>' + t.finish + '</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);

    var capBtn = overlay.querySelector('.ssc-cap');
    var capText = overlay.querySelector('.ssc-cap-t');
    var fileInput = overlay.querySelector('.ssc-cap input');
    var bwCb = overlay.querySelector('.ssc-bw');
    var noteEl = overlay.querySelector('.ssc-note');
    var busyEl = overlay.querySelector('.ssc-busy');
    var grid = overlay.querySelector('.ssc-grid');
    var emptyEl = overlay.querySelector('.ssc-empty');
    var countEl = overlay.querySelector('.ssc-count');
    var doneBtn = overlay.querySelector('.ssc-done');
    var cancelBtn = overlay.querySelector('.ssc-cancel');
    var closeX = overlay.querySelector('.ssc-x');
    var capBusyTimer = null;

    function setCapBusy(busy) {
      capBtn.classList.toggle('is-busy', !!busy);
      if (capBusyTimer) { clearTimeout(capBusyTimer); capBusyTimer = null; }
      if (busy) capBusyTimer = setTimeout(function () { capBtn.classList.remove('is-busy'); }, 45000);
    }

    function armInput() {
      var fresh = fileInput.cloneNode(false);
      fresh.value = '';
      fresh.disabled = false;
      fileInput.parentNode.replaceChild(fresh, fileInput);
      fileInput = fresh;
      fileInput.addEventListener('change', onPick);
    }

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

    function onPick() {
      var file = this.files && this.files[0];
      if (!file) { armInput(); return; }

      setCapBusy(true);
      busyEl.hidden = false;
      busyEl.textContent = t.processing;
      if (!cvSettled) { noteEl.hidden = false; noteEl.textContent = t.loadingCv; }

      var bw = !!bwCb.checked;
      cvReady.then(function () {
        noteEl.hidden = true;
        return processPage(cvInstance, file, bw);
      }).then(function (page) {
        pages.push(page);
      }).catch(function (err) {
        alert(t.imgError + '\n\n' + (err && err.message ? err.message : err));
      }).then(function () {
        setCapBusy(false);
        busyEl.hidden = true;
        noteEl.hidden = true;
        redraw();
        armInput();
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
