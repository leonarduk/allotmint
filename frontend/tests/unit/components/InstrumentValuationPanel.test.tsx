import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { InstrumentValuationPanel } from '@/components/InstrumentValuationPanel';
import {
  navDateLabel,
  navUnreliability,
  valuationCaveats,
} from '@/lib/valuationCaveats';
import * as api from '@/api';
import type { InstrumentPosition, InstrumentValuation } from '@/types';

vi.mock('@/api', () => ({ getInstrumentValuation: vi.fn() }));
const mockGetValuation = vi.mocked(api.getInstrumentValuation);

const profile = (
  overrides: Partial<InstrumentValuation> = {}
): InstrumentValuation => ({
  ticker: 'UKW.L',
  name: 'Greencoat UK Wind',
  instrument_type: 'Investment Trust',
  is_closed_end_fund: true,
  price: 112.5,
  price_currency: 'GBp',
  valuation: {
    pe_ratio: null,
    forward_pe: 9.7,
    pb_ratio: 0.84,
    ev_ebitda: null,
  },
  nav: {
    nav_per_share: 1.341,
    currency: 'GBP',
    as_of: '2026-06-30',
    source: 'reported_book_value',
    premium_discount: -0.1611,
  },
  income: { dividend_yield: 0.0975, payout_ratio: 0.5, dividend_cover: 2 },
  balance_sheet: {
    currency: 'GBP',
    total_debt: null,
    total_cash: null,
    net_debt: null,
    net_gearing: null,
    debt_to_equity: null,
  },
  benchmark: {
    ticker: 'FTAL.L',
    name: 'FTSE All-Share (SPDR FTAL ETF)',
    source: 'exchange_default',
  },
  risk: {
    volatility_1y: 0.2073,
    beta_3y: 0.35,
    beta_weeks: 156,
    beta_provider: null,
    max_drawdown: -0.4475,
    max_drawdown_peak: '2022-09-21',
    max_drawdown_trough: '2026-02-19',
    history_start: '2021-10-04',
    history_end: '2026-10-02',
    history_years: 5,
  },
  data_quality: {
    price_last_date: '2026-10-02',
    price_stale: false,
    suspect_moves: [],
    warnings: [],
    price_snapshot: { is_stale: false, last_price_date: '2026-10-02' },
  },
  ...overrides,
});

const position = (source: string | null): InstrumentPosition =>
  ({
    owner: 'alex',
    account: 'isa',
    cost_basis_source: source,
  }) as unknown as InstrumentPosition;

const rowValue = (label: string) =>
  within(screen.getByText(label).closest('tr') as HTMLElement).getAllByRole(
    'cell'
  )[0].textContent;

describe('InstrumentValuationPanel', () => {
  beforeEach(() => {
    mockGetValuation.mockReset();
  });

  it('shows NAV, premium/discount, income, risk and the benchmark', async () => {
    mockGetValuation.mockResolvedValue(profile());

    render(<InstrumentValuationPanel ticker="UKW.L" positions={[]} />);

    expect(await screen.findByText('Premium/discount')).toBeInTheDocument();
    expect(mockGetValuation).toHaveBeenCalledWith(
      'UKW.L',
      expect.any(AbortSignal)
    );
    expect(rowValue('Premium/discount')).toBe('-16.1%');
    expect(rowValue('NAV per share')).toBe('1.34 GBP');
    expect(rowValue('P/E (trailing)')).toBe('—');
    expect(rowValue('P/E (forward)')).toBe('9.70');
    expect(rowValue('Dividend yield')).toBe('9.75%');
    expect(rowValue('Max drawdown')).toBe('-44.8%');
    expect(
      screen.getByText(/FTSE All-Share \(SPDR FTAL ETF\)/)
    ).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('keeps the equity benchmark header and beta label', async () => {
    mockGetValuation.mockResolvedValue(profile());

    render(<InstrumentValuationPanel ticker="UKW.L" positions={[]} />);

    expect(
      await screen.findByText('Beta vs FTAL.L (3y weekly)')
    ).toBeInTheDocument();
    expect(
      screen.getByText(/^Benchmark:/).closest('p')?.textContent
    ).toBe(
      'Benchmark: FTSE All-Share (SPDR FTAL ETF) (FTAL.L, default for the listing exchange)'
    );
  });

  it('says there is no comparable benchmark for a cash fund', async () => {
    const note =
      'No comparable benchmark: it is a cash instrument. Set ' +
      "'benchmark' in its metadata to compare it with a suitable index.";
    mockGetValuation.mockResolvedValue(
      profile({
        ticker: 'ERNS.L',
        benchmark: {
          ticker: null,
          name: null,
          source: 'none',
          asset_class: 'cash',
          asset_class_basis: "name mentions 'ultrashort'",
          note,
        },
        risk: { ...profile().risk, beta_3y: null },
      })
    );

    render(<InstrumentValuationPanel ticker="ERNS.L" positions={[]} />);

    expect(await screen.findByText('Beta (3y weekly)')).toBeInTheDocument();
    expect(rowValue('Beta (3y weekly)')).toBe('—');
    const header = screen.getByText(/^Benchmark:/).closest('p');
    expect(header?.textContent).toBe(
      "Benchmark: none comparable (cash fund: name mentions 'ultrashort')"
    );
    expect(header).toHaveAttribute('title', note);
    const text = document.body.textContent ?? '';
    expect(text).not.toMatch(/null|undefined|\(\)/);
  });

  it('omits the asset class when the backend gives none', async () => {
    mockGetValuation.mockResolvedValue(
      profile({
        benchmark: { ticker: null, name: null, source: 'none' },
      })
    );

    render(<InstrumentValuationPanel ticker="UKW.L" positions={[]} />);

    expect(
      (await screen.findByText(/^Benchmark:/)).closest('p')?.textContent
    ).toBe('Benchmark: none comparable');
  });

  it('omits the NAV card for an instrument without a NAV', async () => {
    mockGetValuation.mockResolvedValue(
      profile({
        is_closed_end_fund: false,
        nav: {
          nav_per_share: null,
          currency: null,
          as_of: null,
          source: null,
          premium_discount: null,
        },
      })
    );

    render(<InstrumentValuationPanel ticker="GRG.L" positions={[]} />);

    expect(await screen.findByText('P/E (forward)')).toBeInTheDocument();
    expect(screen.queryByText('NAV per share')).not.toBeInTheDocument();
  });

  it('puts stale, suspect and provider caveats in a data-quality box', async () => {
    mockGetValuation.mockResolvedValue(
      profile({
        data_quality: {
          price_last_date: '2026-09-01',
          price_stale: true,
          suspect_moves: [{ date: '2026-05-01', change: -0.9 }],
          warnings: [
            'Latest close is from 2026-09-01; the price series is stale.',
          ],
          price_snapshot: { is_stale: true, last_price_date: '2026-09-01' },
        },
      })
    );

    render(
      <InstrumentValuationPanel
        ticker="UKW.L"
        positions={[position('book_suspect'), position('book')]}
      />
    );

    const box = await screen.findByRole('alert', { name: 'Data quality' });
    expect(
      within(box).getByText('Latest price is flagged stale (as of 2026-09-01).')
    ).toBeInTheDocument();
    expect(
      within(box).getByText(
        'Cost basis is suspect or unknown for 1 position(s): alex/isa.'
      )
    ).toBeInTheDocument();
    expect(
      within(box).getByText('Suspect one-day move of -90.0% on 2026-05-01.')
    ).toBeInTheDocument();
    expect(within(box).getByText(/price series is stale/)).toBeInTheDocument();
  });

  it('renders nothing when the feature is gated (402)', async () => {
    mockGetValuation.mockImplementation(() =>
      Promise.reject(Object.assign(new Error('gated'), { status: 402 }))
    );

    const { container } = render(
      <InstrumentValuationPanel ticker="UKW.L" positions={[]} />
    );

    await vi.waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('marks a premium on a stale NAV with its age', async () => {
    mockGetValuation.mockResolvedValue(
      profile({
        nav: {
          nav_per_share: 100,
          currency: 'GBp',
          as_of: '2026-02-28',
          source: 'metadata',
          premium_discount: 0.044,
          age_days: 218,
          max_age_days: 31,
          status: 'stale',
        },
      })
    );

    render(<InstrumentValuationPanel ticker="HFEL.L" positions={[]} />);

    expect(await screen.findByText('Stale NAV')).toBeInTheDocument();
    expect(rowValue('Premium/discount')).toBe('+4.4%Stale NAV');
    expect(rowValue('NAV last updated')).toBe('2026-02-28 (218 days old)');
    expect(
      screen.getByText('Unreliable: the NAV is 218 days old (limit 31 days).')
    ).toBeInTheDocument();
    expect(screen.getByText('Stale after 31 days')).toBeInTheDocument();
  });

  it('marks a premium on an undated book-value NAV', async () => {
    mockGetValuation.mockResolvedValue(
      profile({
        nav: {
          nav_per_share: 1.2,
          currency: 'GBP',
          as_of: null,
          source: 'reported_book_value',
          premium_discount: -0.389,
          age_days: null,
          max_age_days: 31,
          status: 'undated',
        },
      })
    );

    render(<InstrumentValuationPanel ticker="SERE.L" positions={[]} />);

    expect(await screen.findByText('Undated NAV')).toBeInTheDocument();
    expect(rowValue('Premium/discount')).toBe('-38.9%Undated NAV');
    expect(rowValue('NAV last updated')).toBe('unknown');
  });

  it('shows a current NAV without a warning badge', async () => {
    mockGetValuation.mockResolvedValue(
      profile({
        nav: {
          nav_per_share: 1.341,
          currency: 'GBP',
          as_of: '2026-10-01',
          source: 'metadata',
          premium_discount: -0.1611,
          age_days: 1,
          max_age_days: 31,
          status: 'current',
        },
      })
    );

    render(<InstrumentValuationPanel ticker="UKW.L" positions={[]} />);

    expect(await screen.findByText('Premium/discount')).toBeInTheDocument();
    expect(rowValue('Premium/discount')).toBe('-16.1%');
    expect(rowValue('NAV last updated')).toBe('2026-10-01 (1 day old)');
    expect(screen.queryByText(/Unreliable/)).not.toBeInTheDocument();
  });

  it('reports other errors', async () => {
    mockGetValuation.mockImplementation(() =>
      Promise.reject(Object.assign(new Error('boom'), { status: 500 }))
    );

    render(<InstrumentValuationPanel ticker="UKW.L" positions={[]} />);

    expect(
      await screen.findByText('Unable to load valuation: boom')
    ).toBeInTheDocument();
  });
});

describe('valuationCaveats', () => {
  it('still flags suspect cost basis without a profile', () => {
    expect(valuationCaveats(null, [position('unknown')])).toEqual([
      'Cost basis is suspect or unknown for 1 position(s): alex/isa.',
    ]);
  });
});

describe('NAV freshness helpers', () => {
  const nav = (
    overrides: Partial<InstrumentValuation['nav']>
  ): InstrumentValuation['nav'] => ({
    nav_per_share: 1,
    currency: 'GBP',
    as_of: '2026-10-04',
    source: 'metadata',
    premium_discount: 0,
    ...overrides,
  });

  it('labels the NAV date with its age', () => {
    expect(navDateLabel(nav({ as_of: null }))).toBe('unknown');
    expect(navDateLabel(nav({}))).toBe('2026-10-04');
    expect(navDateLabel(nav({ age_days: 0 }))).toBe('2026-10-04 (today)');
    expect(navDateLabel(nav({ age_days: 40 }))).toBe(
      '2026-10-04 (40 days old)'
    );
  });

  it('treats an undated NAV as unreliable even from an older server', () => {
    expect(navUnreliability(nav({ as_of: null }))?.badge).toBe('Undated NAV');
    expect(navUnreliability(nav({}))).toBeNull();
    expect(navUnreliability(nav({ status: 'current' }))).toBeNull();
    expect(
      navUnreliability(nav({ status: 'stale', age_days: 90 }))?.reason
    ).toBe('Unreliable: the NAV is 90 days old.');
  });
});
