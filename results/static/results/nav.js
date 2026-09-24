/* Menyu ya makundi (kompyuta) + menyu ya chini (simu). */
(function () {
  // ── Menyu ya makundi: fungua kwa kubonyeza, funga ukibonyeza nje ──
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
    });
  });
  document.addEventListener('click', e => { if (!e.target.closest('.nav-group')) closeGroups(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeGroups(); });

  // ── Menyu ya chini (simu): onyesha ukurasa uliopo ──
  document.querySelectorAll('.bottom-nav a[href]').forEach(a => {
    try {
      if (new URL(a.href, location.href).pathname === location.pathname) {
        a.classList.add('active');
        a.setAttribute('aria-current', 'page');
      }
    } catch (e) {}
  });
})();
