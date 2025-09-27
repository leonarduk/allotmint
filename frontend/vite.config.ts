import { defineConfig } from 'vitest/config'
import type { UserConfig } from 'vitest/config'
import type { PluginOption } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'node:path'
import { globSync } from 'glob'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const staticDir = path.resolve(__dirname, 'dist')

// https://vite.dev/config/
export default defineConfig(({ command }) => {
  const plugins: PluginOption[] = []
  const pageRoutes: string[] = []

  const addPlugin = (plugin: PluginOption | PluginOption[]) => {
    if (Array.isArray(plugin)) {
      plugins.push(...plugin)
    } else {
      plugins.push(plugin)
    }
  }

  addPlugin(react())
  addPlugin(
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['vite.svg'],
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'service-worker.ts',
      manifest: false,
      // enable service worker in dev but avoid caching dev assets
      devOptions: { enabled: true, type: 'module', disableRuntimeConfig: true },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,ico,webmanifest}']
      }
    })
  )

  const shouldPrerender = process.env.ENABLE_PRERENDER === 'true'

  if (command === 'build' && shouldPrerender) {
    const files = globSync('src/pages/**/*.tsx', {
      cwd: __dirname,
      ignore: ['**/*.test.tsx']
    })
    pageRoutes.push(
      ...files.map((file) => `/${path.basename(file, '.tsx').toLowerCase()}`)
    )
    const vitePrerender = require('vite-plugin-prerender')
    const prerenderPlugin = vitePrerender({
      staticDir,
      routes: ['/', ...pageRoutes]
    })
    addPlugin(prerenderPlugin)
  }

  const config: UserConfig = {
    plugins,
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src')
      }
    },
    build: {
      cssCodeSplit: false,
      cssMinify: 'esbuild',
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
        thresholds: {
          lines: 85,
          functions: 85,
          branches: 85,
          statements: 85
        },
        include: ['tests/unit/**/*.test.ts?(x)']
      }
    }
  }
  return config
})

