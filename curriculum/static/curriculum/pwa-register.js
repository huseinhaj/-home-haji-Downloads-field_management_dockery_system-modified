/* ============================================================
   PWA: Service Worker Registration
   TLM Tanzania — Teaching & Learning Materials

   The install promo ("Sakinisha App: Matokeo ya Shule") lives in
   templates/curriculum/partials/install_promo.html — not here.
   ============================================================ */

(function() {
  'use strict';

  // ── Register Service Worker ──
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js', { scope: '/' })
      .then(function(reg) {
        console.log('[PWA] ✅ SW registered: ', reg.scope);
        // Check for a new Service Worker on every load so a rebuilt
        // tlm.css / tlm-ui.js is picked up instead of the cached copy.
        reg.update();
      })
      .catch(function(err) {
        console.warn('[PWA] ❌ SW registration failed: ', err);
      });
  }

  // ── Detect standalone mode (already installed) ──
  if (window.matchMedia('(display-mode: standalone)').matches ||
      window.navigator.standalone === true) {
    console.log('[PWA] ✅ Running in standalone (installed) mode');
    document.documentElement.classList.add('pwa-standalone');
  }
})();
