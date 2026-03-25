import { defineConfig } from 'vitest/config'
import type { PluginOption } from 'vite'
import type { UserConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// https://vite.dev/config/
export default defineConfig(() => {
  const plugins: PluginOption[] = [
    ...react()
  ]

  // Prerender/PWA plugins were intentionally removed because this app now ships
  // as a standard SPA and infrastructure does not consume prerendered artifacts.

  const config: UserConfig = {
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
          rewrite: (path) => path.replace(/^\/api/, '') // Optional: strip /api prefix
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
      coverage: {
        provider: 'v8',
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
