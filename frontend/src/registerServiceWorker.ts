// Registers public/sw.js, the app-shell service worker that makes the
// deployed frontend an installable PWA (#11023). Production builds only:
// in dev the worker would serve stale Vite modules across hot reloads.
export const SERVICE_WORKER_URL = '/sw.js';

export function registerServiceWorker(
  isProd: boolean = import.meta.env.PROD
): void {
  if (!isProd || !('serviceWorker' in navigator)) return;
  window.addEventListener(
    'load',
    () => {
      navigator.serviceWorker
        .register(SERVICE_WORKER_URL)
        .catch((err) =>
          console.error('Service worker registration failed:', err)
        );
    },
    { once: true }
  );
}
