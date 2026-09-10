/* Results-PDF style picker.
 *
 * Intercepts clicks on any link to a results PDF (href contains
 * "/results-pdf/") and first asks which output style to generate:
 *   normal - the system's standard official layout (unchanged)
 *   rank   - TEC "School GPA Ranks" colours
 *   necta  - NECTA CSEE results-page layout
 * then continues to  <href>?style=<choice>.
 *
 * Set window.PDF_PICKER_LANG = 'sw' | 'en' before this script for labels.
 */
(function () {
  'use strict';
  var LANG = window.PDF_PICKER_LANG === 'en' ? 'en' : 'sw';

  var T = {
    sw: {
      title: 'Chagua aina ya matokeo (PDF)',
      hint: 'Maudhui na mpangilio ni sawa kwa zote — rangi tu ndizo hutofautiana.',
      normal: 'Kawaida',
      normalSub: 'Muundo wa mfumo (kama ilivyo sasa)',
      rank: 'Muundo wa Ranki (TEC)',
      rankSub: 'Rangi za "School GPA Ranks"',
      necta: 'Muundo wa NECTA CSEE',
      nectaSub: 'Kama ukurasa wa matokeo wa NECTA',
      cancel: 'Ghairi'
    },
    en: {
      title: 'Choose the results output (PDF)',
      hint: 'Content and layout are the same for all — only the colours differ.',
      normal: 'Normal',
      normalSub: "The system's standard layout (unchanged)",
      rank: 'Rank style (TEC)',
      rankSub: '"School GPA Ranks" colours',
      necta: 'NECTA CSEE style',
      nectaSub: 'Like the NECTA results page',
      cancel: 'Cancel'
    }
  }[LANG];

  var STYLE_ID = 'pdf-style-picker-css';
  function injectCss() {
    if (document.getElementById(STYLE_ID)) return;
    var css =
      '.psp-overlay{position:fixed;inset:0;z-index:2147483000;background:rgba(8,12,18,.55);display:flex;align-items:center;justify-content:center;padding:16px;font-family:inherit;}' +
      '.psp-box{background:#fff;color:#1f2937;width:100%;max-width:420px;border-radius:6px;overflow:hidden;box-shadow:0 16px 48px rgba(0,0,0,.3);}' +
      '.psp-head{padding:.9rem 1.1rem;background:#15653a;color:#fff;font-weight:700;font-size:.95rem;}' +
      '.psp-body{padding:1rem 1.1rem;}' +
      '.psp-hint{font-size:.8rem;color:#6b7280;margin:0 0 .9rem;}' +
      '.psp-opt{display:block;width:100%;text-align:left;border:1px solid #dfe3e8;border-radius:5px;background:#fff;padding:.7rem .85rem;margin-bottom:.55rem;cursor:pointer;}' +
      '.psp-opt:hover{border-color:#15653a;background:#f4f8f5;}' +
      '.psp-opt b{display:block;font-size:.88rem;color:#1f2937;}' +
      '.psp-opt span{display:block;font-size:.75rem;color:#6b7280;margin-top:.1rem;}' +
      '.psp-foot{padding:.7rem 1.1rem;border-top:1px solid #eef1f4;text-align:right;}' +
      '.psp-cancel{border:1px solid #dfe3e8;background:#fff;border-radius:5px;padding:.5rem .9rem;font-size:.82rem;font-weight:600;cursor:pointer;}';
    var s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent = css;
    document.head.appendChild(s);
  }

  function withStyle(href, style) {
    return href + (href.indexOf('?') === -1 ? '?' : '&') + 'style=' + style;
  }

  function openPicker(href) {
    injectCss();
    var ov = document.createElement('div');
    ov.className = 'psp-overlay';
    ov.innerHTML =
      '<div class="psp-box">' +
        '<div class="psp-head">' + T.title + '</div>' +
        '<div class="psp-body">' +
          '<p class="psp-hint">' + T.hint + '</p>' +
          '<button type="button" class="psp-opt" data-style="normal"><b>' + T.normal + '</b><span>' + T.normalSub + '</span></button>' +
          '<button type="button" class="psp-opt" data-style="rank"><b>' + T.rank + '</b><span>' + T.rankSub + '</span></button>' +
          '<button type="button" class="psp-opt" data-style="necta"><b>' + T.necta + '</b><span>' + T.nectaSub + '</span></button>' +
        '</div>' +
        '<div class="psp-foot"><button type="button" class="psp-cancel">' + T.cancel + '</button></div>' +
      '</div>';
    document.body.appendChild(ov);

    function close() { if (ov.parentNode) ov.parentNode.removeChild(ov); }
    ov.addEventListener('click', function (e) { if (e.target === ov) close(); });
    ov.querySelector('.psp-cancel').addEventListener('click', close);
    ov.querySelectorAll('.psp-opt').forEach(function (b) {
      b.addEventListener('click', function () {
        var url = withStyle(href, b.dataset.style);
        close();
        window.location.href = url;   // same tab — never popup-blocked
      });
    });
  }

  // Only the exam results PDF: /shule/results-pdf/<id>/  — NOT the
  // per-student slips at /results-pdf/<id>/wanafunzi-wote/.
  var RESULTS_PDF = /\/results-pdf\/\d+\/?(?:$|\?)/;

  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href]');
    if (!a) return;
    var href = a.getAttribute('href') || '';
    if (!RESULTS_PDF.test(href)) return;
    if (/[?&]style=/.test(href)) return;               // already chosen
    if (a.hasAttribute('data-no-style-picker')) return;
    e.preventDefault();
    openPicker(href);
  }, true);
})();
