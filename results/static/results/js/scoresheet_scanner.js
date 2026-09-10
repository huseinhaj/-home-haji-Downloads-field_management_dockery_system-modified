/* Scoresheet Scanner — in-app multi-page document capture.
 *
 * Opens the phone camera inside the dashboard, lets the user snap one
 * scoresheet page after another, then stitches every captured page into a
 * SINGLE PDF (jsPDF) and hands that File to a callback. The rest of the
 * flow is unchanged: that PDF goes to the same upload endpoint / OCR
 * pipeline that already reads multi-page scanned PDFs.
 *
 * Usage:
 *   ScoresheetScanner.open({
 *     lang: 'sw',                 // 'sw' | 'en'  (default 'sw')
 *     filename: 'scoresheet',     // base name for the produced PDF
 *     onComplete: function (file) { ... }   // file: PDF File object
 *   });
 *
 * jsPDF is loaded lazily from the CDN only the first time a scan is
 * finished, so the ~350KB library never costs anything to a user who
 * doesn't scan.
 */
(function () {
  'use strict';
  if (window.ScoresheetScanner) return;

  var JSPDF_SRC = 'https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.2/jspdf.umd.min.js';
  var STYLE_ID = 'scoresheet-scanner-style';
  var MAX_EDGE = 2000; // cap the long edge of each captured page (px)

  var STR = {
    sw: {
      title: 'Scan Scoresheet',
      hint: 'Weka ukurasa mzima ndani ya fremu, kisha bonyeza "Piga ukurasa". Rudia kwa kila ukurasa wa somo hili.',
      capture: 'Piga ukurasa',
      finish: 'Maliza',
      cancel: 'Ghairi',
      pagesLabel: 'Kurasa',
      building: 'Inaunganisha kurasa kuwa PDF moja…',
      needPage: 'Piga angalau ukurasa mmoja kwanza.',
      grayscale: 'Nyeusi–nyeupe',
      camError: 'Imeshindwa kufungua kamera. Hakikisha umeruhusu kamera kwenye kivinjari na upo kwenye tovuti ya HTTPS. Bado unaweza kutumia kitufe cha kupakia picha/PDF.',
      close: 'Funga',
      pdfError: 'Imeshindwa kuandaa PDF. Angalia mtandao kisha jaribu tena.',
      deletePage: 'Futa ukurasa huu'
    },
    en: {
      title: 'Scan Scoresheet',
      hint: 'Fit the whole page inside the frame, then tap "Capture page". Repeat for every page of this subject.',
      capture: 'Capture page',
      finish: 'Done',
      cancel: 'Cancel',
      pagesLabel: 'Pages',
      building: 'Combining pages into one PDF…',
      needPage: 'Capture at least one page first.',
      grayscale: 'Black & white',
      camError: 'Could not open the camera. Make sure you allowed camera access and are on an HTTPS site. You can still use the upload photo/PDF button.',
      close: 'Close',
      pdfError: 'Could not build the PDF. Check your connection and try again.',
      deletePage: 'Delete this page'
    }
  };

  function loadJsPDF() {
    return new Promise(function (resolve, reject) {
      if (window.jspdf && window.jspdf.jsPDF) { resolve(window.jspdf.jsPDF); return; }
      var s = document.createElement('script');
      s.src = JSPDF_SRC;
      s.async = true;
      s.onload = function () {
        if (window.jspdf && window.jspdf.jsPDF) resolve(window.jspdf.jsPDF);
        else reject(new Error('jsPDF loaded but global missing'));
      };
      s.onerror = function () { reject(new Error('jsPDF network error')); };
      document.head.appendChild(s);
    });
  }

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var css = '' +
      '.ssc-overlay{position:fixed;inset:0;z-index:2147483000;background:#0b0f14;display:flex;flex-direction:column;color:#fff;font-family:inherit;}' +
      '.ssc-head{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:#111820;border-bottom:1px solid #223;}' +
      '.ssc-head h3{margin:0;font-size:1rem;font-weight:700;}' +
      '.ssc-x{background:none;border:none;color:#fff;font-size:1.4rem;line-height:1;padding:4px 8px;cursor:pointer;}' +
      '.ssc-stage{position:relative;flex:1;min-height:0;background:#000;display:flex;align-items:center;justify-content:center;overflow:hidden;}' +
      '.ssc-stage video{max-width:100%;max-height:100%;width:100%;height:100%;object-fit:contain;background:#000;}' +
      '.ssc-hint{position:absolute;left:0;right:0;bottom:0;padding:8px 12px;font-size:0.8rem;background:linear-gradient(transparent,rgba(0,0,0,0.75));text-align:center;}' +
      '.ssc-camerr{padding:22px;max-width:520px;margin:auto;text-align:center;font-size:0.92rem;line-height:1.5;}' +
      '.ssc-strip{display:flex;gap:8px;padding:8px 10px;overflow-x:auto;background:#0e141b;min-height:74px;align-items:center;}' +
      '.ssc-strip:empty::after{content:attr(data-empty);color:#5f7183;font-size:0.8rem;padding-left:6px;}' +
      '.ssc-thumb{position:relative;flex:0 0 auto;width:54px;height:66px;border-radius:4px;overflow:hidden;border:1px solid #2a3a49;background:#000;}' +
      '.ssc-thumb img{width:100%;height:100%;object-fit:cover;}' +
      '.ssc-thumb span{position:absolute;left:2px;bottom:2px;font-size:0.62rem;background:rgba(0,0,0,0.65);padding:0 4px;border-radius:3px;}' +
      '.ssc-thumb button{position:absolute;top:1px;right:1px;width:16px;height:16px;border:none;border-radius:50%;background:rgba(192,57,43,0.92);color:#fff;font-size:0.7rem;line-height:16px;padding:0;cursor:pointer;}' +
      '.ssc-controls{display:flex;align-items:center;gap:10px;padding:12px;background:#111820;border-top:1px solid #223;flex-wrap:wrap;justify-content:center;}' +
      '.ssc-btn{border:none;border-radius:4px;padding:12px 18px;font-size:0.92rem;font-weight:700;cursor:pointer;}' +
      '.ssc-btn[disabled]{opacity:0.45;cursor:default;}' +
      '.ssc-cap{background:#fff;color:#111;min-width:150px;}' +
      '.ssc-done{background:#1F7A3D;color:#fff;}' +
      '.ssc-cancel{background:#2a3a49;color:#fff;}' +
      '.ssc-toggle{display:flex;align-items:center;gap:6px;font-size:0.8rem;color:#cdd8e2;}' +
      '.ssc-count{font-size:0.85rem;color:#cdd8e2;min-width:78px;text-align:center;}' +
      '.ssc-busy{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.7);font-size:0.95rem;text-align:center;padding:20px;}';
    var st = document.createElement('style');
    st.id = STYLE_ID;
    st.textContent = css;
    document.head.appendChild(st);
  }

  function grabFrame(video, grayscale) {
    var vw = video.videoWidth || 1280;
    var vh = video.videoHeight || 720;
    var scale = Math.min(1, MAX_EDGE / Math.max(vw, vh));
    var cw = Math.max(1, Math.round(vw * scale));
    var ch = Math.max(1, Math.round(vh * scale));
    var c = document.createElement('canvas');
    c.width = cw;
    c.height = ch;
    var ctx = c.getContext('2d');
    if (grayscale) {
      try { ctx.filter = 'grayscale(1) contrast(1.18) brightness(1.06)'; } catch (e) { /* older browser */ }
    }
    ctx.drawImage(video, 0, 0, cw, ch);
    return { dataUrl: c.toDataURL('image/jpeg', 0.9), w: cw, h: ch };
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
    var onComplete = typeof opts.onComplete === 'function' ? opts.onComplete : function () {};

    injectStyle();
    var pages = [];
    var stream = null;
    var prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    var overlay = document.createElement('div');
    overlay.className = 'ssc-overlay';
    overlay.innerHTML = '' +
      '<div class="ssc-head"><h3>' + t.title + '</h3>' +
        '<button type="button" class="ssc-x" aria-label="' + t.close + '">&times;</button></div>' +
      '<div class="ssc-stage">' +
        '<video playsinline autoplay muted></video>' +
        '<div class="ssc-hint">' + t.hint + '</div>' +
        '<div class="ssc-busy" hidden></div>' +
      '</div>' +
      '<div class="ssc-strip"></div>' +
      '<div class="ssc-controls">' +
        '<button type="button" class="ssc-btn ssc-cancel">' + t.cancel + '</button>' +
        '<label class="ssc-toggle"><input type="checkbox" class="ssc-gray"> ' + t.grayscale + '</label>' +
        '<button type="button" class="ssc-btn ssc-cap">' + t.capture + '</button>' +
        '<span class="ssc-count"></span>' +
        '<button type="button" class="ssc-btn ssc-done" disabled>' + t.finish + '</button>' +
      '</div>';
    document.body.appendChild(overlay);

    var video = overlay.querySelector('video');
    var stage = overlay.querySelector('.ssc-stage');
    var hintEl = overlay.querySelector('.ssc-hint');
    var busyEl = overlay.querySelector('.ssc-busy');
    var strip = overlay.querySelector('.ssc-strip');
    var capBtn = overlay.querySelector('.ssc-cap');
    var doneBtn = overlay.querySelector('.ssc-done');
    var cancelBtn = overlay.querySelector('.ssc-cancel');
    var grayCb = overlay.querySelector('.ssc-gray');
    var countEl = overlay.querySelector('.ssc-count');
    var closeX = overlay.querySelector('.ssc-x');

    function stopStream() {
      if (stream) { stream.getTracks().forEach(function (tr) { tr.stop(); }); stream = null; }
    }
    function close() {
      stopStream();
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }
    function onKey(e) { if (e.key === 'Escape') close(); }
    document.addEventListener('keydown', onKey);

    function refresh() {
      strip.setAttribute('data-empty', t.pagesLabel + ': 0');
      countEl.textContent = t.pagesLabel + ': ' + pages.length;
      doneBtn.disabled = pages.length === 0;
      doneBtn.textContent = t.finish + (pages.length ? ' (' + pages.length + ')' : '');
    }
    function addThumb(page, idx) {
      var d = document.createElement('div');
      d.className = 'ssc-thumb';
      d.innerHTML = '<img alt=""><span></span><button type="button" title="' + t.deletePage + '">&times;</button>';
      d.querySelector('img').src = page.dataUrl;
      d.querySelector('span').textContent = idx + 1;
      d.querySelector('button').addEventListener('click', function () {
        var i = pages.indexOf(page);
        if (i > -1) pages.splice(i, 1);
        redrawStrip();
      });
      strip.appendChild(d);
    }
    function redrawStrip() {
      strip.innerHTML = '';
      pages.forEach(function (p, i) { addThumb(p, i); });
      refresh();
    }

    capBtn.addEventListener('click', function () {
      if (!video.videoWidth) return;
      var page = grabFrame(video, grayCb.checked);
      pages.push(page);
      addThumb(page, pages.length - 1);
      refresh();
      strip.scrollLeft = strip.scrollWidth;
    });

    cancelBtn.addEventListener('click', close);
    closeX.addEventListener('click', close);

    doneBtn.addEventListener('click', function () {
      if (!pages.length) return;
      busyEl.hidden = false;
      busyEl.textContent = t.building;
      capBtn.disabled = true;
      doneBtn.disabled = true;
      loadJsPDF()
        .then(function (jsPDF) {
          var blob = buildPdf(jsPDF, pages);
          var file = new File(
            [blob],
            baseName + '_' + Date.now() + '.pdf',
            { type: 'application/pdf' }
          );
          close();
          onComplete(file);
        })
        .catch(function (err) {
          busyEl.hidden = true;
          capBtn.disabled = false;
          doneBtn.disabled = false;
          alert(t.pdfError + '\n\n' + (err && err.message ? err.message : err));
        });
    });

    function showCamError() {
      stopStream();
      stage.innerHTML = '<div class="ssc-camerr">' + t.camError +
        '<div style="margin-top:16px;"><button type="button" class="ssc-btn ssc-cancel">' + t.close + '</button></div></div>';
      stage.querySelector('button').addEventListener('click', close);
      capBtn.disabled = true;
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      showCamError();
      return;
    }
    navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: { ideal: 'environment' },
        width: { ideal: 2560 },
        height: { ideal: 1440 }
      },
      audio: false
    }).then(function (s) {
      stream = s;
      video.srcObject = s;
      var play = video.play();
      if (play && play.catch) play.catch(function () {});
    }).catch(function () {
      showCamError();
    });

    refresh();
  }

  window.ScoresheetScanner = { open: open };
})();
