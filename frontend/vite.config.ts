import { defineConfig } from 'vitest/config'
import type { PluginOption } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import fs from 'node:fs'

// Local dev instances (e.g. separate worktrees/clones) each run their own
// backend on a port chosen by scripts/bash/run-local-api.sh or
// scripts/run-backend.ps1, recorded in .local/ports/backend.port at the
// repo root. Pick that up automatically so `npm run dev` connects to the
// right backend without manual VITE_ALLOTMINT_API_BASE wiring (see #5760).
// Only applies to the dev server — production builds are unaffected.
function readLocalBackendPort(): string | null {
  const portFile = path.resolve(__dirname, '..', '.local', 'ports', 'backend.port')
  try {
    const port = fs.readFileSync(portFile, 'utf-8').trim()
    return /^\d+$/.test(port) ? port : null
  } catch {
    return null
  }
}

// https://vite.dev/config/
export default defineConfig(({ command }) => {
  const plugins: PluginOption[] = [
    ...react()
  ]

  // Prerender/PWA plugins were intentionally removed because this app now ships
  // as a standard SPA and infrastructure does not consume prerendered artifacts.

  if (command === 'serve' && !process.env.VITE_ALLOTMINT_API_BASE) {
    const backendPort = readLocalBackendPort()
    if (backendPort) {
      const apiBase = `http://localhost:${backendPort}`
      process.env.VITE_ALLOTMINT_API_BASE = apiBase
      console.log(`[vite] Connecting to local backend at ${apiBase} (from .local/ports/backend.port)`)
    }
  }

  const config = {
    plugins,
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src')
      }
    },
    server: {
      proxy: {
        '/api': {
          target: 'http://backend:8000', // Docker internal hostname
          changeOrigin: true,
          rewrite: (path: string) => path.replace(/^\/api/, '')
        }
      }
    },
    build: {
      cssCodeSplit: false,
      cssMinify: 'esbuild' as const,
      rollupOptions: {
        output: {
          assetFileNames: (assetInfo: { name?: string }) => {
            if (assetInfo.name && assetInfo.name.endsWith('.css')) {
              return 'styles.css'
            }
            return 'assets/[name]-[hash][extname]'
          }
        }
      }
    },
    test: {
      environment: 'jsdom',
      setupFiles: './src/setupTests.ts',
      include: ['tests/unit/**/*.test.ts?(x)'],
      // Per-test ceiling. MUST stay above MENU_INTERACTION_TIMEOUT_MS
      // (tests/support/menuInteractionTimeout.ts — 8000ms under CI). If it
      // drops below, vitest kills the test before an inner waitFor can spend
      // its budget, so the CI headroom added in #6126 becomes unreachable and
      // the flake resurfaces as a bare "Test timed out" (#6982). Retune the
      // two values together, never one alone.
      testTimeout: process.env.CI ? 20000 : 10000,
      coverage: {
        provider: 'v8' as const, // literal required by CoverageV8Options — widened to string without explicit annotation
        reporter: ['text', 'html'],
        include: ['tests/unit/**/*.test.ts?(x)'],
        thresholds: {
          lines: 85,
          functions: 85,
          branches: 85,
          statements: 85
        }
      }
    }
  }
  return config
})
