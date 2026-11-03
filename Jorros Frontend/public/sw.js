const SAFE_CACHE = "joross-safe-assets-v2";
const SAFE_PRECACHE = [
  "/offline.html",
  "/manifest.webmanifest",
  "/images/Jorros%20Logo%202.png",
  "/pwa/icon-192.png",
  "/pwa/icon-512.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SAFE_CACHE).then((cache) => cache.addAll(SAFE_PRECACHE)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== SAFE_CACHE).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

function isNextStaticAsset(url) {
  return url.pathname.startsWith("/_next/static/");
}

function isSafeStaticAsset(url) {
  return isNextStaticAsset(url)
    || url.pathname.startsWith("/pwa/")
    || url.pathname === "/manifest.webmanifest"
    || url.pathname === "/images/Jorros%20Logo%202.png"
    || url.pathname === "/images/Jorros Logo 2.png";
}

async function networkFirstSafeAsset(request) {
  try {
    const response = await fetch(request);
    if (response && response.ok && response.type === "basic") {
      const copy = response.clone();
      caches.open(SAFE_CACHE).then((cache) => cache.put(request, copy));
    }
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) return cached;
    throw error;
  }
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Authentication, API responses, staff data, evidence, and page HTML are
  // deliberately never written to the service-worker cache.
  if (url.pathname.startsWith("/api/") || url.pathname.includes("/evidence")) {
    event.respondWith(fetch(request));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match("/offline.html")));
    return;
  }

  if (!isSafeStaticAsset(url)) return;

  // Next development chunk URLs can remain stable while their contents change.
  // Network-first prevents an old My Tasks bundle from surviving a source update.
  // In production, hashed Next assets are still safely cached as an offline fallback.
  if (isNextStaticAsset(url)) {
    event.respondWith(networkFirstSafeAsset(request));
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request).then((response) => {
      if (!response || !response.ok || response.type !== "basic") return response;
      const copy = response.clone();
      caches.open(SAFE_CACHE).then((cache) => cache.put(request, copy));
      return response;
    }))
  );
});
