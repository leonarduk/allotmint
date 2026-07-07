import { defineConfig } from 'vitest/config'
import type { PluginOption } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// https://vite.dev/config/
export default defineConfig(() => {
  const plugins: PluginOption[] = [
    ...react()
  ]

  // Prerender/PWA plugins were intentionally removed because this app now ships
  // as a standard SPA and infrastructure does not consume prerendered artifacts.

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
      // CI runners have limited, variable RAM shared with other concurrent
      // jobs. Vitest's default fork pool spawns roughly one worker per CPU
      // with no per-worker memory cap, which has intermittently exhausted
      // the runner's heap and crashed workers mid-suite (zero real test
      // failures, just "Worker exited unexpectedly") — see #4810. Capping
      // concurrency trades some wall-clock time for reliability.
      // NOTE: `poolOptions.forks.maxForks` was removed in Vitest 4 — options
      // are now top-level (see the migration guide). Use `maxWorkers`.
      maxWorkers: 2,
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
