/* AllotMint service worker (#11023).
 *
 * Deliberately dependency-free: vite-plugin-pwa/Workbox were removed in
 * 91b83afa during dependency hardening, so this file is plain JS served
 * verbatim from public/.
 *
 * Scope is the app shell only:
 *   - navigations: network-first, falling back to the cached index.html so an
 *     installed app opens offline instead of showing the browser error page;
 *   - whenever a new index.html is cached, the scripts/styles it references
 *     are precached too (the first visit is not yet controlled by the worker,
 *     and sw.js itself does not change between releases, so install alone
 *     would never pick up a new build);
 *   - /assets/*: cache-first (Vite content-hashes these, so they never change);
 *   - other same-origin scripts/styles (styles.css is emitted unhashed, see
 *     assetFileNames in vite.config.ts): network-first with cache fallback;
 *   - everything else, including /config.json and all API traffic (which is
 *     cross-origin), is NOT intercepted. Financial data is never cached here.
 *
 * Bump CACHE_VERSION when this file's caching behaviour changes; activate
 * deletes every cache that does not match the current names.
 */
const CACHE_VERSION = 'v1';
const SHELL_CACHE = `allotmint-shell-${CACHE_VERSION}`;
const ASSET_CACHE = `allotmint-assets-${CACHE_VERSION}`;
const SHELL_URL = '/index.html';
const SHELL_REFERENCE = /(?:src|href)="(\/(?:assets\/[^"]+|styles\.css))"/g;
// Origins may send `Vary: Origin`; module scripts carry an Origin header but
// the worker's own precache fetches do not, so a Vary-respecting lookup would
// always miss. Entries are keyed by URL only (hashed or shell-scoped).
const MATCH_OPTIONS = { ignoreVary: true };

// Only store a response as the shell if it really is HTML served directly:
// a navigation to e.g. /robots.txt must not overwrite it, and Chrome refuses
// to replay a redirected response (the canonical-host 301 from
// cdk/functions/viewer-request.js) for a navigation request.
function isCacheableShell(response) {
  const type = response.headers.get('content-type') || '';
  return response.ok && !response.redirected && type.includes('text/html');
}

function shellReferences(html) {
  return [...new Set([...html.matchAll(SHELL_REFERENCE)].map((m) => m[1]))];
}

// CloudFront answers a missing object (e.g. a chunk pruned by a newer deploy)
// with index.html and HTTP 200 (StaticSiteStack error responses), so `ok`
// alone would let an HTML fallback be cached under a script/style URL.
function isCacheableAsset(response) {
  const type = response.headers.get('content-type') || '';
  return response.ok && !type.includes('text/html');
}

async function cacheResource(cache, path) {
  const response = await fetch(path);
  if (!isCacheableAsset(response)) {
    throw new Error(`${path} was not a cacheable asset (${response.status})`);
  }
  await cache.put(path, response);
}

// Stores a fresh index.html and, if it points at a different build than the
// cached one, precaches that build's scripts/styles and drops the previous
// build's assets so the cache stays bounded to one release. The new shell is
// only committed once every asset it references is cached: on any precache
// failure the previous shell and its assets stay intact (a coherent offline
// fallback) and the next navigation retries, since the refs still differ.
async function storeShell(response) {
  const shellCache = await caches.open(SHELL_CACHE);
  const previous = await shellCache.match(SHELL_URL, MATCH_OPTIONS);
  const previousRefs = previous ? shellReferences(await previous.text()) : [];
  const refs = shellReferences(await response.clone().text());

  const unchanged =
    previous &&
    refs.length === previousRefs.length &&
    refs.every((ref) => previousRefs.includes(ref));
  if (unchanged) {
    await shellCache.put(SHELL_URL, response);
    return;
  }

  const assetCache = await caches.open(ASSET_CACHE);
  const failures = (
    await Promise.allSettled(refs.map((ref) => cacheResource(assetCache, ref)))
  ).filter((r) => r.status === 'rejected');
  if (failures.length > 0) {
    failures.forEach((r) =>
      console.warn('Shell asset precache failed:', r.reason)
    );
    return;
  }

  await shellCache.put(SHELL_URL, response);
  const stale = (await assetCache.keys()).filter(
    (req) => !refs.includes(new URL(req.url).pathname)
  );
  await Promise.all(stale.map((req) => assetCache.delete(req)));
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    fetch(new Request(SHELL_URL, { cache: 'reload' }))
      .then((response) =>
        isCacheableShell(response) ? storeShell(response) : undefined
      )
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  const keep = [SHELL_CACHE, ASSET_CACHE];
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter(
              (key) => key.startsWith('allotmint-') && !keep.includes(key)
            )
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

// `settleBackground` resolves the waitUntil() promise the fetch listener
// registered synchronously; some engines reject waitUntil() calls made after
// dispatch (e.g. after an await), so the shell refresh is handed over here.
async function networkFirstNavigation(request, settleBackground) {
  let background = Promise.resolve();
  try {
    const response = await fetch(request);
    if (isCacheableShell(response)) {
      background = storeShell(response.clone());
    }
    return response;
  } catch (err) {
    const cached = await caches.match(SHELL_URL, {
      ...MATCH_OPTIONS,
      cacheName: SHELL_CACHE,
    });
    if (cached) return cached;
    throw err;
  } finally {
    settleBackground(
      background.catch((err) => console.warn('Shell refresh failed:', err))
    );
  }
}

async function cacheFirstAsset(request) {
  const cache = await caches.open(ASSET_CACHE);
  const cached = await cache.match(request, MATCH_OPTIONS);
  if (cached) return cached;
  const response = await fetch(request);
  if (isCacheableAsset(response)) {
    await cache.put(request, response.clone());
  }
  return response;
}

async function networkFirstStatic(request) {
  const cache = await caches.open(ASSET_CACHE);
  try {
    const response = await fetch(request);
    if (isCacheableAsset(response)) {
      await cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    const cached = await cache.match(request, MATCH_OPTIONS);
    if (cached) return cached;
    throw err;
  }
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === 'navigate') {
    let settleBackground;
    event.waitUntil(
      new Promise((resolve) => {
        settleBackground = resolve;
      })
    );
    event.respondWith(networkFirstNavigation(request, settleBackground));
  } else if (url.pathname.startsWith('/assets/')) {
    event.respondWith(cacheFirstAsset(request));
  } else if (
    request.destination === 'script' ||
    request.destination === 'style'
  ) {
    event.respondWith(networkFirstStatic(request));
  }
});
