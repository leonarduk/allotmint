import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { InstrumentCreditRiskPanel } from '@/components/InstrumentCreditRiskPanel';
import * as api from '@/api';
import type { CreditRiskSignal, InstrumentCreditRisk } from '@/types';

vi.mock('@/api', () => ({ getInstrumentCreditRisk: vi.fn() }));
const mockGetCreditRisk = vi.mocked(api.getInstrumentCreditRisk);

const signal = (value: number | null): CreditRiskSignal => ({
  value,
  threshold: null,
  as_of: '2025-12-31',
  source: 'yahoo',
});

const verdict = (
  overrides: Partial<InstrumentCreditRisk['result']> = {},
  context: InstrumentCreditRisk['market_context'] = {
    available: true,
    units: 'percent',
    series: {
      us_high_yield: { value: 3.15, date: '2026-10-08', percentile: 63.7 },
      baa_10y: { value: 1.48, date: '2026-10-08', percentile: 4.2 },
    },
  }
): InstrumentCreditRisk => ({
  result: {
    ticker: 'BP.L',
    name: 'BP',
    sector: 'Energy',
    band: 'high',
    reasons: ['Altman Z 1.35 is below the 1.8 distress line'],
    mitigations: [],
    signals: {
      altman_z: signal(1.3456),
      interest_coverage: signal(2.5105),
      net_debt_to_ebitda: signal(0.9048),
      current_ratio: signal(1.272),
      fcf: signal(12_879_000_000),
      net_debt: signal(35_468_000_000),
      from_52w_high: signal(-0.038),
      vs_sma_200: signal(0.05),
    },
    not_applicable: false,
    data_gaps: [],
    statements_as_of: '2025-12-31',
    financial_currency: 'USD',
    ...overrides,
  },
  market_context: context,
  thresholds: { altman_z_distress_below: 1.8 },
  note: 'Signals against fixed thresholds.',
});

const rowValue = (label: string) =>
  within(screen.getByText(label).closest('tr') as HTMLElement).getByRole('cell')
    .textContent;

describe('InstrumentCreditRiskPanel', () => {
  beforeEach(() => {
    mockGetCreditRisk.mockReset();
  });

  it('shows the band, reasons, signals, accounts date and market spreads', async () => {
    mockGetCreditRisk.mockResolvedValue(verdict());

    render(<InstrumentCreditRiskPanel ticker="BP.L" />);

    expect(await screen.findByTestId('credit-risk-band')).toHaveTextContent(
      'High'
    );
    expect(
      screen.getByText('Altman Z 1.35 is below the 1.8 distress line')
    ).toBeInTheDocument();
    expect(rowValue('Altman Z-score')).toBe('1.35');
    expect(rowValue('Interest cover')).toBe('2.51x');
    expect(rowValue('Net debt / EBITDA')).toBe('0.90x');
    expect(rowValue('Free cash flow')).toContain('USD');
    expect(screen.getByText(/Accounts to 2025-12-31/)).toBeInTheDocument();
    expect(
      screen.getByText(/US high yield 3.15pp \(64th percentile\)/)
    ).toBeInTheDocument();
    expect(mockGetCreditRisk).toHaveBeenCalledWith(
      'BP.L',
      expect.any(AbortSignal)
    );
  });

  it('lists mitigations alongside reasons and names missing inputs', async () => {
    mockGetCreditRisk.mockResolvedValue(
      verdict({
        band: 'watch',
        mitigations: ['the company holds more cash than debt (net cash)'],
        signals: {
          altman_z: signal(null),
          interest_coverage: signal(null),
          current_ratio: signal(4),
        },
        data_gaps: ['altman_z', 'interest_coverage'],
      })
    );

    render(<InstrumentCreditRiskPanel ticker="X.L" />);

    expect(await screen.findByTestId('credit-risk-band')).toHaveTextContent(
      'Watch'
    );
    expect(
      screen.getByText('the company holds more cash than debt (net cash)')
    ).toBeInTheDocument();
    expect(rowValue('Altman Z-score')).toBe('—');
    expect(screen.queryByText('Net debt / EBITDA')).not.toBeInTheDocument();
    expect(
      screen.getByText(/Missing: altman_z, interest_coverage/)
    ).toBeInTheDocument();
  });

  it('shows the sector caveat for a financial company', async () => {
    mockGetCreditRisk.mockResolvedValue(
      verdict({
        ticker: 'ADM.L',
        sector: 'Financials',
        band: 'low',
        not_applicable: true,
        reasons: [
          "Altman Z and interest cover not applied to sector 'Financials'",
        ],
        signals: { altman_z: signal(null), current_ratio: signal(6.1) },
      })
    );

    render(<InstrumentCreditRiskPanel ticker="ADM.L" />);

    expect(await screen.findByTestId('credit-risk-band')).toHaveTextContent(
      'Low'
    );
    expect(
      screen.getByText(
        "Altman Z and interest cover not applied to sector 'Financials'"
      )
    ).toBeInTheDocument();
  });

  it('copes with a row that leaves out its lists', async () => {
    const data = verdict();
    delete data.result.reasons;
    delete data.result.mitigations;
    delete data.result.data_gaps;
    delete data.result.signals;
    mockGetCreditRisk.mockResolvedValue(data);

    render(<InstrumentCreditRiskPanel ticker="BP.L" />);

    expect(await screen.findByTestId('credit-risk-band')).toHaveTextContent(
      'High'
    );
    expect(screen.queryByText('Altman Z-score')).not.toBeInTheDocument();
  });

  it('hides market spreads when none are stored', async () => {
    mockGetCreditRisk.mockResolvedValue(
      verdict(
        {},
        { available: false, reason: 'no credit spread series stored yet' }
      )
    );

    render(<InstrumentCreditRiskPanel ticker="BP.L" />);

    await screen.findByTestId('credit-risk-band');
    expect(screen.queryByText(/Market credit spreads/)).not.toBeInTheDocument();
  });

  it('renders nothing when the feature is not in this deployment (402)', async () => {
    mockGetCreditRisk.mockRejectedValue(
      Object.assign(new Error('Payment Required'), { status: 402 })
    );

    const { container } = render(<InstrumentCreditRiskPanel ticker="BP.L" />);

    await vi.waitFor(() =>
      expect(
        screen.queryByText('Loading credit risk...')
      ).not.toBeInTheDocument()
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows an error for other failures', async () => {
    mockGetCreditRisk.mockRejectedValue(
      Object.assign(new Error('boom'), { status: 502 })
    );

    render(<InstrumentCreditRiskPanel ticker="BP.L" />);

    expect(
      await screen.findByText('Could not load credit risk: boom')
    ).toBeInTheDocument();
  });
});
