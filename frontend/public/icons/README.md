Progressive Web App icons referenced by `public/manifest.webmanifest` and the
`apple-touch-icon` link in `index.html` (#11023).

- `icon.svg` is the source artwork. Its background is full-bleed and the sprout
  sits inside the central 80% safe zone, so `icon-512.png` doubles as the
  maskable icon.
- `icon-192.png` and `icon-512.png` are generated from it. After editing the
  SVG, regenerate them from `frontend/` with:

  ```bash
  node scripts/generate-pwa-icons.mjs
  ```
