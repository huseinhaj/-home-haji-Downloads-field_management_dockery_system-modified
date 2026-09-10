/* Scoresheet Scanner — in-app multi-page document capture.
 *
 * Lets the user photograph one scoresheet page after another using the
 * phone's REAL camera app (full resolution, autofocus), collects the
 * pages, then stitches every page into a SINGLE PDF (jsPDF, served from
 * this app's own static files — no external CDN) and hands that File to
 * a callback. From there the flow is unchanged: the PDF goes to the same
 * upload endpoint / OCR pipeline that already reads multi-page scanned
 * PDFs.
 *
 * Usage:
 *   ScoresheetScanner.open({
 *     lang: 'sw',                 // 'sw' | 'en'  (default 'sw')
 *     filename: 'scoresheet',     // base name for the produced PDF
 *     jspdfUrl: '/static/.../jspdf.umd.min.js',   // REQUIRED — local path
 *     onComplete: function (file) { ... }         // file: PDF File object
 *   });
 */
(function () {
  'use strict';
  if (window.ScoresheetScanner) return;

  var STYLE_ID = 'scoresheet-scanner-style';
  var MAX_EDGE = 2200;     // cap the long edge of each page image (px)
  var JPEG_QUALITY = 0.85; // per-page JPEG quality inside the PDF

  var STR = {
    sw: {
      title: 'Scan Scoresheet (kurasa nyingi)',
      hint: 'Bonyeza "Piga picha ya ukurasa" — kamera ya simu yako itafunguka. Piga picha ya ukurasa MZIMA ukiwa kwenye mwanga wa kutosha na maandishi yaonekane wazi. Rudia kwa kila ukurasa, kisha bonyeza "Maliza".',
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
      imgError: 'Picha moja haikusomeka — imeachwa.',
      deletePage: 'Futa ukurasa huu',
      tip: '💡 Shikilia simu sawa juu ya karatasi, subiri kamera i-focus, epuka kivuli.'
    },
    en: {
      title: 'Scan Scoresheet (multi-page)',
      hint: 'Tap "Capture page" — your phone camera opens. Photograph the WHOLE page in good light so the text is sharp. Repeat for every page, then tap "Done".',
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
      imgError: 'One image could not be read — skipped.',
      deletePage: 'Delete this page',
      tip: '💡 Hold the phone flat above the paper, let the camera focus, avoid shadows.'
    }
  };

  var jspdfPromise = null;
  function loadJsPDF(url) {
    if (window.jspdf && window.jspdf.jsPDF) return Promise.resolve(window.jspdf.jsPDF);
    if (jspdfPromise) return jspdfPromise;
    jspdfPromise = new Promise(function (resolve, reject) {
      if (!url) { reject(new Error('jspdfUrl not provided')); return; }
      var s = document.createElement('script');
      s.src = url;
      s.async = true;
      s.onload = function () {
        if (window.jspdf && window.jspdf.jsPDF) resolve(window.jspdf.jsPDF);
        else reject(new Error('jsPDF loaded but global missing'));
      };
      s.onerror = function () { jspdfPromise = null; reject(new Error('jsPDF failed to load')); };
      document.head.appendChild(s);
    });
    return jspdfPromise;
  }

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var css = '' +
      '.ssc-overlay{position:fixed;inset:0;z-index:2147483000;background:rgba(8,12,18,0.92);display:flex;align-items:stretch;justify-content:center;padding:0;font-family:inherit;}' +
      '.ssc-panel{background:#fff;color:#1a1a1a;width:100%;max-width:620px;display:flex;flex-direction:column;max-height:100%;}' +
      '.ssc-head{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:#1F7A3D;color:#fff;}' +
      '.ssc-head h3{margin:0;font-size:0.98rem;font-weight:700;}' +
      '.ssc-x{background:none;border:none;color:#fff;font-size:1.5rem;line-height:1;padding:2px 6px;cursor:pointer;}' +
      '.ssc-body{padding:14px 16px;overflow-y:auto;flex:1;}' +
      '.ssc-hint{font-size:0.86rem;line-height:1.5;color:#333;margin-bottom:12px;}' +
      '.ssc-tip{font-size:0.78rem;color:#666;margin:10px 0 0;}' +
      '.ssc-cap{display:block;width:100%;border:none;border-radius:6px;padding:15px;font-size:1rem;font-weight:700;background:#24508a;color:#fff;cursor:pointer;}' +
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
      '.ssc-busy{margin-top:14px;font-size:0.9rem;color:#24508a;font-weight:700;text-align:center;}';
    var st = document.createElement('style');
    st.id = STYLE_ID;
    st.textContent = css;
    document.head.appendChild(st);
  }

  // Downscale a captured photo so a 10-page PDF stays a few MB (the OCR
  // step downsizes to ~1800px anyway, so full-sensor resolution is wasted
  // bytes on mobile data).
  function downscale(dataUrl) {
    return new Promise(function (resolve, reject) {
      var img = new Image();
      img.onload = function () {
        var w = img.naturalWidth || img.width;
        var h = img.naturalHeight || img.height;
        if (!w || !h) { reject(new Error('empty image')); return; }
        var scale = Math.min(1, MAX_EDGE / Math.max(w, h));
        var cw = Math.max(1, Math.round(w * scale));
        var ch = Math.max(1, Math.round(h * scale));
        var c = document.createElement('canvas');
        c.width = cw; c.height = ch;
        c.getContext('2d').drawImage(img, 0, 0, cw, ch);
        resolve({ dataUrl: c.toDataURL('image/jpeg', JPEG_QUALITY), w: cw, h: ch });
      };
      img.onerror = function () { reject(new Error('decode failed')); };
      img.src = dataUrl;
    });
  }

  function readFile(file) {
    return new Promise(function (resolve, reject) {
      var fr = new FileReader();
      fr.onload = function () { resolve(fr.result); };
      fr.onerror = function () { reject(new Error('read failed')); };
      fr.readAsDataURL(file);
    });
  }

  function buildPdf(jsPDF, pages) {
    var doc = new jsPDF({ unit: 'pt', format: 'a4', orientation: 'portrait' });
    var pw = doc.internal.pageSize.getWidth();
    var ph = doc.internal.pageSize.getHeight();
    for (var i = 0; i < pages.length; i++) {
      if (i > 0) doc.addPage();
      var p = pages[i];
      var s = Math.min(pw / p.w, ph / p.h);
      var dw = p.w * s;
      var dh = p.h * s;
      doc.addImage(p.dataUrl, 'JPEG', (pw - dw) / 2, (ph - dh) / 2, dw, dh, undefined, 'FAST');
    }
    return doc.output('blob');
  }

  function open(opts) {
    opts = opts || {};
    var lang = opts.lang === 'en' ? 'en' : 'sw';
    var t = STR[lang];
    var baseName = (opts.filename || 'scoresheet').replace(/[^\w.-]+/g, '_');
    var jspdfUrl = opts.jspdfUrl || (window.ScoresheetScanner && window.ScoresheetScanner.jspdfUrl);
    var onComplete = typeof opts.onComplete === 'function' ? opts.onComplete : function () {};

    injectStyle();
    // Warm the PDF library early so "Done" is instant and any load
    // problem surfaces before the user has captured 10 pages.
    loadJsPDF(jspdfUrl).catch(function () {});

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
          '<button type="button" class="ssc-cap">' + t.capture + '</button>' +
          '<p class="ssc-tip">' + t.tip + '</p>' +
          '<div class="ssc-empty">' + t.empty + '</div>' +
          '<div class="ssc-grid" hidden></div>' +
          '<div class="ssc-busy" hidden></div>' +
        '</div>' +
        '<div class="ssc-foot">' +
          '<span class="ssc-count"></span>' +
          '<button type="button" class="ssc-btn ssc-no">' + t.cancel + '</button>' +
          '<button type="button" class="ssc-btn ssc-ok" disabled>' + t.finish + '</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);

    var fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'image/*';
    fileInput.setAttribute('capture', 'environment');
    fileInput.multiple = true;
    fileInput.style.display = 'none';
    overlay.appendChild(fileInput);

    var capBtn = overlay.querySelector('.ssc-cap');
    var grid = overlay.querySelector('.ssc-grid');
    var emptyEl = overlay.querySelector('.ssc-empty');
    var busyEl = overlay.querySelector('.ssc-busy');
    var countEl = overlay.querySelector('.ssc-count');
    var okBtn = overlay.querySelector('.ssc-ok');
    var noBtn = overlay.querySelector('.ssc-no');
    var closeX = overlay.querySelector('.ssc-x');

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
      okBtn.disabled = !has;
      okBtn.textContent = t.finish + (has ? ' (' + pages.length + ')' : '');
      capBtn.textContent = has ? t.addMore : t.capture;
    }

    capBtn.addEventListener('click', function () { fileInput.click(); });

    fileInput.addEventListener('change', function () {
      var files = Array.prototype.slice.call(fileInput.files || []);
      fileInput.value = '';
      if (!files.length) return;
      capBtn.disabled = true;
      busyEl.hidden = false;
      busyEl.textContent = '…';
      var chain = Promise.resolve();
      var failed = 0;
      files.forEach(function (f) {
        chain = chain
          .then(function () { return readFile(f); })
          .then(downscale)
          .then(function (page) { pages.push(page); })
          .catch(function () { failed++; });
      });
      chain.then(function () {
        busyEl.hidden = true;
        capBtn.disabled = false;
        redraw();
        if (failed) alert(t.imgError);
      });
    });

    noBtn.addEventListener('click', close);
    closeX.addEventListener('click', close);

    okBtn.addEventListener('click', function () {
      if (!pages.length) { alert(t.needPage); return; }
      busyEl.hidden = false;
      busyEl.textContent = t.building;
      capBtn.disabled = true;
      okBtn.disabled = true;
      noBtn.disabled = true;
      loadJsPDF(jspdfUrl)
        .then(function (jsPDF) {
          var blob = buildPdf(jsPDF, pages);
          var file = new File([blob], baseName + '_' + Date.now() + '.pdf', { type: 'application/pdf' });
          close();
          onComplete(file);
        })
        .catch(function (err) {
          busyEl.hidden = true;
          capBtn.disabled = false;
          okBtn.disabled = false;
          noBtn.disabled = false;
          alert(t.pdfError + '\n\n' + (err && err.message ? err.message : err));
        });
    });

    redraw();
  }

  window.ScoresheetScanner = { open: open, jspdfUrl: null };
})();
