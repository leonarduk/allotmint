/// <reference lib="webworker" />

// basic service worker for push notifications
self.addEventListener('push', (event: PushEvent) => {
  const data = event.data?.json() || {};
  const title = data.title || 'AllotMint';
  const options: NotificationOptions = {
    body: data.body || data.message || ''
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event: NotificationEvent) => {
  event.notification.close();
  event.waitUntil(self.clients.openWindow('/'));
});

export {};
