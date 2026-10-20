import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

// Guards the PWA wiring (#11023) against renames: index.html must link the
// manifest, and every manifest icon must exist at the size it declares.
const FRONTEND = path.resolve(__dirname, '../..');
const PUBLIC = path.join(FRONTEND, 'public');

type ManifestIcon = {
  src: string;
  sizes: string;
  type: string;
  purpose?: string;
};

const manifest = JSON.parse(
  readFileSync(path.join(PUBLIC, 'manifest.webmanifest'), 'utf-8')
) as { icons: ManifestIcon[] };

// PNG IHDR: width and height are big-endian uint32s at byte offsets 16 and 20.
function pngSize(file: string): string {
  const bytes = readFileSync(file);
  return `${bytes.readUInt32BE(16)}x${bytes.readUInt32BE(20)}`;
}

describe('PWA manifest', () => {
  it('is linked from index.html', () => {
    const html = readFileSync(path.join(FRONTEND, 'index.html'), 'utf-8');
    expect(html).toContain(
      '<link rel="manifest" href="/manifest.webmanifest"/>'
    );
  });

  it('declares 192px and 512px icons, including a maskable one', () => {
    const sizes = manifest.icons.map((icon) => icon.sizes);
    expect(sizes).toEqual(expect.arrayContaining(['192x192', '512x512']));
    expect(manifest.icons.some((icon) => icon.purpose === 'maskable')).toBe(
      true
    );
  });

  it.each(manifest.icons)('ships $src at its declared size', (icon) => {
    expect(icon.type).toBe('image/png');
    expect(pngSize(path.join(PUBLIC, icon.src))).toBe(icon.sizes);
  });
});
