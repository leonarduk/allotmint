/// <reference lib="webworker" />

const CACHE_NAME = 'allotmint-cache-v1';
const CORE_ASSETS = [
  '/',
  '/index.html',
  '/manifest.webmanifest'
];

self.addEventListener('install', (event: ExtendableEvent) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event: ExtendableEvent) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event: FetchEvent) => {
  event.respondWith(
    caches.match(event.request).then((response) => response || fetch(event.request))
  );
});

self.addEventListener('push', (event: PushEvent) => {
  const payload = event.data?.text();
  let data: Record<string, unknown> = {};
  if (payload) {
    try {
      data = JSON.parse(payload);
    } catch {
      data = { body: payload };
    }
  }
  const title = typeof data.title === 'string' ? data.title : 'AllotMint';
  const options: NotificationOptions = {
    body: typeof data.body === 'string' ? data.body : ''
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event: NotificationEvent) => {
  event.notification.close();
  event.waitUntil(self.clients.openWindow('/'));
});

export {};
