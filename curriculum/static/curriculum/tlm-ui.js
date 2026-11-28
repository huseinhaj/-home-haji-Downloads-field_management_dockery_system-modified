/* =====================================================================
   TLM Tanzania — UI behaviours (vanilla ES6, no dependencies)
   File: curriculum/static/curriculum/tlm-ui.js  (load with defer)
   Public API on window.TLM: toast, confirm, pick, openPdf, runGenerate
   ===================================================================== */
(function () {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const icon = (id, cls = 'ic') => `<svg class="${cls}"><use href="#i-${id}"/></svg>`;
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  /* ---------- Theme (dark mode) ---------- */
  const savedTheme = localStorage.getItem('tlm-theme');
  if (savedTheme) document.documentElement.dataset.theme = savedTheme;
  document.addEventListener('click', e => {
    if (!e.target.closest('[data-theme-toggle]')) return;
    const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem('tlm-theme', t); } catch (_) {}
  });

  /* ---------- Drawer ---------- */
  document.addEventListener('click', e => {
    if (e.target.closest('[data-drawer-open]')) document.body.classList.add('drawer-open');
    if (e.target.closest('[data-drawer-close]') || e.target.classList.contains('drawer-dim')) document.body.classList.remove('drawer-open');
  });

  /* ---------- Toast (info icon, never a tick) ---------- */
  function toast(msg, ms = 3200) {
    let w = $('.toast-wrap');
    if (!w) { w = document.createElement('div'); w.className = 'toast-wrap'; document.body.appendChild(w); }
    const t = document.createElement('div');
    t.className = 'toast-tlm';
    t.setAttribute('role', 'status');
    t.innerHTML = `${icon('info')}<span class="grow">${esc(msg)}</span><button class="dlg-x" style="border:0" aria-label="Funga">${icon('x', 'ic ic-sm')}</button>`;
    t.querySelector('button').onclick = () => t.remove();
    w.appendChild(t);
    setTimeout(() => t.remove(), ms);
  }

  /* ---------- Dialog shell (F3: centered, square X) ---------- */
  function openDialog(title, inner, { onClose } = {}) {
    const dim = document.createElement('div'); dim.className = 'dlg-dim';
    const d = document.createElement('div');
    d.className = 'dlg';
    d.setAttribute('role', 'dialog');
    d.setAttribute('aria-modal', 'true');
    d.innerHTML = `<div class="dlg-head"><b>${esc(title)}</b><button type="button" class="dlg-x" aria-label="Funga">${icon('x', 'ic ic-sm')}</button></div>`;
    d.appendChild(inner);
    const close = () => { dim.remove(); d.remove(); document.removeEventListener('keydown', onKey); onClose && onClose(); };
    const onKey = e => { if (e.key === 'Escape') close(); };
    dim.onclick = close;
    d.querySelector('.dlg-x').onclick = close;
    document.addEventListener('keydown', onKey);
    document.body.append(dim, d);
    return { el: d, close };
  }

  /* ---------- Confirm (used by Toka) ---------- */
  function confirmDlg({ title, text, ok = 'Sawa', cancel = 'Ghairi', danger = false, okIcon = '' }) {
    return new Promise(res => {
      const body = document.createElement('div');
      body.innerHTML = `<div class="dlg-body">${esc(text)}</div><div class="dlg-actions">
        <button type="button" class="btn-tlm grey sm" data-c>${esc(cancel)}</button>
        <button type="button" class="btn-tlm sm ${danger ? 'danger' : ''}" data-ok>${okIcon ? icon(okIcon, 'ic ic-sm') : ''}${esc(ok)}</button></div>`;
      const dlg = openDialog(title, body, { onClose: () => res(false) });
      body.querySelector('[data-c]').onclick = () => dlg.close();
      body.querySelector('[data-ok]').onclick = () => { res(true); dlg.el.remove(); $('.dlg-dim') && $('.dlg-dim').remove(); };
    });
  }
  // <a href="/logout/" data-confirm-logout>Toka</a>
  document.addEventListener('click', async e => {
    const a = e.target.closest('[data-confirm-logout]');
    if (!a) return;
    e.preventDefault();
    const ok = await confirmDlg({ title: 'Toka?', text: 'Una uhakika unataka kutoka kwenye akaunti yako?', ok: 'Toka', danger: true, okIcon: 'log-out' });
    if (ok) { if (a.tagName === 'BUTTON' && a.form) a.form.submit(); else window.location.href = a.href; }
  });

  /* ---------- Picker: enhances <select data-picker> ---------- */
  // <select name="level" data-picker data-title="Chagua Ngazi" [data-search="Tafuta somo…"] [data-placeholder="Chagua mada"]>
  function pick({ title, options, value, search }) {
    return new Promise(res => {
      const wrap = document.createElement('div');
      wrap.style.cssText = 'display:flex;flex-direction:column;min-height:0';
      wrap.innerHTML = (search ? `<div class="dlg-search"><input class="tlm-input" type="search" placeholder="${esc(search)}" style="height:38px"></div>` : '')
        + '<div class="dlg-list" role="listbox"></div>';
      const list = wrap.querySelector('.dlg-list');
      const render = q => {
        list.innerHTML = options.filter(o => !q || o.label.toLowerCase().includes(q.toLowerCase()))
          .map(o => `<button type="button" class="opt" role="option" aria-selected="${o.value === value}" data-v="${esc(o.value)}">${esc(o.label)}<span class="rd"></span></button>`).join('');
      };
      render('');
      const dlg = openDialog(title, wrap, { onClose: () => res(null) });
      const s = wrap.querySelector('input');
      if (s) s.oninput = () => render(s.value);
      list.onclick = e => {
        const b = e.target.closest('.opt'); if (!b) return;
        res(b.dataset.v); dlg.el.remove(); $('.dlg-dim') && $('.dlg-dim').remove();
      };
    });
  }
  function enhanceSelect(sel) {
    if (sel.dataset.enhanced) return;
    sel.dataset.enhanced = '1';
    sel.classList.add('tlm-hidden');
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'ip';
    const paint = () => {
      const o = sel.selectedOptions[0];
      const empty = !o || !o.value;
      btn.classList.toggle('ph', empty);
      btn.innerHTML = `<span>${esc(empty ? (sel.dataset.placeholder || 'Chagua') : o.textContent)}</span>${icon('chevron-down', 'ic ic-sm')}`;
    };
    paint();
    sel.after(btn);
    sel.addEventListener('change', paint);
    btn.onclick = async () => {
      const options = Array.from(sel.options).filter(o => o.value).map(o => ({ value: o.value, label: o.textContent }));
      const v = await pick({ title: sel.dataset.title || 'Chagua', options, value: sel.value, search: sel.dataset.search });
      if (v !== null) { sel.value = v; sel.dispatchEvent(new Event('change', { bubbles: true })); }
    };
  }

  /* ---------- Calendar: enhances <input type="hidden" data-date data-title="Tarehe ya kuanza"> (value = YYYY-MM-DD) ---------- */
  const MONTHS = ['Januari', 'Februari', 'Machi', 'Aprili', 'Mei', 'Juni', 'Julai', 'Agosti', 'Septemba', 'Oktoba', 'Novemba', 'Desemba'];
  const MSH = ['Jan', 'Feb', 'Mac', 'Apr', 'Mei', 'Jun', 'Jul', 'Ago', 'Sep', 'Okt', 'Nov', 'Des'];
  const DAYS = ['Jumapili', 'Jumatatu', 'Jumanne', 'Jumatano', 'Alhamisi', 'Ijumaa', 'Jumamosi'];
  const WD = ['J1', 'J2', 'J3', 'Al', 'Ij', 'Jm', 'Jp']; // Monday first
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const dmy = s => s ? s.split('-').reverse().join('/') : '';

  function calendar(title, value) {
    return new Promise(res => {
      const today = new Date(); today.setHours(0, 0, 0, 0);
      let sel = value ? new Date(value + 'T00:00') : new Date(today);
      let view = new Date(sel.getFullYear(), sel.getMonth(), 1);
      let years = false;
      const box = document.createElement('div');
      const draw = () => {
        const big = `${DAYS[sel.getDay()]}, ${sel.getDate()} ${MSH[sel.getMonth()]} ${sel.getFullYear()}`;
        let grid = '';
        if (years) {
          const y0 = today.getFullYear() - 2;
          grid = '<div class="yr-grid">' + Array.from({ length: 24 }, (_, i) => y0 + i)
            .map(y => `<button type="button" data-y="${y}" class="${y === view.getFullYear() ? 'sel' : ''}">${y}</button>`).join('') + '</div>';
        } else {
          const lead = (view.getDay() + 6) % 7;
          const n = new Date(view.getFullYear(), view.getMonth() + 1, 0).getDate();
          grid = '<div class="cal-grid">' + WD.map(w => `<span class="wd">${w}</span>`).join('')
            + '<span></span>'.repeat(lead)
            + Array.from({ length: n }, (_, i) => {
                const d = new Date(view.getFullYear(), view.getMonth(), i + 1);
                const c = (+d === +sel ? 'sel' : '') + (+d === +today ? ' today' : '');
                return `<button type="button" data-d="${i + 1}" class="${c}"><i>${i + 1}</i></button>`;
              }).join('') + '</div>';
        }
        box.innerHTML = `<div class="cal-big">${big}</div>
          <div class="cal-bar"><div style="display:flex;align-items:center"><span class="m">${MONTHS[view.getMonth()]}</span>
            <button type="button" class="cal-year" data-yt>${view.getFullYear()} ${icon(years ? 'chevron-up' : 'chevron-down', 'ic ic-sm')}</button></div>
            <div style="display:flex;gap:8px;${years ? 'visibility:hidden' : ''}"><button type="button" class="sq sq-sm" data-p aria-label="Mwezi uliopita">${icon('chevron-left', 'ic ic-sm')}</button>
            <button type="button" class="sq sq-sm" data-n aria-label="Mwezi unaofuata">${icon('chevron-right', 'ic ic-sm')}</button></div></div>
          ${grid}<div class="cal-foot"><button type="button" data-c>Ghairi</button><button type="button" class="ok" data-ok>Sawa</button></div>`;
      };
      draw();
      const dlg = openDialog(title, box, { onClose: () => res(null) });
      box.onclick = e => {
        const t = e.target.closest('button'); if (!t) return;
        if (t.dataset.p !== undefined) view.setMonth(view.getMonth() - 1);
        else if (t.dataset.n !== undefined) view.setMonth(view.getMonth() + 1);
        else if (t.dataset.yt !== undefined) years = !years;
        else if (t.dataset.y) { view.setFullYear(+t.dataset.y); years = false; }
        else if (t.dataset.d) sel = new Date(view.getFullYear(), view.getMonth(), +t.dataset.d);
        else if (t.dataset.c !== undefined) return dlg.close();
        else if (t.dataset.ok !== undefined) {
          res(iso(sel)); dlg.el.remove(); $('.dlg-dim') && $('.dlg-dim').remove(); return;
        }
        draw();
      };
    });
  }
  function enhanceDate(inp) {
    if (inp.dataset.enhanced) return;
    inp.dataset.enhanced = '1';
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'ip';
    const paint = () => {
      btn.classList.toggle('ph', !inp.value);
      btn.innerHTML = `<span>${inp.value ? dmy(inp.value) : 'dd/mm/yyyy'}</span>${icon('calendar', 'ic ic-sm')}`;
    };
    paint();
    inp.after(btn);
    btn.onclick = async () => {
      const v = await calendar(inp.dataset.title || 'Chagua tarehe', inp.value);
      if (v) { inp.value = v; paint(); inp.dispatchEvent(new Event('change', { bubbles: true })); }
    };
  }

  /* ---------- Toggle groups: <div data-toggle="format" data-input="#id_format"> <button data-value="table">… ---------- */
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-toggle] > button');
    if (!b) return;
    const g = b.parentElement;
    $$('button', g).forEach(x => x.setAttribute('aria-pressed', x === b));
    const inp = g.dataset.input && $(g.dataset.input);
    if (inp) { inp.value = b.dataset.value; inp.dispatchEvent(new Event('change', { bubbles: true })); }
  });

  /* ---------- Open the finished PDF in the phone's PDF reader ----------
     Works in the installed PWA too: the PDF is fetched as a file, saved with a name
     (download), and Android opens it in the PDF reader automatically (no extra button).
     Server: the PDF URL must return Content-Type: application/pdf and
     Content-Disposition: attachment; filename="Scheme_<Somo>_<Darasa>.pdf" */
  async function openPdf(src, filename = 'TLM.pdf', label = 'PDF iko tayari') {
    try {
      let blob = src;
      if (!(src instanceof Blob)) {
        const r = await fetch(src, { credentials: 'same-origin' });
        if (!r.ok) throw new Error('pdf ' + r.status);
        const cd = r.headers.get('Content-Disposition') || '';
        const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)/i);
        if (m) filename = decodeURIComponent(m[1]);
        blob = await r.blob();
      }
      const url = URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10 * 60 * 1000);
    } catch (e) {
      // Last resort: let the browser open the URL itself
      if (!(src instanceof Blob)) window.location.href = src;
      else toast('Imeshindikana kufungua PDF.');
    }
  }

  function toastAction(msg, btnText, onClick, ms = 12000) {
    let w = $('.toast-wrap');
    if (!w) { w = document.createElement('div'); w.className = 'toast-wrap'; document.body.appendChild(w); }
    const t = document.createElement('div');
    t.className = 'toast-tlm';
    t.setAttribute('role', 'status');
    t.innerHTML = `${icon('info')}<span class="grow">${esc(msg)}</span><button type="button" class="tbtn">${icon('download', 'ic ic-sm')}${esc(btnText)}</button>`;
    t.querySelector('.tbtn').onclick = () => { onClick(); t.remove(); };
    w.appendChild(t);
    setTimeout(() => t.remove(), ms);
  }

  /* ---------- G1: generate button fills while the request runs ----------
     <button class="btn-tlm btn-gen" data-gen><span class="gen-fill"></span><span class="gen-label">…</span></button>
     TLM.runGenerate(btn, () => fetch(...)) -> resolves with the fetch Response */
  async function runGenerate(btn, job) {
    const fill = btn.querySelector('.gen-fill');
    const note = document.createElement('p');
    note.className = 'gen-note';
    note.textContent = 'Inaweza kuchukua sekunde chache…';
    btn.after(note);
    btn.classList.add('is-running');
    btn.disabled = true;
    let p = 0;
    const tick = setInterval(() => { p += (92 - p) * 0.06; fill.style.width = p + '%'; }, 250); // eases toward 92%
    try {
      const r = await job();
      clearInterval(tick);
      fill.style.width = '100%';
      await new Promise(z => setTimeout(z, 450));
      return r;
    } catch (err) {
      clearInterval(tick);
      toast('Imeshindikana kutengeneza. Jaribu tena.');
      throw err;
    } finally {
      setTimeout(() => { btn.classList.remove('is-running'); btn.disabled = false; fill.style.width = '0'; note.remove(); }, 500);
    }
  }

  /* ---------- Students: Hawapo & Jumla auto-calculate ----------
     inputs: [data-reg-b] [data-reg-g] [data-att-b] [data-att-g]; outputs: [data-out="regT|attT|absB|absG|absT"] */
  function students(root) {
    const n = s => +($(s, root)?.value || $(s, root)?.textContent || 0);
    const calc = () => {
      const rb = n('[data-reg-b]'), rg = n('[data-reg-g]'), ab = n('[data-att-b]'), ag = n('[data-att-g]');
      const set = (k, v) => { const el = $(`[data-out="${k}"]`, root); if (el) el.textContent = v; };
      set('regT', rb + rg);
      set('attT', ab + ag);
      set('absB', Math.max(0, rb - ab));
      set('absG', Math.max(0, rg - ag));
      set('absT', Math.max(0, rb + rg - ab - ag));
    };
    root.addEventListener('input', calc);
    calc();
  }

  /* ---------- Week accordions: "Fungua zote / Funga zote" ---------- */
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-open-all]'); if (!b) return;
    const all = $$('details.wk');
    const open = all.some(d => !d.open);
    all.forEach(d => d.open = open);
    b.textContent = open ? 'Funga zote' : 'Fungua zote';
  });

  /* ---------- Opening screen: fade out when BOTH the animation (3.9 s) and page load are done ---------- */
  const splashStart = performance.now();
  function hideSplash() {
    const s = document.getElementById('tlm-splash');
    if (!s) return;
    const wait = Math.max(0, 3900 - (performance.now() - splashStart));
    setTimeout(() => { s.classList.add('hide'); setTimeout(() => s.remove(), 450); }, wait);
  }
  if (document.readyState === 'complete') hideSplash();
  else window.addEventListener('load', hideSplash);

  /* ---------- Bottom nav: highlight the tapped tab at once + show a top progress bar ---------- */
  function startNav(a) {
    const nav = a.closest('.bottom-nav');
    if (nav) {
      $$('a', nav).forEach(x => x.classList.remove('active', 'going'));
      a.classList.add('going');
    }
    let bar = document.getElementById('nav-progress');
    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'nav-progress';
      document.body.appendChild(bar);
    }
    bar.classList.add('on');
    bar.style.width = '30%';
    let w = 30;
    clearInterval(bar._t);
    bar._t = setInterval(() => { w += (90 - w) * 0.12; bar.style.width = w + '%'; }, 120);
  }

  document.addEventListener('click', e => {
    const a = e.target.closest('.bottom-nav a[href]');
    if (!a || e.defaultPrevented) return;
    const url = new URL(a.href, location.href);
    if (url.pathname === location.pathname && url.search === location.search) return;
    startNav(a);
  });

  // Back/forward from bfcache: clear the bar
  window.addEventListener('pageshow', () => {
    const b = document.getElementById('nav-progress');
    if (b) { clearInterval(b._t); b.classList.remove('on'); b.style.width = '0'; }
  });

  /* ---------- Auto-grow boxes (one function, used by every page) ----------
     Every textarea grows with its text: no scrollbar inside, nothing cut off,
     and whatever sits below it moves down. Recalculated when the page opens,
     while typing, and when a collapsed week/stage is opened. */
  function autoGrow(el) {
    if (!el || el.tagName !== 'TEXTAREA') return;
    el.style.overflowY = 'hidden';
    el.style.resize = 'none';
    el.style.height = 'auto';            // shrink first, then fit the content
    el.style.height = el.scrollHeight + 'px';
  }

  function growAll(root = document) {
    $$('textarea', root).forEach(autoGrow);
  }

  document.addEventListener('input', e => {
    if (e.target.tagName === 'TEXTAREA') autoGrow(e.target);
  }, true);

  // Opening a week / stage: the boxes inside were hidden, so measure them now
  document.addEventListener('toggle', e => {
    if (e.target.tagName === 'DETAILS' && e.target.open) growAll(e.target);
  }, true);

  window.addEventListener('resize', () => growAll());

  // Web fonts load after the first paint and change the width: measure again
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => growAll());

  /* ---------- Boot ---------- */
  function boot(root = document) {
    $$('select[data-picker]', root).forEach(enhanceSelect);
    $$('input[data-date]', root).forEach(enhanceDate);
    $$('[data-students]', root).forEach(students);
    growAll(root);
  }
  document.addEventListener('DOMContentLoaded', () => boot());

  window.TLM = { toast, toastAction, confirm: confirmDlg, pick, calendar, openPdf, runGenerate, boot, icon, dmy, autoGrow, growAll };
})();
