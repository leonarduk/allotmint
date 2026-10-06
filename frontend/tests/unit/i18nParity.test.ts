import { describe, expect, it } from 'vitest';

import en from '../../src/locales/en/translation.json';
import de from '../../src/locales/de/translation.json';
import es from '../../src/locales/es/translation.json';
import fr from '../../src/locales/fr/translation.json';
import itLocale from '../../src/locales/it/translation.json';
import pt from '../../src/locales/pt/translation.json';

type Tree = { [key: string]: string | Tree };

function flatten(tree: Tree, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') out[path] = value;
    else Object.assign(out, flatten(value, path));
  }
  return out;
}

function placeholders(value: string): string[] {
  return [...value.matchAll(/\{\{\s*([^}\s,]+)[^}]*\}\}/g)]
    .map((m) => m[1])
    .sort();
}

const english = flatten(en as Tree);
const locales: Record<string, Record<string, string>> = {
  de: flatten(de as Tree),
  es: flatten(es as Tree),
  fr: flatten(fr as Tree),
  it: flatten(itLocale as Tree),
  pt: flatten(pt as Tree),
};

describe.each(Object.entries(locales))('locale %s', (_lang, strings) => {
  it('defines every English key', () => {
    const missing = Object.keys(english).filter((key) => !(key in strings));
    expect(missing).toEqual([]);
  });

  it('keeps the same interpolation placeholders as English', () => {
    const mismatched = Object.keys(english).filter(
      (key) =>
        key in strings &&
        placeholders(strings[key]).join(',') !==
          placeholders(english[key]).join(',')
    );
    expect(mismatched).toEqual([]);
  });
});
