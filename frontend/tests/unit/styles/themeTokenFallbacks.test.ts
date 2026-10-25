import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

// Guards #10460: a ``var(--token, fallback)`` whose token is never defined
// always resolves to the fallback, so dark mode silently got light-theme
// colours (e.g. white cards on the Trading page). jsdom does not resolve CSS
// variables, so this asserts the source contract directly: every token used
// with a fallback must be defined somewhere (a stylesheet declaration or an
// inline ``'--token': value`` style object).
const SRC = path.resolve(__dirname, '../../../src');

function sourceFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    return /\.(css|tsx?)$/.test(entry.name) ? [full] : [];
  });
}

describe('theme token fallbacks', () => {
  const sources = sourceFiles(SRC).map((file) => ({
    file: path.relative(SRC, file),
    text: fs.readFileSync(file, 'utf-8'),
  }));
  const all = sources.map((s) => s.text).join('\n');

  const isDefined = (token: string) => {
    const escaped = token.replace(/[-]/g, '\\-');
    return new RegExp(`(^|[\\s{;'"])${escaped}['"]?\\s*:`, 'm').test(all);
  };

  it('only falls back from tokens that are actually defined', () => {
    const undefinedUses = sources.flatMap(({ file, text }) =>
      [...text.matchAll(/var\((--[\w-]+)\s*,/g)]
        .map((m) => m[1])
        .filter((token) => !isDefined(token))
        .map((token) => `${file}: ${token}`)
    );
    expect(undefinedUses).toEqual([]);
  });
});
