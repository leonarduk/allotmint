import '@testing-library/jest-dom/vitest';
// Initialize i18n for components using react-i18next
import './i18n';
// Add accessibility matchers for Vitest using jest-axe's matcher
import { expect } from 'vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import { toHaveNoViolations } from 'jest-axe';
expect.extend(toHaveNoViolations);

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
  HTMLElement.prototype.getBoundingClientRect = function () {
    return {
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: (this as any).offsetWidth || 800,
      bottom: (this as any).offsetHeight || 600,
      width: (this as any).offsetWidth || 800,
      height: (this as any).offsetHeight || 600,
      toJSON() {},
    } as DOMRect;
  } as any;
}
