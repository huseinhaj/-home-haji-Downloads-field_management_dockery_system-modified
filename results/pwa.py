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
    sw_code = '''const CACHE_NAME = "school-results-v2";
const STATIC_ASSETS = [
  "/static/results/img/srs-icon-192.png",
  "/static/results/img/srs-icon-512.png",
  "/static/results/img/srs-icon.svg",
];

// ── Install: cache static assets ──
self.addEventListener("install", function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// ── Activate: clean old caches ──
self.addEventListener("activate", function(event) {
  event.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(k) { return k !== CACHE_NAME; })
            .map(function(k) { return caches.delete(k); })
      );
    })
  );
  self.clients.claim();
});

// ── Fetch: network-first, fallback to cache ──
self.addEventListener("fetch", function(event) {
  if (event.request.method !== "GET") return;
  if (!event.request.url.startsWith("http")) return;

  event.respondWith(
    fetch(event.request)
      .then(function(response) {
        if (response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(function(cache) {
            cache.put(event.request, clone);
          });
        }
        return response;
      })
      .catch(function() {
        return caches.match(event.request).then(function(cached) {
          return cached || new Response("Offline", { status: 503 });
        });
      })
  );
});
'''
    return HttpResponse(sw_code, content_type="application/javascript; charset=utf-8")
