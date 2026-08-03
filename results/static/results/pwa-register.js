/* ============================================================
   PWA: Service Worker Registration + Install Prompt
   School Results System (SRS V1) — Tanzania
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

  // ── Helpers ──
  function isStandalone() {
    return window.matchMedia('(display-mode: standalone)').matches ||
           window.navigator.standalone === true;
  }

  function isIOS() {
    return /iphone|ipad|ipod/i.test(navigator.userAgent) ||
           (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  }

  function removePrompt() {
    const el = document.getElementById('pwaInstallPrompt');
    if (el) el.remove();
  }

  // ── Main entry: called by header / drawer / floating buttons ──
  function requestInstall() {
    if (isStandalone()) {
      // Already installed — nothing to do
      return;
    }
    if (deferredPrompt) {
      // Native install prompt (Chrome / Android / Edge)
      deferredPrompt.prompt();
      deferredPrompt.userChoice.then(function(result) {
        if (result.outcome === 'accepted') {
          console.log('[PWA] ✅ User installed the app');
        }
        deferredPrompt = null;
        removePrompt();
      });
    } else if (isIOS()) {
      // iOS Safari has no native prompt — show instructions
      showIOSInstructions();
    } else {
      // Prompt not fired yet — show the floating card; the native prompt
      // will be triggered from there once beforeinstallprompt fires.
      showInstallPrompt();
    }
  }

  // ── Floating install prompt card ──
  function showInstallPrompt() {
    if (isStandalone()) return;
    removePrompt();

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
              📱 Sakinisha App — SRS V1
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
      if (deferredPrompt) {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(function(result) {
          if (result.outcome === 'accepted') {
            console.log('[PWA] ✅ User installed the app');
          }
          deferredPrompt = null;
          removePrompt();
        });
      } else {
        // No native prompt yet — guide the user with a styled toast
        showInstallGuide();
      }
    });

    // Dismiss temporarily
    document.getElementById('pwaInstallLater').addEventListener('click', function() {
      removePrompt();
    });

    // Dismiss permanently
    document.getElementById('pwaInstallDismiss').addEventListener('click', function() {
      localStorage.setItem(STORAGE_KEY, 'true');
      removePrompt();
    });
  }

  // ── Styled guide toast (no native prompt available yet) ──
  function showInstallGuide() {
    removePrompt();
    const toast = document.createElement('div');
    toast.id = 'pwaInstallGuide';
    toast.innerHTML = `
      <div style="
        position: fixed; bottom: 80px; right: 16px; z-index: 999;
        background: #ffffff; border: 2px solid #D9A441; border-radius: 12px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.18);
        padding: 0.85rem 1rem; max-width: 320px;
        animation: resultsPwaIn 400ms cubic-bezier(0.16, 1, 0.3, 1);
        color: #0f172a;
      ">
        <strong style="font-size:0.8rem;display:block;margin-bottom:4px;">📱 Sakinisha App — SRS V1</strong>
        <p style="font-size:0.75rem;color:#475569;line-height:1.5;margin:0 0 8px;">
          Bonyeza menyu ya browser (⋮) → <strong>"Sakinisha app"</strong> / "Add to Home screen"
          kuweka SRS V1 kwenye skrini yako.
        </p>
        <div style="display:flex;justify-content:flex-end;">
          <button id="pwaGuideClose" style="
            background: linear-gradient(135deg, #D9A441, #B8891E); border:none;
            color:white; font-size:0.72rem; font-weight:700; cursor:pointer;
            padding:6px 14px; border-radius:6px;
          ">Sawa ✓</button>
        </div>
      </div>
    `;
    document.body.appendChild(toast);
    document.getElementById('pwaGuideClose').addEventListener('click', function() {
      toast.remove();
    });
  }

  // ── iOS instructions modal ──
  function showIOSInstructions() {
    if (document.getElementById('pwaIOSModal')) return;
    const modal = document.createElement('div');
    modal.id = 'pwaIOSModal';
    modal.innerHTML = `
      <div style="
        position: fixed; inset: 0; z-index: 1000;
        background: rgba(0,0,0,0.55);
        display: flex; align-items: center; justify-content: center;
        padding: 20px;
      " onclick="if(event.target===this)window.SRSInstall&&SRSInstall.closeIOS()">
        <div style="
          background: #ffffff; border-radius: 16px;
          max-width: 380px; width: 100%;
          padding: 1.4rem;
          border: 2px solid #D9A441;
          box-shadow: 0 16px 48px rgba(0,0,0,0.3);
          color: #0f172a;
        ">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
            <div style="
              width: 44px; height: 44px; border-radius: 11px;
              background: linear-gradient(135deg, #124D22, #1F7A3D);
              display:flex;align-items:center;justify-content:center;
              color:white;font-size:1.15rem;
            "><i class="fas fa-download"></i></div>
            <div>
              <strong style="font-size:0.95rem;display:block;">Sakinisha App — SRS V1</strong>
              <span style="font-size:0.72rem;color:#475569;">iPhone / iPad</span>
            </div>
          </div>
          <p style="font-size:0.8rem;color:#475569;line-height:1.55;margin:0 0 12px;">
            Ili kuweka SRS V1 kwenye skrini yako ya nyumbani (kama app):
          </p>
          <ol style="font-size:0.82rem;color:#0f172a;line-height:1.8;padding-left:1.1rem;margin:0 0 14px;">
            <li>Fungua ukurasa huu kwenye <strong>Safari</strong></li>
            <li>Bonyeza kitufe cha <strong>Share</strong> <i class="fas fa-share" style="color:#2563EB;"></i> (chini ya skrini)</li>
            <li>Chagua <strong>"Add to Home Screen"</strong> / "Ongeza kwenye Skrini ya Nyumbani"</li>
            <li>Bonyeza <strong>Add</strong> — App itaonekana kwenye skrini yako!</li>
          </ol>
          <button id="pwaIOSClose" style="
            width:100%; padding: 10px;
            background: linear-gradient(135deg, #D9A441, #B8891E);
            border:none; color:white; font-weight:700;
            border-radius: 8px; font-size: 0.85rem; cursor:pointer;
          ">Nimeelewa ✓</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    document.getElementById('pwaIOSClose').addEventListener('click', function() {
      modal.remove();
    });
  }

  // ── Listen for app installed ──
  window.addEventListener('appinstalled', function() {
    console.log('[PWA] ✅ App installed successfully!');
    removePrompt();
    const iosModal = document.getElementById('pwaIOSModal');
    if (iosModal) iosModal.remove();
  });

  // ── Detect standalone mode (already installed) ──
  if (isStandalone()) {
    console.log('[PWA] ✅ Running in standalone (installed) mode');
    document.documentElement.classList.add('pwa-standalone');
  }

  // ── Public API used by header / drawer / bottom-nav buttons ──
  window.SRSInstall = {
    prompt: requestInstall,
    isStandalone: isStandalone,
    isIOS: isIOS,
    closeIOS: function() {
      const m = document.getElementById('pwaIOSModal');
      if (m) m.remove();
    }
  };
})();
