import { describe, expect, it } from 'vitest';

import i18n from '@/i18n';
import { HELP_PAGES } from '@/lib/helpPages';
import { wholeNumber } from '@/lib/money';
import en from '../../../src/locales/en/translation.json';

type Tree = { [key: string]: string | Tree };

function lookup(tree: Tree, key: string): unknown {
  return key
    .split('.')
    .reduce<unknown>(
      (node, part) =>
        node && typeof node === 'object' ? (node as Tree)[part] : undefined,
      tree
    );
}

// #10835 / #7477: the help.pages.* keys were referenced but never defined, so
// every locale silently fell back to the English descriptionDefault.
describe('helpPages translation keys', () => {
  it.each(HELP_PAGES.map((entry) => [entry.path, entry] as const))(
    '%s has its title and description keys in en/translation.json',
    (_path, entry) => {
      expect(lookup(en as Tree, entry.descriptionKey)).toBe(
        entry.descriptionDefault
      );
      expect(lookup(en as Tree, entry.titleKey)).toBe(entry.titleDefault);
    }
  );

  it('renders German descriptions instead of the English default', () => {
    const de = i18n.getFixedT('de');
    const dashboard = HELP_PAGES[0];
    expect(de(dashboard.descriptionKey, dashboard.descriptionDefault)).not.toBe(
      dashboard.descriptionDefault
    );
  });
});

describe('#10835 German copy fixes', () => {
  const de = i18n.getFixedT('de');

  it('pluralises the trades-without-fee note', () => {
    expect(de('fundCharges.allInUnknownTrades', { count: 1, trades: 1 })).toBe(
      '1 Trade ohne erfasste Gebühr'
    );
    expect(de('fundCharges.allInUnknownTrades', { count: 3, trades: 3 })).toBe(
      '3 Trades ohne erfasste Gebühr'
    );
  });

  it('declines the adjective for unknown fund charges', () => {
    expect(
      de('fundCharges.allInBreakdownUnknownFunds', { fees: '5 £' })
    ).toMatch(/^Unbekannte Fondskosten/);
  });

  it('keeps the noun capitalised in the allocation link', () => {
    expect(de('allocation.viewAllocationBy.sector')).toBe(
      'Allokation nach Branchen anzeigen'
    );
  });

  it('shares the owner-table period labels with the VaR selector', () => {
    expect(de('dashboard.rangeOptions.1y')).toBe('1J');
  });
});

describe('wholeNumber', () => {
  it('groups digits for the requested locale', () => {
    expect(wholeNumber(10000, 'de')).toBe('10.000');
    expect(wholeNumber(10000, 'en')).toBe('10,000');
  });
});
