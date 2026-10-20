import { readFileSync } from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { describe, it, expect, vi } from 'vitest';

// Exercises public/sw.js (#11023) in a vm sandbox with a fake worker global,
// so the caching rules are pinned without a real browser.
const SW_SOURCE = readFileSync(
  path.resolve(__dirname, '../../public/sw.js'),
  'utf-8'
);
const ORIGIN = 'https://app.allotmint.io';
const SHELL_CACHE = 'allotmint-shell-v1';
const ASSET_CACHE = 'allotmint-assets-v1';

type Listener = (event: unknown) => void;
type Route = () => Response;

// In a real worker, relative Request URLs resolve against the worker origin.
class WorkerRequest extends Request {
  constructor(input: string | Request, init?: RequestInit) {
    super(
      typeof input === 'string' ? new URL(input, ORIGIN).href : input,
      init
    );
  }
}

const keyOf = (req: Request | string) =>
  new URL(typeof req === 'string' ? req : req.url, ORIGIN).href;

// Models the one Vary behaviour that matters: a stored response that varies
// on anything is only matched when the lookup passes ignoreVary (origins send
// `Vary: Origin`, and the worker's precache requests carry no Origin header).
function lookup(
  store: Map<string, Response>,
  req: Request | string,
  opts?: { ignoreVary?: boolean }
) {
  const hit = store.get(keyOf(req));
  if (!hit || (hit.headers.has('vary') && !opts?.ignoreVary)) return undefined;
  return hit.clone();
}

function createFakeCaches() {
  const stores = new Map<string, Map<string, Response>>();
  const open = async (name: string) => {
    if (!stores.has(name)) stores.set(name, new Map());
    const store = stores.get(name)!;
    return {
      match: async (req: Request | string, opts?: { ignoreVary?: boolean }) =>
        lookup(store, req, opts),
      put: async (req: Request | string, res: Response) => {
        store.set(keyOf(req), res);
      },
      keys: async () => [...store.keys()].map((url) => new Request(url)),
      delete: async (req: Request | string) => store.delete(keyOf(req)),
    };
  };
  return {
    stores,
    paths: (name: string) =>
      [...(stores.get(name)?.keys() ?? [])].map((u) => new URL(u).pathname),
    api: {
      open,
      keys: async () => [...stores.keys()],
      delete: async (name: string) => stores.delete(name),
      match: async (
        req: string,
        opts: { cacheName: string; ignoreVary?: boolean }
      ) => lookup(stores.get(opts.cacheName) ?? new Map(), req, opts),
    },
  };
}

// Network double keyed by pathname; `offline` makes every request reject.
// Like CloudFront's 403/404 -> /index.html rule, extensionless SPA paths
// fall back to the index.html route.
function createNetwork(routes: Record<string, Route>) {
  const state = { offline: false, routes };
  const fetchMock = vi.fn(async (input: Request | string) => {
    if (state.offline) throw new TypeError('Failed to fetch');
    const { pathname } = new URL(keyOf(input));
    const spaFallback = pathname.includes('.')
      ? undefined
      : state.routes['/index.html'];
    const route = state.routes[pathname] ?? spaFallback;
    return route ? route() : new Response('missing', { status: 404 });
  });
  return { state, fetchMock };
}

function loadWorker(routes: Record<string, Route>) {
  const listeners: Record<string, Listener> = {};
  const fakeCaches = createFakeCaches();
  const network = createNetwork(routes);
  const self = {
    location: new URL(ORIGIN),
    addEventListener: (type: string, fn: Listener) => {
      listeners[type] = fn;
    },
    skipWaiting: vi.fn(async () => undefined),
    clients: { claim: vi.fn(async () => undefined) },
  };
  vm.runInNewContext(SW_SOURCE, {
    self,
    caches: fakeCaches.api,
    fetch: network.fetchMock,
    console,
    Request: WorkerRequest,
    Response,
    URL,
    Set,
  });

  // Resolves to the respondWith() response (undefined if not intercepted),
  // after any waitUntil() background work has settled.
  const dispatchFetch = async (request: Request) => {
    let responded: Promise<Response> | undefined;
    const background: Promise<unknown>[] = [];
    listeners.fetch({
      request,
      respondWith: (p: Promise<Response>) => {
        responded = p;
      },
      waitUntil: (p: Promise<unknown>) => background.push(p),
    });
    const response = await responded;
    await Promise.all(background);
    return response;
  };
  const runLifecycle = async (type: 'install' | 'activate') => {
    let pending: Promise<unknown> = Promise.resolve();
    listeners[type]({ waitUntil: (p: Promise<unknown>) => (pending = p) });
    await pending;
  };
  return { dispatchFetch, runLifecycle, caches: fakeCaches, network };
}

const typed = (type: string, body: string) => () =>
  new Response(body, { headers: { 'content-type': type, vary: 'Origin' } });
const html = (body: string) => typed('text/html', body);
const js = (body = 'js') => typed('text/javascript', body);
const css = (body = 'css') => typed('text/css', body);

const shellFor = (build: string) =>
  `<html><script src="/assets/index-${build}.js"></script>` +
  `<link href="/assets/vendor-${build}.js"><link href="/styles.css"></html>`;

const buildRoutes = (build: string): Record<string, Route> => ({
  '/index.html': html(shellFor(build)),
  [`/assets/index-${build}.js`]: js(),
  [`/assets/vendor-${build}.js`]: js(),
  '/styles.css': css(),
});

const navigation = (url: string) => {
  const req = new Request(url);
  Object.defineProperty(req, 'mode', { value: 'navigate' });
  return req;
};

const withDestination = (url: string, destination: string) => {
  const req = new Request(url);
  Object.defineProperty(req, 'destination', { value: destination });
  return req;
};

describe('service worker', () => {
  it('does not intercept cross-origin API requests', async () => {
    const sw = loadWorker({});
    const res = await sw.dispatchFetch(
      new Request(
        'https://abc.execute-api.eu-west-1.amazonaws.com/portfolio/alice'
      )
    );
    expect(res).toBeUndefined();
    expect(sw.network.fetchMock).not.toHaveBeenCalled();
  });

  it('does not intercept non-GET requests', async () => {
    const sw = loadWorker({});
    const res = await sw.dispatchFetch(
      new Request(`${ORIGIN}/assets/x.js`, { method: 'POST' })
    );
    expect(res).toBeUndefined();
  });

  it('does not intercept runtime config.json', async () => {
    const sw = loadWorker({});
    expect(
      await sw.dispatchFetch(new Request(`${ORIGIN}/config.json`))
    ).toBeUndefined();
  });

  it('precaches the shell and the build it references on install', async () => {
    const sw = loadWorker(buildRoutes('a1'));
    await sw.runLifecycle('install');
    expect(sw.caches.paths(SHELL_CACHE)).toEqual(['/index.html']);
    expect(sw.caches.paths(ASSET_CACHE).sort()).toEqual([
      '/assets/index-a1.js',
      '/assets/vendor-a1.js',
      '/styles.css',
    ]);
  });

  it('serves navigations from the network and refreshes the shell', async () => {
    const sw = loadWorker(buildRoutes('a1'));
    const res = await sw.dispatchFetch(
      navigation(`${ORIGIN}/portfolio?code=abc`)
    );
    expect(await res!.text()).toBe(shellFor('a1'));
    expect(sw.caches.paths(SHELL_CACHE)).toEqual(['/index.html']);
  });

  it('swaps cached assets to the new build when the shell changes', async () => {
    const sw = loadWorker(buildRoutes('a1'));
    await sw.runLifecycle('install');
    await sw.dispatchFetch(new Request(`${ORIGIN}/assets/lazy-a1.js`));
    sw.network.state.routes = buildRoutes('b2');
    await sw.dispatchFetch(navigation(`${ORIGIN}/`));
    expect(sw.caches.paths(ASSET_CACHE).sort()).toEqual([
      '/assets/index-b2.js',
      '/assets/vendor-b2.js',
      '/styles.css',
    ]);
  });

  it('keeps the previous build intact when the new build fails to precache', async () => {
    const sw = loadWorker(buildRoutes('a1'));
    await sw.runLifecycle('install');
    const partial = buildRoutes('b2');
    delete partial['/assets/vendor-b2.js'];
    sw.network.state.routes = partial;
    await sw.dispatchFetch(navigation(`${ORIGIN}/`));

    sw.network.state.offline = true;
    const page = await sw.dispatchFetch(navigation(`${ORIGIN}/`));
    expect(await page!.text()).toBe(shellFor('a1'));
    expect(sw.caches.paths(ASSET_CACHE)).toEqual(
      expect.arrayContaining(['/assets/index-a1.js', '/assets/vendor-a1.js'])
    );
  });

  it('skips re-precaching when the shell still references the same build', async () => {
    const sw = loadWorker(buildRoutes('a1'));
    await sw.runLifecycle('install');
    sw.network.fetchMock.mockClear();
    await sw.dispatchFetch(navigation(`${ORIGIN}/`));
    expect(sw.network.fetchMock).toHaveBeenCalledTimes(1);
  });

  it('opens offline to the cached shell with its scripts and styles', async () => {
    const sw = loadWorker(buildRoutes('a1'));
    await sw.runLifecycle('install');
    sw.network.state.offline = true;

    const page = await sw.dispatchFetch(navigation(`${ORIGIN}/watchlist`));
    expect(await page!.text()).toBe(shellFor('a1'));
    const script = await sw.dispatchFetch(
      new Request(`${ORIGIN}/assets/index-a1.js`)
    );
    expect(script!.ok).toBe(true);
    const styles = await sw.dispatchFetch(
      withDestination(`${ORIGIN}/styles.css`, 'style')
    );
    expect(await styles!.text()).toBe('css');
  });

  it('does not store non-HTML or redirected navigations as the shell', async () => {
    const redirected = html(shellFor('a1'))();
    Object.defineProperty(redirected, 'redirected', { value: true });
    const sw = loadWorker({
      '/robots.txt': () =>
        new Response('User-agent: *', {
          headers: { 'content-type': 'text/plain' },
        }),
      '/': () => redirected,
    });
    await sw.dispatchFetch(navigation(`${ORIGIN}/robots.txt`));
    await sw.dispatchFetch(navigation(`${ORIGIN}/`));
    expect(sw.caches.paths(SHELL_CACHE)).toEqual([]);
  });

  it('serves hashed assets cache-first', async () => {
    const url = `${ORIGIN}/assets/index-abc123.js`;
    const sw = loadWorker({ '/assets/index-abc123.js': js() });
    await sw.dispatchFetch(new Request(url));
    await sw.dispatchFetch(new Request(url));
    expect(sw.network.fetchMock).toHaveBeenCalledTimes(1);
    expect(sw.caches.paths(ASSET_CACHE)).toEqual(['/assets/index-abc123.js']);
  });

  it('serves unhashed styles network-first so a deploy is picked up', async () => {
    const sw = loadWorker({ '/styles.css': css('v1') });
    await sw.dispatchFetch(withDestination(`${ORIGIN}/styles.css`, 'style'));
    sw.network.state.routes = { '/styles.css': css('v2') };
    const res = await sw.dispatchFetch(
      withDestination(`${ORIGIN}/styles.css`, 'style')
    );
    expect(await res!.text()).toBe('v2');
  });

  it('deletes outdated allotmint caches on activate but keeps others', async () => {
    const sw = loadWorker({});
    await sw.caches.api.open('allotmint-shell-v0');
    await sw.caches.api.open(ASSET_CACHE);
    await sw.caches.api.open('unrelated-cache');
    await sw.runLifecycle('activate');
    expect([...sw.caches.stores.keys()].sort()).toEqual([
      ASSET_CACHE,
      'unrelated-cache',
    ]);
  });
});
