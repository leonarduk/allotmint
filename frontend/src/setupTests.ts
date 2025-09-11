import './i18n';
import '@testing-library/jest-dom/vitest';
import { expect } from 'vitest';
import { toHaveNoViolations } from 'jest-axe';

expect.extend(toHaveNoViolations);

// Polyfill for libraries relying on ResizeObserver
class ResizeObserver {
  private readonly cb: ResizeObserverCallback;
  constructor(cb: ResizeObserverCallback) {
    this.cb = cb;
  }
  observe() {
    this.cb(
      [{ contentRect: { width: 400, height: 400 } } as ResizeObserverEntry],
      this
    );
  }
  unobserve() {}
  disconnect() {}
}
declare global {
  interface GlobalThis {
    ResizeObserver: typeof ResizeObserver;
  }
}

globalThis.ResizeObserver = ResizeObserver;
