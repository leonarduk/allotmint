import { defineConfig } from 'vitest/config'
import { loadEnv, type PluginOption } from 'vite'
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

const DEV_SERVER_PORT = 2568

// index.html interpolates %VITE_APP_BASE_URL% into its canonical/og:url and
// JSON-LD tags. Only .env.production sets it, so the dev server warned on
// every load and served the literal placeholder (#7823). Default it to the
// local dev origin unless an .env file or the shell already provides one.
function ensureAppBaseUrl(mode: string): void {
  if (loadEnv(mode, __dirname, 'VITE_APP_BASE_URL').VITE_APP_BASE_URL) return
  process.env.VITE_APP_BASE_URL = `http://localhost:${DEV_SERVER_PORT}`
}

// https://vite.dev/config/
export default defineConfig(({ command, mode }) => {
  const plugins: PluginOption[] = [
    ...react()
  ]

  // Prerender/PWA plugins were intentionally removed because this app now ships
  // as a standard SPA and infrastructure does not consume prerendered artifacts.

  if (command === 'serve') {
    ensureAppBaseUrl(mode)
  }

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
      // AllotMint's dev ports spell the halves of the name on a phone keypad:
      // ALOT -> 2568 (this server), MINT -> 6468 (the backend). See #7811.
      // strictPort is deliberately left off, so a busy 2568 still walks to
      // 2569+ exactly as the Vite default did.
      port: DEV_SERVER_PORT,
      proxy: {
        '/api': {
          target: 'http://backend:6468', // Docker internal hostname
          changeOrigin: true,
          rewrite: (path: string) => path.replace(/^\/api/, '')
        }
      }
    },
    preview: {
      port: DEV_SERVER_PORT
    },
    build: {
      // One stylesheet, emitted with Vite's default content-hashed name under
      // assets/ like every other asset: StaticSiteStack serves assets as
      // immutable for a year, so a fixed name would pin stale CSS (#11028).
      cssCodeSplit: false,
      cssMinify: 'esbuild' as const
    },
    test: {
      environment: 'jsdom',
      setupFiles: './src/setupTests.ts',
      include: ['tests/unit/**/*.test.ts?(x)'],
      // Restore vi.spyOn spies between tests, so a test that fails before its
      // own mockRestore() cannot leave a stubbed console/window/etc. behind
      // for later tests in the file (#10689). vi.fn() mock state is untouched.
      restoreMocks: true,
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
