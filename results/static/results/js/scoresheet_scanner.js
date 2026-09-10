/* Scoresheet Scanner — in-app multi-page document capture.
 *
 * Photograph each page with the phone camera, the widget downscales it,
 * adds it to a page list, then stitches every page into ONE PDF (jsPDF)
 * and hands that File to a callback for the existing OCR upload path.
 * Nothing on the server changes.
 *
 * Deliberately minimal so it works on every phone:
 *  - no camera/getUserMedia preview, no OpenCV, no heavy processing that
 *    could hang a low-end device;
 *  - the file input is visually hidden (clipped, NOT display:none) and
 *    clicked programmatically, the one pattern every mobile browser
 *    honours;
 *  - a fresh input node after each shot so the next tap re-opens the
 *    camera;
 *  - the device Back button closes the overlay.
 *  - jsPDF is served from this app's own static files (no CDN) and
 *    loaded lazily.
 *
 * Usage:
 *   ScoresheetScanner.open({
 *     lang: 'sw',
 *     filename: 'scoresheet',
 *     jspdfUrl: '{% static "results/vendor/jspdf.umd.min.js" %}',
 *     onComplete: function (pdfFile) { ... }
 *   });
 */
(function () {
  'use strict';
  if (window.ScoresheetScanner) return;

  var STYLE_ID = 'scoresheet-scanner-style';
  var OUT_EDGE = 2000;       // final per-page image long edge (px)
  var JPEG_QUALITY = 0.88;

  var STR = {
    sw: {
      title: 'Scan Scoresheet (kurasa nyingi)',
      hint: 'Bonyeza "Piga picha ya ukurasa" — kamera itafunguka. Piga picha ya ukurasa mzima kwenye mwanga mzuri, karatasi ijae fremu. Rudia kwa kila ukurasa, kisha "Maliza".',
      capture: '📸 Piga picha ya ukurasa',
      addMore: '📸 Ongeza ukurasa mwingine',
      finish: 'Maliza',
      cancel: 'Ghairi',
      pagesLabel: 'Kurasa',
      empty: 'Bado hakuna ukurasa.',
      processing: 'Inaandaa ukurasa…',
      building: 'Inaunganisha kurasa kuwa PDF moja…',
      needPage: 'Piga angalau ukurasa mmoja kwanza.',
      close: 'Funga',
      pdfError: 'Imeshindwa kuandaa PDF. Jaribu tena.',
      imgError: 'Picha haikusomeka. Jaribu tena.',
      deletePage: 'Futa ukurasa huu',
      bw: 'Nyeusi–nyeupe (husaidia usomaji)'
    },
    en: {
      title: 'Scan Scoresheet (multi-page)',
      hint: 'Tap "Capture page" — the camera opens. Photograph the whole page in good light, filling the frame. Repeat for every page, then "Done".',
      capture: '📸 Capture page',
      addMore: '📸 Add another page',
      finish: 'Done',
      cancel: 'Cancel',
      pagesLabel: 'Pages',
      empty: 'No pages yet.',
      processing: 'Preparing page…',
      building: 'Combining pages into one PDF…',
      needPage: 'Capture at least one page first.',
      close: 'Close',
      pdfError: 'Could not build the PDF. Please try again.',
      imgError: 'Could not read the image. Try again.',
      deletePage: 'Delete this page',
      bw: 'Black & white (helps reading)'
    }
  };

  /* ---------- jsPDF (lazy, local) ------------------------------- */

  var jspdfP = null;
  function loadJsPDF(url) {
    if (window.jspdf && window.jspdf.jsPDF) return Promise.resolve(window.jspdf.jsPDF);
    if (!jspdfP) {
      jspdfP = new Promise(function (resolve, reject) {
        if (!url) { reject(new Error('jspdfUrl not set')); return; }
        var s = document.createElement('script');
        s.src = url; s.async = true;
        s.onload = function () {
          if (window.jspdf && window.jspdf.jsPDF) resolve(window.jspdf.jsPDF);
          else reject(new Error('jsPDF global missing'));
        };
        s.onerror = function () { jspdfP = null; reject(new Error('jsPDF failed to load')); };
        document.head.appendChild(s);
      });
    }
    return jspdfP;
  }

  /* ---------- image helpers ----------------------------------- */

  function imageFromFile(file) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () { URL.revokeObjectURL(url); resolve(img); };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error('decode failed')); };
      img.src = url;
    });
  }

  function processPage(file, bw) {
    return imageFromFile(file).then(function (img) {
      var w = img.naturalWidth || img.width;
      var h = img.naturalHeight || img.height;
      if (!w || !h) throw new Error('empty image');
      var s = Math.min(1, OUT_EDGE / Math.max(w, h));
      var c = document.createElement('canvas');
      c.width = Math.max(1, Math.round(w * s));
      c.height = Math.max(1, Math.round(h * s));
      var ctx = c.getContext('2d');
      if (bw) {
        try { ctx.filter = 'grayscale(1) contrast(1.35) brightness(1.05)'; } catch (e) {}
      }
      ctx.drawImage(img, 0, 0, c.width, c.height);
      return { dataUrl: c.toDataURL('image/jpeg', JPEG_QUALITY), w: c.width, h: c.height };
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
      '.ssc-x{background:none;border:none;color:#fff;font-size:1.6rem;line-height:1;padding:2px 10px;cursor:pointer;}' +
      '.ssc-body{padding:14px 16px;overflow-y:auto;flex:1;}' +
      '.ssc-hint{font-size:0.86rem;line-height:1.5;color:#333;margin:0 0 12px;}' +
      '.ssc-toggle{display:flex;align-items:center;gap:7px;font-size:0.86rem;color:#333;margin:0 0 12px;}' +
      '.ssc-cap{display:block;width:100%;min-height:56px;box-sizing:border-box;border:none;border-radius:6px;padding:15px;font-size:1rem;font-weight:700;background:#24508a;color:#fff;text-align:center;cursor:pointer;-webkit-tap-highlight-color:rgba(0,0,0,0.15);}' +
      '.ssc-cap.is-busy{opacity:0.5;pointer-events:none;}' +
      '.ssc-file{position:absolute!important;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0;}' +
      '.ssc-busy{margin-top:14px;font-size:0.9rem;color:#24508a;font-weight:700;text-align:center;}' +
      '.ssc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(88px,1fr));gap:10px;margin-top:14px;}' +
      '.ssc-empty{margin-top:14px;font-size:0.82rem;color:#888;text-align:center;padding:18px 8px;border:1px dashed #ccc;border-radius:6px;}' +
      '.ssc-thumb{position:relative;border:1px solid #d5dbe0;border-radius:6px;overflow:hidden;background:#f4f6f8;aspect-ratio:3/4;}' +
      '.ssc-thumb img{width:100%;height:100%;object-fit:cover;display:block;}' +
      '.ssc-thumb .n{position:absolute;left:3px;bottom:3px;font-size:0.7rem;font-weight:700;color:#fff;background:rgba(0,0,0,0.6);padding:0 6px;border-radius:3px;}' +
      '.ssc-thumb .del{position:absolute;top:2px;right:2px;width:24px;height:24px;border:none;border-radius:50%;background:rgba(192,57,43,0.95);color:#fff;font-size:0.9rem;line-height:24px;padding:0;cursor:pointer;}' +
      '.ssc-foot{display:flex;align-items:center;gap:10px;padding:12px 16px;border-top:1px solid #e6e6e6;flex-wrap:wrap;}' +
      '.ssc-count{font-size:0.9rem;font-weight:700;color:#333;flex:1;}' +
      '.ssc-btn{border:none;border-radius:6px;padding:11px 18px;font-size:0.9rem;font-weight:700;cursor:pointer;}' +
      '.ssc-btn[disabled]{opacity:0.45;cursor:default;}' +
      '.ssc-ok{background:#1F7A3D;color:#fff;}' +
      '.ssc-no{background:#eceff1;color:#333;}';
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
    var onComplete = typeof opts.onComplete === 'function' ? opts.onComplete : function () {};

    injectStyle();
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
          '<label class="ssc-toggle"><input type="checkbox" class="ssc-bw"> ' + t.bw + '</label>' +
          '<button type="button" class="ssc-cap"><span class="ssc-cap-t">' + t.capture + '</span></button>' +
          '<input type="file" class="ssc-file" accept="image/*" capture="environment">' +
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
    var fileInput = overlay.querySelector('.ssc-file');
    var bwCb = overlay.querySelector('.ssc-bw');
    var busyEl = overlay.querySelector('.ssc-busy');
    var grid = overlay.querySelector('.ssc-grid');
    var emptyEl = overlay.querySelector('.ssc-empty');
    var countEl = overlay.querySelector('.ssc-count');
    var doneBtn = overlay.querySelector('.ssc-done');
    var cancelBtn = overlay.querySelector('.ssc-cancel');
    var closeX = overlay.querySelector('.ssc-x');
    var capBusyTimer = null;
    var closed = false;

    // ---- Back-button support: pushing a history entry means the device
    // Back button fires popstate, which we turn into "close the overlay"
    // instead of navigating away from the marks page.
    var pushed = false;
    try { history.pushState({ ssc: 1 }, ''); pushed = true; } catch (e) {}
    function onPop() { pushed = false; close(true); }
    window.addEventListener('popstate', onPop);

    function setCapBusy(busy) {
      capBtn.classList.toggle('is-busy', !!busy);
      if (capBusyTimer) { clearTimeout(capBusyTimer); capBusyTimer = null; }
      if (busy) capBusyTimer = setTimeout(function () { capBtn.classList.remove('is-busy'); }, 20000);
    }

    function armInput() {
      var fresh = fileInput.cloneNode(false);
      fresh.value = '';
      fresh.disabled = false;
      if (fileInput.parentNode) fileInput.parentNode.replaceChild(fresh, fileInput);
      fileInput = fresh;
      fileInput.addEventListener('change', onPick);
    }

    function close(fromPop) {
      if (closed) return;
      closed = true;
      if (capBusyTimer) { clearTimeout(capBusyTimer); capBusyTimer = null; }
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('popstate', onPop);
      document.body.style.overflow = prevOverflow;
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
      if (pushed && !fromPop) { pushed = false; try { history.back(); } catch (e) {} }
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
      var bw = !!bwCb.checked;
      setCapBusy(true);
      busyEl.hidden = false;
      busyEl.textContent = t.processing;

      processPage(file, bw).then(function (page) {
        if (closed) return;
        pages.push(page);
      }).catch(function (err) {
        if (closed) return;
        alert(t.imgError + '\n\n' + (err && err.message ? err.message : err));
      }).then(function () {
        if (closed) return;
        setCapBusy(false);
        busyEl.hidden = true;
        redraw();
        armInput();
      });
    }
    fileInput.addEventListener('change', onPick);

    // The input is clipped (rendered, not display:none), so a
    // programmatic click inside this user gesture opens the camera on
    // every mobile browser.
    capBtn.addEventListener('click', function () {
      if (capBtn.classList.contains('is-busy')) return;
      try { fileInput.click(); } catch (e) {}
    });

    cancelBtn.addEventListener('click', function () { close(); });
    closeX.addEventListener('click', function () { close(); });

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
        if (closed) return;
        busyEl.hidden = true;
        setCapBusy(false);
        doneBtn.disabled = false;
        cancelBtn.disabled = false;
        alert(t.pdfError + '\n\n' + (err && err.message ? err.message : err));
      });
    });

    redraw();
  }

  // Combine already-taken photos (e.g. picked from the gallery) into one
  // PDF, same output as a scan. Images only — a PDF file should be used
  // directly, not passed here.
  function bundleImages(files, opts) {
    opts = opts || {};
    var S = window.ScoresheetScanner;
    var jspdfUrl = opts.jspdfUrl || (S && S.jspdfUrl);
    var baseName = (opts.filename || 'scoresheet').replace(/[^\w.-]+/g, '_');
    var bw = !!opts.bw;
    var arr = Array.prototype.slice.call(files || []);
    if (!arr.length) return Promise.reject(new Error('no files'));
    return arr.reduce(function (chain, f) {
      return chain.then(function (pages) {
        return processPage(f, bw).then(function (p) { pages.push(p); return pages; });
      });
    }, Promise.resolve([])).then(function (pages) {
      return loadJsPDF(jspdfUrl).then(function (jsPDF) {
        var blob = buildPdf(jsPDF, pages);
        return new File([blob], baseName + '_' + Date.now() + '.pdf', { type: 'application/pdf' });
      });
    });
  }

  window.ScoresheetScanner = { open: open, bundleImages: bundleImages, jspdfUrl: null, opencvUrl: null };
})();
