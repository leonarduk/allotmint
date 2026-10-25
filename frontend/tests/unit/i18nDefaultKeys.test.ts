import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

import { describe, expect, it } from 'vitest';

import en from '../../src/locales/en/translation.json';

/**
 * Guards against `t('some.key', 'Inline default')` call sites whose key is
 * missing from en/translation.json (#10872). i18next silently falls back to
 * the inline default, so a missing key renders English in every locale and
 * never shows up at runtime.
 *
 * Scope: only `t(...)` calls whose first argument is a single- or
 * double-quoted string literal are checked. Keys built dynamically (template
 * literals such as `t(\`trendWatch.verdict.${v}\`)`, variables, or string
 * concatenation) cannot be resolved statically and are out of scope, as are
 * method-style calls such as `i18n.t(...)`. A key that only exists in plural
 * form (`key_one` / `key_other` / ...) is accepted, because i18next resolves
 * those when the call passes `count`.
 */

type Tree = { [key: string]: unknown };

const SRC_DIR = join(__dirname, '../../src');
const SOURCE_FILE = /\.(ts|tsx)$/;
const TEST_FILE = /\.(test|spec)\.(ts|tsx)$/;
// `t(` not preceded by an identifier char or `.`, then a quoted literal key,
// then either more arguments or the closing paren.
const T_CALL = /(?<![\w$.])t\(\s*(['"])([^'"`\s]+)\1\s*[,)]/g;
const PLURAL_SUFFIXES = ['zero', 'one', 'two', 'few', 'many', 'other'];

function flattenKeys(tree: Tree, prefix = ''): Set<string> {
  const out = new Set<string>();
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      for (const nested of flattenKeys(value as Tree, path)) out.add(nested);
    } else {
      out.add(path);
    }
  }
  return out;
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return SOURCE_FILE.test(name) && !TEST_FILE.test(name) ? [full] : [];
  });
}

function isDefined(keys: Set<string>, key: string): boolean {
  return keys.has(key) || PLURAL_SUFFIXES.some((s) => keys.has(`${key}_${s}`));
}

function findMissing(keys: Set<string>): string[] {
  const missing: string[] = [];
  for (const file of sourceFiles(SRC_DIR)) {
    const text = readFileSync(file, 'utf8');
    for (const match of text.matchAll(T_CALL)) {
      const key = match[2];
      if (isDefined(keys, key)) continue;
      const line = text.slice(0, match.index).split('\n').length;
      missing.push(`${relative(SRC_DIR, file)}:${line} ${key}`);
    }
  }
  return missing;
}

describe('literal t() keys', () => {
  const keys = flattenKeys(en as Tree);

  it('scans a non-trivial number of call sites', () => {
    const total = sourceFiles(SRC_DIR).reduce(
      (sum, file) =>
        sum + [...readFileSync(file, 'utf8').matchAll(T_CALL)].length,
      0
    );
    expect(total).toBeGreaterThan(100);
  });

  it('are all defined in en/translation.json', () => {
    expect(findMissing(keys)).toEqual([]);
  });
});
