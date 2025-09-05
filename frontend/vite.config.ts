import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { readdirSync } from 'node:fs'
import { createRequire } from 'module'

const require = createRequire(import.meta.url)

const __dirname = dirname(fileURLToPath(import.meta.url))
const staticDir = resolve(__dirname, 'dist')
const pageRoutes = readdirSync(resolve(__dirname, 'src/pages'))
  .filter((f) => f.endsWith('.tsx') && !f.endsWith('.test.tsx'))
  .map((f) => '/' + f.replace(/\.tsx$/, '').toLowerCase())

// https://vite.dev/config/
export default defineConfig(({ command }) => {
  const plugins = [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['vite.svg'],
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'service-worker.ts',
      manifest: false,
      // enable service worker in dev but avoid caching dev assets
      devOptions: { enabled: true, disableRuntimeConfig: true },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,ico,webmanifest}']
      }
    })
  ]

  if (command === 'build') {
    const vitePrerender = require('vite-plugin-prerender').default
    plugins.push(
      vitePrerender({
        staticDir,
        routes: ['/', ...pageRoutes]
      })
    )
  }

  return {
    plugins,
    build: {
      cssCodeSplit: false,
      cssMinify: 'esbuild',
      rollupOptions: {
        output: {
          assetFileNames: (assetInfo) => {
            if (assetInfo.name && assetInfo.name.endsWith('.css')) {
              return 'styles.css'
            }
            return 'assets/[name]-[hash][extname]'
          }
        }
      }
    }
  }
})
