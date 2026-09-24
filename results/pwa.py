"""
PWA support for the School Results app — Web App Manifest & Service Worker.

The results app lives at /shule/, so its manifest and service worker are
served from /shule/manifest.json and /shule/sw.js (scoped to /shule/).
"""
from django.http import HttpResponse, JsonResponse


def pwa_manifest(request):
    """Serve Web App Manifest so the School Results portal can be installed
    as an app on phones and desktops (like the TLM curriculum app)."""
    manifest = {
        "name": "School Results System Tanzania (SRS V1)",
        "short_name": "SRS V1",
        "description": "Mfumo wa Matokeo ya Shule Tanzania — walimu wanapakia alama za mitihani, kuzalisha PDF, na kugawa matokeo kwa wanafunzi.",
        "start_url": "/shule/",
        "scope": "/shule/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": "#1F7A3D",
        "theme_color": "#124D22",
        "categories": ["education", "productivity", "books"],
        "lang": "sw",
        "dir": "ltr",
        "icons": [
            {
                "src": "/static/results/img/srs-icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "/static/results/img/srs-icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "/static/results/img/srs-icon-1024.png",
                "sizes": "1024x1024",
                "type": "image/png",
                "purpose": "any maskable",
            },
            {
                "src": "/static/results/img/srs-icon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any",
            },
        ],
        "screenshots": [
            {
                "src": "/static/results/img/srs-splash.png",
                "sizes": "1280x640",
                "type": "image/png",
                "form_factor": "wide",
                "label": "SRS V1 — School Results System Tanzania"
            },
            {
                "src": "/static/results/img/srs-splash.png",
                "sizes": "1280x640",
                "type": "image/png",
                "form_factor": "narrow",
                "label": "SRS V1 — School Results System Tanzania"
            },
        ],
        "shortcuts": [
            {
                "name": "Mitihani",
                "short_name": "Mitihani",
                "description": "Angalia mitihani na maendeleo ya uwasilishaji",
                "url": "/shule/",
                "icons": [{"src": "/static/results/img/srs-icon-192.png", "sizes": "192x192"}],
            },
            {
                "name": "Tafuta Matokeo",
                "short_name": "Matokeo",
                "description": "Wanafunzi na wazazi watafute matokeo kwa jina",
                "url": "/shule/matokeo/",
                "icons": [{"src": "/static/results/img/srs-icon-192.png", "sizes": "192x192"}],
            },
            {
                "name": "Binafsi",
                "short_name": "Binafsi",
                "description": "Pakia alama za somo lako binafsi",
                "url": "/shule/binafsi/",
                "icons": [{"src": "/static/results/img/srs-icon-192.png", "sizes": "192x192"}],
            },
        ],
    }
    return JsonResponse(manifest)


def pwa_service_worker(request):
    """Serve the Service Worker for offline caching & PWA install."""
    sw_code = '''const CACHE_NAME = "school-results-v4";

// ── Install ──
self.addEventListener("install", function(event) {
  self.skipWaiting();
});

// ── Activate: wipe every old cache, take control now ──
self.addEventListener("activate", function(event) {
  event.waitUntil(
    caches.keys()
      .then(function(keys) { return Promise.all(keys.map(function(k) { return caches.delete(k); })); })
      .then(function() { return self.clients.claim(); })
  );
});

// ── Fetch ──
// HTML pages (navigations): NETWORK-ONLY. Never serve a cached page — a
// stale HTML kept pointing at an old hashed script and shipped an old
// scanner build. Only if the network is truly unreachable do we show a
// minimal offline notice.
// Everything else (images, css, fonts): network-first with a cache
// fallback, so the app still opens offline but a new deploy always wins
// while online.
self.addEventListener("fetch", function(event) {
  var req = event.request;
  if (req.method !== "GET" || !req.url.startsWith("http")) return;

  var isNavigation = req.mode === "navigate" ||
    (req.headers.get("accept") || "").indexOf("text/html") !== -1;

  if (isNavigation) {
    event.respondWith(
      fetch(req).catch(function() {
        return new Response(
          "<meta charset=utf-8><meta name=viewport content='width=device-width'>" +
          "<body style='font-family:sans-serif;padding:2rem;text-align:center;color:#333'>" +
          "<h3>Huna mtandao</h3><p>Tafadhali angalia intaneti kisha jaribu tena.</p>",
          { headers: { "Content-Type": "text/html; charset=utf-8" }, status: 503 }
        );
      })
    );
    return;
  }

  event.respondWith(
    fetch(req).then(function(response) {
      if (response && response.status === 200 && response.type === "basic") {
        var clone = response.clone();
        caches.open(CACHE_NAME).then(function(cache) { cache.put(req, clone); });
      }
      return response;
    }).catch(function() {
      return caches.match(req).then(function(cached) {
        return cached || new Response("", { status: 504 });
      });
    })
  );
});
'''
    return HttpResponse(sw_code, content_type="application/javascript; charset=utf-8")
