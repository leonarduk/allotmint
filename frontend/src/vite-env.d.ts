/// <reference types="vite/client" />

declare global {
  interface GlobalThis {
    ResizeObserver: typeof ResizeObserver;
  }
}

export {};
