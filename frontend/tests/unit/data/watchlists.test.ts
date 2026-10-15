import { describe, expect, it } from 'vitest';
import {
  FTSE100,
  FTSE250,
  FTSE350,
  FTSEAllShare,
  WATCHLISTS,
  WATCHLIST_META,
} from '@/data/watchlists';

// Tickers that no longer trade under these symbols on the LSE (#10912).
// Do not remove entries: this list guards against a stale list coming back.
const DEFUNCT_FTSE_SYMBOLS = [
  'RDSA.L', // Royal Dutch Shell A -> SHEL.L (2022)
  'RDSB.L', // Royal Dutch Shell B -> SHEL.L (2022)
  'RBS.L', // RBS -> NWG.L (2020)
  'RSA.L', // RSA Insurance, acquired 2021
  'MRW.L', // Morrisons, taken private 2021
  'NMC.L', // NMC Health, delisted 2020
  'JE.L', // Just Eat, left LSE 2020
  'SLA.L', // Standard Life Aberdeen -> ABDN.L
  'RB.L', // Reckitt -> RKT.L
  'MGGT.L', // Meggitt, acquired 2022
  'AVV.L', // AVEVA, acquired 2023
  'TUI.L', // TUI, left LSE 2023
  'EVR.L', // Evraz, delisted 2022
  'POLY.L', // Polymetal, left LSE 2023
  'PHNX.L', // Phoenix -> Standard Life SDLF.L
  'LXI.L', // LXI REIT, merged into LondonMetric 2024
  'DARK.L', // Darktrace, acquired 2024
  'HL.L', // Hargreaves Lansdown, taken private 2025
  'SMDS.L', // DS Smith, acquired 2025
  'BEZ.L', // Beazley, acquired Oct 2026
  'SDR.L', // Schroders, acquired Oct 2026
];

const FTSE_LISTS = {
  'FTSE 100': FTSE100,
  'FTSE 250': FTSE250,
  'FTSE 350': FTSE350,
  'FTSE All-Share': FTSEAllShare,
};

describe('built-in FTSE watchlists', () => {
  it.each(Object.entries(FTSE_LISTS))(
    '%s contains no known-defunct symbols',
    (_name, list) => {
      expect(list.filter((t) => DEFUNCT_FTSE_SYMBOLS.includes(t))).toEqual([]);
    }
  );

  it('FTSE 100 and FTSE 250 have the index sizes with no duplicates', () => {
    expect(FTSE100).toHaveLength(100);
    expect(new Set(FTSE100).size).toBe(100);
    expect(FTSE250).toHaveLength(250);
    expect(new Set(FTSE250).size).toBe(250);
  });

  it('no company sits in both the FTSE 100 and FTSE 250', () => {
    expect(FTSE100.filter((t) => FTSE250.includes(t))).toEqual([]);
    expect(FTSE350).toHaveLength(350);
  });

  it('every FTSE ticker is an LSE symbol', () => {
    for (const t of FTSE350) expect(t).toMatch(/^[A-Z0-9-]+\.L$/);
  });

  it('includes current constituents that replaced defunct tickers', () => {
    for (const t of ['SHEL.L', 'NWG.L', 'ABDN.L', 'RKT.L', 'AAF.L', 'SDLF.L']) {
      expect(FTSE100).toContain(t);
    }
  });
});

describe('WATCHLIST_META', () => {
  it('keeps the watchlist names saved screens reference', () => {
    expect(Object.keys(WATCHLISTS)).toEqual([
      'FTSE 100',
      'FTSE 250',
      'FTSE 350',
      'FTSE All-Share',
      'S&P 500',
      'Core ETFs',
    ]);
  });

  it('gives every watchlist an ISO as-of date and a source', () => {
    for (const name of Object.keys(WATCHLISTS) as (keyof typeof WATCHLISTS)[]) {
      const meta = WATCHLIST_META[name];
      expect(meta.asOf).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(Number.isNaN(Date.parse(meta.asOf))).toBe(false);
      expect(meta.source).not.toBe('');
    }
  });
});
