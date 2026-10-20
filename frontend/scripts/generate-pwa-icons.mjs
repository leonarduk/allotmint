// Regenerates the PWA PNG icons in public/icons/ from public/icons/icon.svg
// (#11023). Run after editing the SVG: `node scripts/generate-pwa-icons.mjs`.
// The PNGs are committed because Chrome's Android install (WebAPK) flow needs
// raster icons at 192 and 512 px.
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const iconsDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
  'public',
  'icons'
);
const source = path.join(iconsDir, 'icon.svg');

const outputs = [
  { file: 'icon-192.png', size: 192 },
  { file: 'icon-512.png', size: 512 },
];

for (const { file, size } of outputs) {
  await sharp(source, { density: 300 })
    .resize(size, size)
    .png({ compressionLevel: 9 })
    .toFile(path.join(iconsDir, file));
  console.log(`wrote ${file}`);
}
