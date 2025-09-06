import "./i18n";
import "@testing-library/jest-dom";

// Polyfill for libraries relying on ResizeObserver (e.g. recharts)
class ResizeObserver {
  private readonly cb: ResizeObserverCallback;
  constructor(cb: ResizeObserverCallback) {
    this.cb = cb;
  }
  observe() {
    this.cb([{ contentRect: { width: 400, height: 400 } } as ResizeObserverEntry], this);
  }
  unobserve() {}
  disconnect() {}
}
declare global {
  interface GlobalThis {
    ResizeObserver: typeof ResizeObserver;
    sparks: Record<string, any>;
  }
}

globalThis.ResizeObserver = ResizeObserver;
globalThis.sparks = {};
