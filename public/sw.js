const VERSION = "postlane-cache-v9-ai-mailboxes";
const SHELL_CACHE = `${VERSION}-shell`;
const DATA_CACHE = `${VERSION}-data`;
const API_CACHE_PATHS = [
  "/api/auth/status",
  "/api/auth/me",
  "/api/mailboxes",
  "/api/folders",
  "/api/messages",
  "/api/drafts",
  "/api/spam-rules",
  "/api/push/public-key",
];

const shouldCacheApi = (url) =>
  API_CACHE_PATHS.some(
    (path) => url.pathname === path || url.pathname.startsWith(path + "/"),
  );

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) =>
        cache.addAll([
          "/",
          "/index.html",
          "/manifest.webmanifest",
          "/branding/postlane-icon-192.png",
          "/branding/postlane-logo.png",
          "/branding/postlane-brand-v1.css",
        ]),
      ),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter(
              (key) =>
                key.startsWith("postlane-cache-") && !key.startsWith(VERSION),
            )
            .map((key) => caches.delete(key)),
        ),
      ),
  );
  self.clients.claim();
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "CLEAR_APP_CACHE") {
    event.waitUntil(
      Promise.all([caches.delete(SHELL_CACHE), caches.delete(DATA_CACHE)]),
    );
  }
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          void caches
            .open(SHELL_CACHE)
            .then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() =>
          caches.match(request).then((cached) => cached || caches.match("/")),
        ),
    );
    return;
  }

  if (url.pathname.startsWith("/api/") && shouldCacheApi(url)) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            void caches
              .open(DATA_CACHE)
              .then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() =>
          caches.open(DATA_CACHE).then((cache) =>
            cache.match(request).then(
              (cached) =>
                cached ||
                new Response(JSON.stringify({ detail: "Offline" }), {
                  status: 503,
                  headers: { "Content-Type": "application/json" },
                }),
            ),
          ),
        ),
    );
    return;
  }

  if (["script", "style", "font", "image"].includes(request.destination)) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((response) => {
            if (response.ok) {
              const copy = response.clone();
              void caches
                .open(SHELL_CACHE)
                .then((cache) => cache.put(request, copy));
            }
            return response;
          }),
      ),
    );
  }
});

self.addEventListener("push", (event) => {
  let data = { title: "Postlane", body: "You have a new update.", url: "/" };
  try {
    if (event.data) data = { ...data, ...event.data.json() };
  } catch (_) {}
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/branding/postlane-icon-192.png",
      badge: "/branding/postlane-icon-192.png",
      tag: "postlane-mail",
      data: { url: data.url || "/" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/", self.location.origin)
    .href;
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clients) => {
        const open = clients.find((client) => "focus" in client);
        if (open) {
          open.focus();
          return open.navigate(url);
        }
        return self.clients.openWindow(url);
      }),
  );
});
