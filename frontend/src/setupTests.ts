import '@testing-library/jest-dom/vitest';
// Initialize i18n for components using react-i18next
import './i18n';
// Add accessibility matchers for Vitest using jest-axe's matcher
import { expect, vi } from 'vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import { toHaveNoViolations } from 'jest-axe';
expect.extend(toHaveNoViolations);

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  };
});

// Fix AbortSignal compatibility for React Router data-router tests.
// JSDOM overrides global.AbortController, but Node's undici (used by native Request)
// validates signals against its own AbortSignal class. When createClientSideRequest
// constructs new Request(url, { signal: jsDomSignal }), undici rejects it.
// We patch Request to retry without the signal on that specific TypeError.
if (typeof globalThis.Request !== 'undefined') {
  const _OriginalRequest = globalThis.Request as typeof Request;
  (globalThis as Record<string, unknown>).Request = function PatchedRequest(
    input: RequestInfo | URL,
    init?: RequestInit,
  ) {
    try {
      return new _OriginalRequest(input, init);
    } catch (e) {
      if (init?.signal && e instanceof TypeError) {
        const { signal: _s, ...rest } = init;
        return new _OriginalRequest(input, rest);
      }
      throw e;
    }
  };
}

// Ensure React Testing Library cleans up between tests to avoid cross-test DOM leakage
afterEach(() => cleanup());

// Polyfill matchMedia
if (!('matchMedia' in window)) {
  Object.defineProperty(window, 'matchMedia', {
    value: (query: string) => ({
      matches: false,
      media: query,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
    writable: true,
  });
}

// Polyfill ResizeObserver
if (typeof window.ResizeObserver === 'undefined') {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as any;
}

// Basic IntersectionObserver stub for components relying on visibility detection
if (typeof window.IntersectionObserver === 'undefined') {
  class MockIntersectionObserver {
    private readonly callback: IntersectionObserverCallback;

    constructor(callback: IntersectionObserverCallback) {
      this.callback = callback;
    }

    observe(target: Element) {
      this.callback(
        [
          {
            isIntersecting: true,
            intersectionRatio: 1,
            target,
            time: 0,
            boundingClientRect: target.getBoundingClientRect(),
            intersectionRect: target.getBoundingClientRect(),
            rootBounds: null,
          } as IntersectionObserverEntry,
        ],
        this as unknown as IntersectionObserver,
      );
    }

    unobserve() {}

    disconnect() {}

    takeRecords(): IntersectionObserverEntry[] {
      return [];
    }
  }

  (window as any).IntersectionObserver = MockIntersectionObserver;
}

// Provide non-zero element sizes so chart libraries (e.g., Recharts) can render
// and tests relying on layout don't fail due to 0x0 containers in JSDOM.
const defineSize = (prop: 'offsetWidth' | 'offsetHeight', value: number) => {
  Object.defineProperty(HTMLElement.prototype, prop, {
    configurable: true,
    get() {
      // If an explicit inline style is set, try to parse it; otherwise return default
      const styleVal = (this as HTMLElement).style && (this as HTMLElement).style[prop === 'offsetWidth' ? 'width' : 'height'];
      if (styleVal) {
        const n = parseInt(styleVal.toString(), 10);
        if (!Number.isNaN(n)) return n;
      }
      return value;
    },
  });
};

defineSize('offsetWidth', 800);
defineSize('offsetHeight', 600);

// Fallback for getBoundingClientRect to return a sensible box
if (!HTMLElement.prototype.getBoundingClientRect) {
  HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
    const width = this.offsetWidth || 800;
    const height = this.offsetHeight || 600;
    return {
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: width,
      bottom: height,
      width,
      height,
      toJSON() {},
    } as DOMRect;
  };
}
