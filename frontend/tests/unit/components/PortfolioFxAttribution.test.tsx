import { render, screen, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import i18n from '@/i18n';
import { PortfolioFxAttribution } from '@/components/PortfolioFxAttribution';
import { getFxAttribution } from '@/api';
import type { FxAttribution, FxAttributionComponents } from '@/types';

vi.mock('@/api', () => ({ getFxAttribution: vi.fn() }));

const parts = (
  local: number,
  fx: number,
  income: number,
  residual: number,
  unattributed = 0
): FxAttributionComponents => ({
  local_gbp: local,
  fx_gbp: fx,
  income_gbp: income,
  residual_gbp: residual,
  unattributed_gbp: unattributed,
  pnl_gbp: local + fx + income + residual + unattributed,
});

const ATTRIBUTION: FxAttribution = {
  after: '2025-01-30',
  through: '2026-01-30',
  totals: parts(1000, -440, 25, -100),
  by_currency: [
    { currency: 'GBP', fx_applicable: false, ...parts(200, 0, 0, -50) },
    { currency: 'USD', fx_applicable: true, ...parts(800, -440, 25, -50) },
  ],
  instruments: [],
  unconverted_holdings: [],
  cash_fx_modelled: false,
  coverage: {
    ledger_value_gbp: 9000,
    portfolio_value_gbp: 10000,
    share: 0.9,
    unreconciled_holdings: [],
  },
};

describe('PortfolioFxAttribution', () => {
  beforeEach(() => {
    i18n.changeLanguage('en');
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows the portfolio line, the per-currency table, coverage and the notes', async () => {
    vi.mocked(getFxAttribution).mockResolvedValue({
      owner: 'alice',
      fx_attribution: ATTRIBUTION,
    });

    render(
      <PortfolioFxAttribution owner="alice" days={365} asOf="2026-01-30" />
    );

    expect(
      await screen.findByTestId('fx-attribution-local_gbp')
    ).toHaveTextContent('£1,000.00');
    expect(screen.getByTestId('fx-attribution-fx_gbp')).toHaveTextContent(
      '-£440.00'
    );
    expect(screen.getByTestId('fx-attribution-income_gbp')).toHaveTextContent(
      '£25.00'
    );
    expect(screen.getByTestId('fx-attribution-residual_gbp')).toHaveTextContent(
      '-£100.00'
    );
    expect(screen.getByTestId('fx-attribution-pnl_gbp')).toHaveTextContent(
      '£485.00'
    );
    // No unattributed amount: no column for it.
    expect(screen.queryByTestId('fx-attribution-unattributed_gbp')).toBeNull();
    const table = screen.getByTestId('fx-attribution-by-currency');
    const gbp = within(table).getByText('GBP').closest('tr') as HTMLElement;
    expect(within(gbp).getByText('n/a')).toBeInTheDocument();
    const usd = within(table).getByText('USD').closest('tr') as HTMLElement;
    expect(within(usd).getByText('-£440.00')).toBeInTheDocument();
    expect(screen.getByTestId('fx-attribution-coverage')).toHaveTextContent(
      'Covers 90% of portfolio value'
    );
    expect(
      screen.getByText(
        'By quote currency: GBP-listed foreign funds count as local.'
      )
    ).toBeInTheDocument();
    expect(screen.getByText(/Cash is not included/)).toBeInTheDocument();
    expect(getFxAttribution).toHaveBeenCalledWith('alice', 365, {
      asOf: '2026-01-30',
    });
  });

  it('shows unattributed amounts and FX gaps when present', async () => {
    vi.mocked(getFxAttribution).mockResolvedValue({
      owner: 'alice',
      fx_attribution: {
        ...ATTRIBUTION,
        totals: parts(1000, -440, 25, -100, 30),
        unconverted_holdings: [
          {
            ticker: 'USCO.N',
            currency: 'USD',
            reason: 'no stored FX rate on some dates',
          },
        ],
        coverage: {
          ...ATTRIBUTION.coverage,
          unreconciled_holdings: ['MANUAL.L'],
        },
      },
    });

    render(<PortfolioFxAttribution owner="alice" days={30} />);

    expect(
      await screen.findByTestId('fx-attribution-unattributed_gbp')
    ).toHaveTextContent('£30.00');
    expect(screen.getByTestId('fx-attribution-unconverted')).toHaveTextContent(
      'USCO.N (USD)'
    );
    expect(screen.getByText(/MANUAL\.L/)).toBeInTheDocument();
  });

  it('says when there is no ledger to attribute', async () => {
    vi.mocked(getFxAttribution).mockResolvedValue({
      owner: 'alice',
      fx_attribution: null,
    });

    render(<PortfolioFxAttribution owner="alice" days={365} />);

    expect(
      await screen.findByText('No transaction ledger to attribute.')
    ).toBeInTheDocument();
  });

  it('says when the request fails', async () => {
    vi.mocked(getFxAttribution).mockRejectedValue(new Error('boom'));

    render(<PortfolioFxAttribution owner="alice" days={365} />);

    expect(
      await screen.findByText('The P&L attribution is unavailable right now.')
    ).toBeInTheDocument();
  });

  it('is translated', async () => {
    await i18n.changeLanguage('fr');
    vi.mocked(getFxAttribution).mockResolvedValue({
      owner: 'alice',
      fx_attribution: ATTRIBUTION,
    });

    render(<PortfolioFxAttribution owner="alice" days={365} />);

    expect(await screen.findAllByText('Variations de change')).toHaveLength(2); // tile and column
    expect(screen.getByText('s.o.')).toBeInTheDocument();
  });
});
