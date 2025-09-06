import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'node:path'

const staticDir = path.resolve(__dirname, 'dist')
const pageRoutes: string[] = []

// https://vite.dev/config/
export default defineConfig(async ({ command }) => {
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
      devOptions: { enabled: true, type: 'module', disableRuntimeConfig: true },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,ico,webmanifest}']
      }
    })
  ]

  if (command === 'build') {
    const { default: vitePrerender } = await import('vite-plugin-prerender')
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

