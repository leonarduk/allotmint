import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

// Guards #8168 (follow-up to #8151): Tailwind's slate/gray palette classes are
// not themed, so light-only backgrounds, borders and dark text render as
// white-on-white or dark-on-dark in the app's dark theme. Use the surface
// tokens instead (`bg-[var(--surface-card-bg)]`, `text-[var(--surface-muted-color)]`,
// `text-[var(--surface-card-color)]`, `border-[var(--surface-card-border)]`, or
// `surface.module.css`). `dark:` slate/gray variants are also banned: they follow
// the OS colour scheme, not the app's `data-theme` toggle.
//
// Intentionally fixed dark colours (e.g. `bg-slate-900 text-white` buttons,
// `bg-gray-800` inputs, skeleton `bg-gray-700`) stay readable in both themes and
// are not matched here. Coloured status badges and accents (e.g. Bots
// STATUS_CLASSES, StrategyLibrary TONES, indigo/blue active states) are
// intentionally theme-independent, commented at their definition sites, and
// out of scope for this guard (it only matches neutral slate/gray). Neutral
// fills (secondary buttons, chips, tracks, table stripes) use
// --surface-muted-bg; --surface-card-border is for borders/dividers only.
const SRC = path.resolve(__dirname, '../../../src');

const LIGHT_ONLY = [
  /(?<![\w-])(?:[a-z-]+:)*bg-(?:slate|gray)-(?:50|100|200)(?![\w/-])/g,
  /(?<![\w-])(?:[a-z-]+:)*bg-white(?![\w/-])/g,
  /(?<![\w-])text-(?:slate|gray)-(?:500|600|700|800|900)(?![\w/-])/g,
  /(?<![\w-])(?:border|divide)-(?:slate|gray)-(?:100|200|300)(?![\w/-])/g,
  /(?<![\w-])dark:[\w:-]*(?:slate|gray)-\d+/g,
  // Focus borders/rings and dividers of any slate/gray shade. (`ring-offset-*`
  // is not matched: PensionForecast's hero uses `focus:ring-offset-slate-900`
  // to match its own fixed `bg-slate-900` panel.)
  /(?<![\w-])focus(?:-visible|-within)?:(?:border|ring)-(?:slate|gray)-\d+/g,
  /(?<![\w-])divide-(?:slate|gray)-\d+/g,
];

// MetricsExplanation renders fixed dark panels (`bg-slate-900/60`) whose
// table dividers are intentionally dark-only.
const ALLOWED: Record<string, string[]> = {
  [path.join('pages', 'MetricsExplanation.tsx')]: [
    'divide-slate-700',
    'divide-slate-800',
  ],
};

function sourceFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    return /\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)
      ? [full]
      : [];
  });
}

describe('light-only palette classes', () => {
  it('uses theme surface tokens instead of light-only slate/gray classes', () => {
    const offenders = sourceFiles(SRC).flatMap((file) => {
      const text = fs.readFileSync(file, 'utf-8');
      const rel = path.relative(SRC, file);
      const allowed = ALLOWED[rel] ?? [];
      return LIGHT_ONLY.flatMap((pattern) =>
        [...text.matchAll(pattern)]
          .filter((m) => !allowed.includes(m[0]))
          .map((m) => `${rel}: ${m[0]}`)
      );
    });
    expect(offenders).toEqual([]);
  });
});
