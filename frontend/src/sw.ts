/// <reference lib="webworker" />

// basic service worker for push notifications
self.addEventListener('push', (event: PushEvent) => {
  const payload = event.data?.text();
  let data: Record<string, unknown> = {};
  if (payload) {
    try {
      data = JSON.parse(payload);
    } catch (err) {
      data = {body: payload};
    }
  }

  const title = typeof data.title === 'string' ? data.title : 'AllotMint';
  const options: NotificationOptions = {
    body:
      typeof data.body === 'string'
        ? data.body
        : typeof data.message === 'string'
            ? data.message
            : ''
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event: NotificationEvent) => {
  event.notification.close();
  event.waitUntil(self.clients.openWindow('/'));
});

export {};
