/// <reference lib="webworker" />

const sw = self as unknown as ServiceWorkerGlobalScope;

// basic service worker for push notifications
sw.addEventListener('push', (event: PushEvent) => {
  const payload = event.data?.text();
  let data: Record<string, unknown> = {};
  if (payload) {
    try {
      data = JSON.parse(payload);
    } catch {
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

  event.waitUntil(sw.registration.showNotification(title, options));
});

sw.addEventListener('notificationclick', (event: NotificationEvent) => {
  event.notification.close();
  event.waitUntil(sw.clients.openWindow('/'));
});
