import { describe, expect, it } from 'vitest';
import en from '../../../src/locales/en/translation.json';
import {
  PLOT_GLOSSARY,
  plotGlossaryEntry,
  plotGlossaryPath,
} from '@/lib/plotGlossary';

type Tree = { [key: string]: string | Tree };
const plotSection = (en as unknown as Tree).metricsExplanation as Tree;
const plotStrings = (plotSection.sections as Tree).plot as Tree;

describe('Plot glossary (#7210)', () => {
  it('has unique anchors and keys', () => {
    const ids = PLOT_GLOSSARY.map((entry) => entry.id);
    const keys = PLOT_GLOSSARY.map((entry) => entry.key);
    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('keeps each English default in step with the en locale', () => {
    for (const entry of PLOT_GLOSSARY) {
      const strings = plotStrings[entry.key] as Tree;
      expect(strings?.title, entry.key).toBe(entry.title);
      expect(strings?.detail, entry.key).toBe(entry.detail);
    }
  });

  it('builds glossary links and refuses unknown keys', () => {
    expect(plotGlossaryPath('crate')).toBe('/metrics-explained#crate');
    expect(plotGlossaryEntry('crate').title).toBe('Crate');
    expect(() => plotGlossaryEntry('propagator')).toThrow(/Unknown/);
  });
});
