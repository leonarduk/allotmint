/** Base-currency reporting phase 2 (#9805): headers follow the reporting currency. */
import type { ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { configContext, type ConfigContextValue } from '@/ConfigContext';
import { clearReportingRateCache } from '@/hooks/useReportingCurrency';
import { currencySymbol } from '@/lib/money';
import type { Account, Holding, InstrumentSummary } from '@/types';

const mockGetGbpRate = vi.fn();

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api');
  return {
    ...actual,
    getGbpRate: (currency: string) => mockGetGbpRate(currency),
    getInstrumentDetail: vi.fn(() =>
      Promise.resolve({ mini: { 7: [], 30: [], 180: [] } })
    ),
    getValueAtRisk: vi.fn(() =>
      Promise.resolve({
        owner: 'alice',
        as_of: '2024-01-01',
        var: { '1d': 100, '10d': 200 },
      })
    ),
    getDividends: vi.fn(() =>
      Promise.resolve([
        {
          owner: 'alex',
          account: 'isa',
          ticker: 'AAA',
          date: '2024-01-01',
          amount_minor: 1000,
          currency: 'USD',
        },
        {
          owner: 'alex',
          account: 'isa',
          ticker: 'AAA',
          date: '2024-02-01',
          amount_minor: 500,
          currency: 'GBP',
        },
        {
          owner: 'alex',
          account: 'isa',
          ticker: 'AAA',
          date: '2024-03-01',
          amount_minor: 250,
          currency: 'USD',
        },
      ])
    ),
    listInstrumentGroups: vi.fn(async () => []),
    listInstrumentGroupingDefinitions: vi.fn(async () => []),
  };
});
vi.mock('@/components/InstrumentDetail', () => ({
  InstrumentDetail: () => null,
}));

import { AccountBlock } from '@/components/AccountBlock';
import { HoldingsTable } from '@/components/HoldingsTable';
import { InstrumentTable } from '@/components/InstrumentTable';
import ValueAtRisk from '@/components/ValueAtRisk';
import { DividendHistory } from '@/components/DividendHistory';

function withCurrency(reportingCurrency: string) {
  const value = {
    configLoaded: true,
    relativeViewEnabled: false,
    familyMvpEnabled: false,
    disabledTabs: [],
    tabs: {},
    theme: 'system',
    reportingCurrency,
    refreshConfig: async () => {},
    setRelativeViewEnabled: () => {},
  } as unknown as ConfigContextValue;
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter>
        <configContext.Provider value={value}>
          {children}
        </configContext.Provider>
      </MemoryRouter>
    );
  };
}

const usd = (v: number) =>
  new Intl.NumberFormat('en', { style: 'currency', currency: 'USD' }).format(v);
const gbp = (v: number) =>
  new Intl.NumberFormat('en', { style: 'currency', currency: 'GBP' }).format(v);

const holding: Holding = {
  ticker: 'AAA.L',
  name: 'Alpha',
  units: 10,
  current_price_gbp: 100,
  market_value_gbp: 1000,
  cost_basis_gbp: 800,
  effective_cost_basis_gbp: 800,
  gain_gbp: 200,
  gain_pct: 25,
  cost_basis_source: 'book',
  acquired_date: null,
  days_held: null,
  sell_eligible: null,
  days_until_eligible: null,
  next_eligible_sell_date: null,
} as Holding;

const row: InstrumentSummary = {
  ticker: 'AAA',
  name: 'Alpha',
  grouping: 'Growth',
  exchange: 'L',
  currency: 'GBP',
  instrument_type: 'Equity',
  units: 10,
  market_value_gbp: 1000,
  cost_basis_gbp: 800,
  effective_cost_basis_gbp: 800,
  gain_gbp: 200,
  gain_pct: 25,
  last_price_gbp: 100,
  last_price_date: '2024-01-01',
  change_7d_pct: null,
  change_30d_pct: null,
  cost_basis_source: 'book',
} as InstrumentSummary;

beforeEach(() => {
  clearReportingRateCache();
  mockGetGbpRate.mockReset();
  mockGetGbpRate.mockResolvedValue({
    currency: 'USD',
    gbp_per_unit: 0.8,
    source: 'cache',
  });
});
afterEach(() => vi.restoreAllMocks());

describe('currencySymbol', () => {
  it('names the symbol a currency is written with', () => {
    expect(currencySymbol('GBP', 'en')).toBe('£');
    expect(currencySymbol('GBX', 'en')).toBe('£');
    expect(currencySymbol('USD', 'en')).toBe('$');
  });

  it('falls back to the code it cannot format', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(currencySymbol('US', 'en')).toBe('US');
  });
});

describe('HoldingsTable in the reporting currency', () => {
  it('keeps £ headers when reporting in GBP', async () => {
    render(<HoldingsTable holdings={[holding]} />, {
      wrapper: withCurrency('GBP'),
    });

    expect(
      await screen.findByRole('columnheader', { name: /Mkt £/ })
    ).toBeInTheDocument();
    expect(screen.getAllByText(gbp(1000)).length).toBeGreaterThan(0);
    expect(mockGetGbpRate).not.toHaveBeenCalled();
  });

  it('shows converted values under headers in the same currency', async () => {
    render(<HoldingsTable holdings={[holding]} />, {
      wrapper: withCurrency('USD'),
    });

    expect(
      await screen.findByRole('columnheader', { name: /Mkt \$/ })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('columnheader', { name: /Cost \$/ })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('columnheader', { name: /£/ })
    ).not.toBeInTheDocument();
    expect(screen.getAllByText(usd(1250)).length).toBeGreaterThan(0);
  });
});

describe('InstrumentTable in the reporting currency', () => {
  it('shows converted values under headers in the same currency', async () => {
    render(<InstrumentTable rows={[row]} />, { wrapper: withCurrency('USD') });

    expect(
      await screen.findByRole('columnheader', { name: /Market \$/ })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('columnheader', { name: /£/ })
    ).not.toBeInTheDocument();
    expect(screen.getAllByText(usd(1250)).length).toBeGreaterThan(0);
  });
});

describe('AccountBlock estimated value (#9795)', () => {
  // Same options as AccountBlock's compact formatter, so the locale matches.
  const compact = (v: number, currency: string) =>
    new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      notation: 'compact',
      maximumFractionDigits: 2,
    }).format(v);
  const account = (overrides: Partial<Account> = {}): Account => ({
    account_type: 'ISA',
    currency: 'GBP',
    value_estimate_gbp: 1000,
    value_estimate_currency: 'GBP',
    holdings: [],
    ...overrides,
  });

  it('shows GBP unchanged when reporting in GBP', async () => {
    render(<AccountBlock account={account()} />, {
      wrapper: withCurrency('GBP'),
    });

    expect(
      await screen.findByText(compact(1000, 'GBP'), { exact: false })
    ).toBeInTheDocument();
    expect(mockGetGbpRate).not.toHaveBeenCalled();
  });

  it('converts the GBP value into the reporting currency', async () => {
    render(<AccountBlock account={account()} />, {
      wrapper: withCurrency('USD'),
    });

    expect(
      await screen.findByText(compact(1250, 'USD'), { exact: false })
    ).toBeInTheDocument();
  });

  it('ignores a non-GBP value_estimate_currency tag: the value is GBP', async () => {
    render(
      <AccountBlock
        account={account({ currency: 'USD', value_estimate_currency: 'USD' })}
      />,
      { wrapper: withCurrency('GBP') }
    );

    expect(
      await screen.findByText(compact(1000, 'GBP'), { exact: false })
    ).toBeInTheDocument();
    expect(
      screen.queryByText(compact(1000, 'USD'), { exact: false })
    ).not.toBeInTheDocument();
  });
});

describe('ValueAtRisk in the reporting currency', () => {
  it('converts the VaR amounts', async () => {
    render(<ValueAtRisk owner="alice" />, { wrapper: withCurrency('USD') });

    await waitFor(() =>
      expect(screen.getByText(/95%:/)).toHaveTextContent(usd(125))
    );
    expect(screen.getByText(/99%:/)).toHaveTextContent(usd(250));
  });
});

describe('DividendHistory totals', () => {
  it('never adds dividends paid in different currencies', async () => {
    render(<DividendHistory />, { wrapper: withCurrency('GBP') });

    // USD 10.00 + 2.50 and GBP 5.00 for the same ticker: two totals, not £17.50.
    expect(await screen.findByText(usd(12.5))).toBeInTheDocument();
    expect(screen.getAllByText(gbp(5)).length).toBe(2); // the row and its total
    expect(screen.queryByText(gbp(17.5))).not.toBeInTheDocument();
  });
});
