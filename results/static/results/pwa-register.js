/* ============================================================
   PWA: Service Worker Registration + Install Prompt
   School Results — Matokeo ya Shule Tanzania
   ============================================================ */

(function() {
  'use strict';

  // ── Register Service Worker (scoped to /shule/) ──
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/shule/sw.js', { scope: '/shule/' })
      .then(function(reg) {
        console.log('[PWA] ✅ SW registered: ', reg.scope);
      })
      .catch(function(err) {
        console.warn('[PWA] ❌ SW registration failed: ', err);
      });
  }

  // ── Install Prompt (beforeinstallprompt event) ──
  let deferredPrompt = null;
  const STORAGE_KEY = 'results-pwa-install-dismissed';

  window.addEventListener('beforeinstallprompt', function(event) {
    // Prevent the default mini-infobar
    event.preventDefault();
    deferredPrompt = event;

    // Show install button only if user hasn't dismissed permanently
    if (!localStorage.getItem(STORAGE_KEY)) {
      showInstallPrompt();
    }
  });

  // ── Install Prompt UI ──
  function showInstallPrompt() {
    // Remove any existing prompt
    const existing = document.getElementById('pwaInstallPrompt');
    if (existing) existing.remove();

    const prompt = document.createElement('div');
    prompt.id = 'pwaInstallPrompt';
    prompt.innerHTML = `
      <div style="
        position: fixed; bottom: 80px; right: 16px; z-index: 999;
        background: #ffffff;
        border: 2px solid #D9A441;
        border-radius: 12px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.18);
        padding: 0.85rem 1rem;
        max-width: 320px;
        animation: resultsPwaIn 400ms cubic-bezier(0.16, 1, 0.3, 1);
        display: flex;
        flex-direction: column;
        gap: 8px;
        color: #0f172a;
      ">
        <style>
          @keyframes resultsPwaIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
          }
        </style>
        <div style="display:flex;align-items:flex-start;gap:8px;">
          <div style="
            width: 40px; height: 40px; flex-shrink: 0;
            border-radius: 10px;
            background: linear-gradient(135deg, #124D22, #1F7A3D);
            display: flex; align-items: center; justify-content: center;
            color: white; font-size: 1.1rem;
          ">
            <i class="fas fa-download"></i>
          </div>
          <div style="flex:1;min-width:0;">
            <strong style="font-size:0.8rem;color:#0f172a;display:block;">
              📱 Sakinisha App — Matokeo ya Shule
            </strong>
            <p style="font-size:0.72rem;color:#475569;margin:2px 0 0;line-height:1.35;">
              Pakia alama za mitihani, tengeneza PDF na ugawie wanafunzi matokeo —
              moja kwa moja kutoka simu yako.
            </p>
          </div>
        </div>
        <div style="display:flex;gap:6px;justify-content:flex-end;">
          <button id="pwaInstallLater" style="
            background: none; border: none;
            color: #64748b;
            font-size: 0.72rem;
            font-weight: 600;
            cursor: pointer; padding: 4px 10px;
            border-radius: 6px;
          ">Baadaye</button>
          <button id="pwaInstallDismiss" style="
            background: none; border: none;
            color: #DC2626;
            font-size: 0.72rem;
            font-weight: 600;
            cursor: pointer; padding: 4px 10px;
            border-radius: 6px;
          ">Usionyeshe tena</button>
          <button id="pwaInstallBtn" style="
            background: linear-gradient(135deg, #D9A441, #B8891E);
            border: none; color: white;
            font-size: 0.72rem;
            font-weight: 700;
            cursor: pointer; padding: 6px 14px;
            border-radius: 6px;
            transition: transform 150ms ease;
          ">Sakinisha</button>
        </div>
      </div>
    `;

    document.body.appendChild(prompt);

    // Install action
    document.getElementById('pwaInstallBtn').addEventListener('click', function() {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      deferredPrompt.userChoice.then(function(result) {
        if (result.outcome === 'accepted') {
          console.log('[PWA] ✅ User installed the app');
        }
        deferredPrompt = null;
        prompt.remove();
      });
    });

    // Dismiss temporarily
    document.getElementById('pwaInstallLater').addEventListener('click', function() {
      prompt.remove();
    });

    // Dismiss permanently
    document.getElementById('pwaInstallDismiss').addEventListener('click', function() {
      localStorage.setItem(STORAGE_KEY, 'true');
      prompt.remove();
    });
  }

  // ── Listen for app installed ──
  window.addEventListener('appinstalled', function() {
    console.log('[PWA] ✅ App installed successfully!');
    const prompt = document.getElementById('pwaInstallPrompt');
    if (prompt) prompt.remove();
  });

  // ── Detect standalone mode (already installed) ──
  if (window.matchMedia('(display-mode: standalone)').matches ||
      window.navigator.standalone === true) {
    console.log('[PWA] ✅ Running in standalone (installed) mode');
    document.documentElement.classList.add('pwa-standalone');
  }
})();
