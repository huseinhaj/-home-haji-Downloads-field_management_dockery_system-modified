/* Mfumo unaojielezea — maelekezo ya kila kitufe na kiungo.
 *
 * Chanzo cha maelezo (kwa mpangilio):
 *   1. data-help="…" kwenye kitufe chenyewe
 *   2. URL kinachoelekea (kiungo / fomu) → results/page_help.py (SRS_HELP.routes)
 *   3. maneno ya kitufe (Hifadhi, Futa, Pakua…) → KEYWORDS hapa chini
 *
 * Kompyuta: weka mouse juu ya kitufe → maelezo yanatokea.
 * Simu: bonyeza ❓ Msaada → gusa kitufe chochote → maelezo + "Endelea".
 */
(function () {
  const CFG = window.SRS_HELP || { lang: 'sw', routes: [] };
  const SW = CFG.lang !== 'en';
  const routes = (CFG.routes || []).map(r => ({ ...r, rx: new RegExp(r.re) }));

  const T = SW ? {
    goes: '➜ Inakupeleka:', file: '📄 Inafungua / kupakua:', action: '⚡ Kitendo:',
    newTab: '(inafunguka dirisha jipya)', external: '🌐 Inafungua tovuti nyingine:',
    filter: '🔎 Inaonyesha kulingana na ulichochagua.', cont: 'Endelea ➜', close: 'Funga',
    help: 'Msaada', helpOn: 'Gusa kitufe chochote kujua kinafanya nini', exit: 'Maliza msaada',
    none: 'Kitufe hiki hakina maelezo zaidi.',
  } : {
    goes: '➜ Takes you to:', file: '📄 Opens / downloads:', action: '⚡ Action:',
    newTab: '(opens in a new tab)', external: '🌐 Opens another website:',
    filter: '🔎 Shows results for what you picked.', cont: 'Continue ➜', close: 'Close',
    help: 'Help', helpOn: 'Tap any button to see what it does', exit: 'Exit help',
    none: 'No further details for this button.',
  };

  // Maneno ya kawaida kwenye vitufe → maelezo (neno la kwanza linalolingana linashinda).
  const KEYWORDS = SW ? [
    [/futa|delete|ondoa|remove|🗑/i, 'Inafuta — utaulizwa kuthibitisha kabla.'],
    [/hifadhi|save|💾/i, 'Inahifadhi mabadiliko yako.'],
    [/wasilisha|submit/i, 'Inatuma kazi yako kwa anayehusika (mf. Academic) kuidhinishwa.'],
    [/idhinisha|approve/i, 'Inakubali alama/kazi hii iingie kwenye matokeo.'],
    [/rudisha|return|restore/i, 'Inarudisha kwa hatua iliyopita / kwa mhusika kurekebisha.'],
    [/pakua|download/i, 'Inapakua faili kwenye kifaa chako.'],
    [/pakia|upload/i, 'Chagua faili kutoka kwenye kifaa chako kulipakia.'],
    [/scan|piga picha|camera/i, 'Piga picha / pakia picha — mfumo unasoma yaliyomo wenyewe.'],
    [/chapisha|print/i, 'Inaandaa kwa ajili ya kuchapisha.'],
    [/hakiki|preview|angalia|view/i, 'Inaonyesha kabla ya kuhifadhi / kutuma.'],
    [/ongeza|add|➕/i, 'Inaongeza kipya.'],
    [/hariri|edit|badilisha|✎/i, 'Inafungua sehemu ya kurekebisha.'],
    [/tafuta|search|filter/i, 'Inatafuta / kuchuja orodha.'],
    [/continue|endelea|next|mbele/i, 'Inaenda hatua inayofuata.'],
    [/funga|close|cancel|ghairi/i, 'Inafunga bila kubadilisha kitu.'],
    [/unda|create|tengeneza|generate/i, 'Inatengeneza kipya.'],
    [/pdf/i, 'Inafungua PDF.'],
    [/excel/i, 'Inapakua Excel.'],
  ] : [
    [/delete|remove|futa|ondoa|🗑/i, 'Deletes — you will be asked to confirm first.'],
    [/save|hifadhi|💾/i, 'Saves your changes.'],
    [/submit|wasilisha/i, 'Sends your work to the person responsible (e.g. the Academic) for approval.'],
    [/approve|idhinisha/i, 'Accepts these marks/work into the results.'],
    [/return|restore|rudisha/i, 'Sends it back a step / to the owner to fix.'],
    [/download|pakua/i, 'Downloads a file to your device.'],
    [/upload|pakia/i, 'Pick a file from your device to upload.'],
    [/scan|camera/i, 'Take / upload a photo — the system reads it for you.'],
    [/print|chapisha/i, 'Prepares it for printing.'],
    [/preview|view|hakiki/i, 'Shows it before saving / sending.'],
    [/add|ongeza|➕/i, 'Adds something new.'],
    [/edit|change|hariri|✎/i, 'Opens the editing section.'],
    [/search|filter|tafuta/i, 'Searches / filters the list.'],
    [/continue|next|endelea/i, 'Goes to the next step.'],
    [/close|cancel|funga/i, 'Closes without changing anything.'],
    [/create|generate|unda/i, 'Creates something new.'],
    [/pdf/i, 'Opens a PDF.'],
    [/excel/i, 'Downloads Excel.'],
  ];

  const CLICKABLE = 'a[href], button, input[type=submit], input[type=button], [data-help]';

  function textOf(el) {
    return (el.innerText || el.value || el.getAttribute('aria-label') || el.dataset.helpTitle || el.title || '')
      .replace(/\s+/g, ' ').trim().slice(0, 80);
  }

  function matchRoute(url) {
    try {
      const u = new URL(url, location.href);
      if (u.origin !== location.origin) return { external: u.host };
      return routes.find(r => r.rx.test(u.pathname)) || null;
    } catch (e) { return null; }
  }

  function fromRoute(r) {
    const head = r.kind === 'file' ? T.file : r.kind === 'action' ? T.action : T.goes;
    return { head: head + ' ' + r.title, body: r.what };
  }

  function fromKeywords(el) {
    const t = textOf(el);
    for (const [rx, msg] of KEYWORDS) if (rx.test(t)) return { head: '⚡ ' + t, body: msg };
    return t ? { head: '⚡ ' + t, body: '' } : null;
  }

  // → {head, body} | null
  function describe(el) {
    if (el.dataset.help) {
      return { head: el.dataset.helpTitle || ('💡 ' + (textOf(el) || T.help)), body: el.dataset.help };
    }
    if (el.matches('a[href]')) {
      const href = el.getAttribute('href') || '';
      if (href.startsWith('#') || href.startsWith('javascript:')) return fromKeywords(el);
      if (href.startsWith('tel:')) return { head: '📞 ' + href.slice(4), body: '' };
      if (href.startsWith('mailto:')) return { head: '✉️ ' + href.slice(7), body: '' };
      const r = matchRoute(href);
      const tab = el.target === '_blank' ? ' ' + T.newTab : '';
      if (r && r.external) return { head: T.external + ' ' + r.external + tab, body: '' };
      if (r) { const d = fromRoute(r); d.body += tab; return d; }
      const kw = fromKeywords(el);
      return { head: T.goes + ' ' + (textOf(el) || href), body: (kw && kw.body ? kw.body : '') + tab };
    }
    const form = el.form || el.closest('form');
    const isSubmit = el.matches('input[type=submit]') ||
      (el.matches('button') && (el.getAttribute('type') || 'submit') === 'submit' && form);
    if (isSubmit && form) {
      const action = el.getAttribute('formaction') || form.getAttribute('action') || location.pathname;
      const r = matchRoute(action);
      if (r && !r.external && r.kind !== 'page') return fromRoute(r);
      if ((form.method || 'get').toLowerCase() === 'get') {
        return r && !r.external ? fromRoute(r) : { head: '🔎 ' + textOf(el), body: T.filter };
      }
    }
    return fromKeywords(el);
  }

  // ── Tooltip ya mouse (kompyuta) ─────────────────────────────────────
  const tip = document.createElement('div');
  tip.className = 'srs-tip';
  tip.setAttribute('role', 'tooltip');
  document.body.appendChild(tip);
  let tipTimer = null, tipEl = null;

  function fill(box, d) {
    box.innerHTML = '';
    const h = document.createElement('strong'); h.textContent = d.head; box.appendChild(h);
    if (d.body) { const p = document.createElement('span'); p.textContent = d.body; box.appendChild(p); }
  }

  function showTip(el) {
    const d = describe(el);
    if (!d) return;
    if (el.title) { el.dataset.helpTitleOrig = el.title; el.removeAttribute('title'); }
    fill(tip, d);
    tip.classList.add('show');
    const r = el.getBoundingClientRect();
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let left = Math.min(Math.max(8, r.left + r.width / 2 - tw / 2), window.innerWidth - tw - 8);
    let top = r.bottom + 8;
    if (top + th > window.innerHeight - 8) top = r.top - th - 8;
    tip.style.left = left + 'px';
    tip.style.top = Math.max(8, top) + 'px';
  }

  function hideTip() {
    clearTimeout(tipTimer);
    tip.classList.remove('show');
    if (tipEl && tipEl.dataset.helpTitleOrig) { tipEl.title = tipEl.dataset.helpTitleOrig; delete tipEl.dataset.helpTitleOrig; }
    tipEl = null;
  }

  if (window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
    document.addEventListener('mouseover', e => {
      const el = e.target.closest(CLICKABLE);
      if (el === tipEl) return;
      hideTip();
      // Viungo vya menyu tayari vinaonyesha maelezo yao — hakuna haja ya tooltip.
      if (!el || el.closest('.srs-help-sheet') || el.matches('.nav-item, .drawer-item')) return;
      tipEl = el;
      tipTimer = setTimeout(() => showTip(el), 400);
    });
    document.addEventListener('scroll', hideTip, true);
    document.addEventListener('click', hideTip, true);
  }
  document.addEventListener('focusin', e => {
    const el = e.target.closest(CLICKABLE);
    if (el && e.target.matches(':focus-visible')) { hideTip(); tipEl = el; showTip(el); }
  });
  document.addEventListener('focusout', hideTip);

  // ── Hali ya msaada (simu + kompyuta) ────────────────────────────────
  const fab = document.createElement('button');
  fab.type = 'button';
  fab.className = 'srs-help-fab';
  fab.innerHTML = '❓ <span></span>';
  fab.querySelector('span').textContent = T.help;
  fab.setAttribute('aria-pressed', 'false');
  document.body.appendChild(fab);

  const banner = document.createElement('div');
  banner.className = 'srs-help-banner';
  banner.textContent = '❓ ' + T.helpOn;
  document.body.appendChild(banner);

  const sheet = document.createElement('div');
  sheet.className = 'srs-help-sheet';
  sheet.innerHTML = '<div class="srs-help-body"></div><div class="srs-help-actions">' +
    '<button type="button" class="srs-help-close"></button><button type="button" class="srs-help-go"></button></div>';
  sheet.querySelector('.srs-help-close').textContent = T.close;
  sheet.querySelector('.srs-help-go').textContent = T.cont;
  document.body.appendChild(sheet);

  let helpMode = false, pending = null;

  function setHelpMode(on) {
    helpMode = on;
    document.body.classList.toggle('srs-help-mode', on);
    fab.setAttribute('aria-pressed', String(on));
    fab.querySelector('span').textContent = on ? T.exit : T.help;
    if (!on) closeSheet();
  }

  function closeSheet() { sheet.classList.remove('show'); pending = null; }

  fab.addEventListener('click', e => { e.stopPropagation(); setHelpMode(!helpMode); });

  document.addEventListener('click', e => {
    if (!helpMode || e.target.closest('.srs-help-sheet, .srs-help-fab')) return;
    const el = e.target.closest(CLICKABLE);
    if (!el) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    fill(sheet.querySelector('.srs-help-body'), describe(el) || { head: textOf(el) || T.help, body: T.none });
    pending = el;
    sheet.classList.add('show');
  }, true);

  sheet.querySelector('.srs-help-close').addEventListener('click', closeSheet);
  sheet.querySelector('.srs-help-go').addEventListener('click', () => {
    const el = pending;
    setHelpMode(false);
    if (el) el.click();
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && helpMode) setHelpMode(false); });

  // ── Kisanduku cha "Ukurasa huu" — kumbuka kama mtumiaji amekifunga ──
  const card = document.getElementById('srsPageHelp');
  if (card) {
    const key = 'srs-page-help:' + card.dataset.key;
    try { if (localStorage.getItem(key) === 'closed') card.open = false; } catch (e) {}
    card.addEventListener('toggle', () => {
      try { localStorage.setItem(key, card.open ? 'open' : 'closed'); } catch (e) {}
    });
  }

  // ── Menyu ya makundi (kompyuta): fungua kwa kubonyeza, funga ukibonyeza nje ──
  const groups = Array.from(document.querySelectorAll('.nav-group'));
  function closeGroups(except) {
    groups.forEach(g => {
      if (g === except) return;
      g.classList.remove('open');
      const b = g.querySelector('.nav-group-btn');
      if (b) b.setAttribute('aria-expanded', 'false');
    });
  }
  groups.forEach(g => {
    const btn = g.querySelector('.nav-group-btn');
    if (!btn) return;
    btn.addEventListener('click', () => {
      const open = !g.classList.contains('open');
      closeGroups(g);
      g.classList.toggle('open', open);
      btn.setAttribute('aria-expanded', String(open));
      hideTip();
    });
  });
  document.addEventListener('click', e => { if (!e.target.closest('.nav-group')) closeGroups(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeGroups(); });

  // ── Menyu ya chini (simu): onyesha ukurasa uliopo ─────────────────────
  document.querySelectorAll('.bottom-nav a[href]').forEach(a => {
    try {
      if (new URL(a.href, location.href).pathname === location.pathname) {
        a.classList.add('active');
        a.setAttribute('aria-current', 'page');
      }
    } catch (e) {}
  });

  window.SRSHelp = { describe, setHelpMode };
})();
