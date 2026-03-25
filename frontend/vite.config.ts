import { defineConfig } from 'vitest/config'
import type { PluginOption } from 'vite'
import type { UserConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import fg from 'fast-glob'

const pageRoutes: string[] = []

// https://vite.dev/config/
export default defineConfig(({ command }) => {
  const plugins: PluginOption[] = [
    ...react()
  ]

  if (command === 'build') {
    const files = fg.sync('src/pages/**/*.tsx', {
      cwd: __dirname,
      ignore: ['**/*.test.tsx']
    })
    pageRoutes.push(
      ...files.map((file) => `/${path.basename(file, '.tsx').toLowerCase()}`)
    )
    const prerenderRoutes = ['/', ...pageRoutes]
    if (prerenderRoutes.length > 0) {
      console.info(`[vite] Skipping legacy prerender plugin; computed ${prerenderRoutes.length} routes.`)
    }
  }

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
