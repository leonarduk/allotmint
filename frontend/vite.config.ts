import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { readdirSync } from 'node:fs'

const require = createRequire(import.meta.url)
const prerender = require('vite-plugin-prerender').default

const __dirname = dirname(fileURLToPath(import.meta.url))
const staticDir = resolve(__dirname, 'dist')
const pageRoutes = readdirSync(resolve(__dirname, 'src/pages'))
  .filter((f) => f.endsWith('.tsx') && !f.endsWith('.test.tsx'))
  .map((f) => '/' + f.replace(/\.tsx$/, '').toLowerCase())

// https://vite.dev/config/
export default defineConfig({
    plugins: [
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
      }),
        prerender({
          staticDir,
          routes: ['/', ...pageRoutes]
        })
      ],
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
})
