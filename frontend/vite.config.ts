import { defineConfig } from 'vitest/config'
import type { PluginOption } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'node:path'
import { glob } from 'glob'

const staticDir = path.resolve(__dirname, 'dist')
const pageRoutes: string[] = []

// https://vite.dev/config/
export default defineConfig(async ({ command }) => {
  const plugins: PluginOption[] = [
    ...react(),
    ...VitePWA({
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
  ]

  if (command === 'build') {
    const files = await glob('src/pages/**/*.tsx', {
      cwd: __dirname,
      ignore: ['**/*.test.tsx']
    })
    pageRoutes.push(
      ...files.map((file) => `/${path.basename(file, '.tsx')}`)
    )
    const { createRequire } = await import('node:module')
    const require = createRequire(import.meta.url)
    const vitePrerender = require('vite-plugin-prerender')
    const prerenderPlugin = vitePrerender({
      staticDir,
      routes: ['/', ...pageRoutes]
    })
    plugins.push(...(Array.isArray(prerenderPlugin) ? prerenderPlugin : [prerenderPlugin]))
  }

  const config = {
    plugins,
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
      setupFiles: './src/setupTests.ts'
    }
  }
  return config
})

