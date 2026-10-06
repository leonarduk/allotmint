import type { ReactNode } from 'react';
import { render, renderHook, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { configContext, type ConfigContextValue } from '@/ConfigContext';
import {
  PortfolioSummary,
  computePortfolioTotals,
} from '@/components/PortfolioSummary';
import {
  clearReportingRateCache,
  useReportingCurrency,
} from '@/hooks/useReportingCurrency';

const mockGetGbpRate = vi.fn();

vi.mock('@/api', () => ({
  getGbpRate: (currency: string) => mockGetGbpRate(currency),
}));

function wrapperFor(reportingCurrency: string) {
  const value = {
    configLoaded: true,
    relativeViewEnabled: false,
    familyMvpEnabled: false,
    tabs: {},
    theme: 'system',
    reportingCurrency,
    refreshConfig: async () => {},
    setRelativeViewEnabled: () => {},
  } as unknown as ConfigContextValue;
  return ({ children }: { children: ReactNode }) => (
    <configContext.Provider value={value}>{children}</configContext.Provider>
  );
}

const gbp = (v: number) =>
  new Intl.NumberFormat('en', { style: 'currency', currency: 'GBP' }).format(v);
const usd = (v: number) =>
  new Intl.NumberFormat('en', { style: 'currency', currency: 'USD' }).format(v);

describe('useReportingCurrency', () => {
  beforeEach(() => {
    clearReportingRateCache();
    mockGetGbpRate.mockReset();
  });
  afterEach(() => vi.restoreAllMocks());

  it('formats GBP as GBP and fetches no rate when the base currency is GBP', () => {
    const { result } = renderHook(() => useReportingCurrency(), {
      wrapper: wrapperFor('GBP'),
    });

    expect(result.current.status).toBe('gbp');
    expect(result.current.format(1000)).toBe(gbp(1000));
    expect(mockGetGbpRate).not.toHaveBeenCalled();
  });

  it('converts GBP amounts at the cached rate once it arrives', async () => {
    mockGetGbpRate.mockResolvedValue({
      currency: 'USD',
      gbp_per_unit: 0.8,
      source: 'cache',
    });
    const { result } = renderHook(() => useReportingCurrency(), {
      wrapper: wrapperFor('USD'),
    });

    // Never relabelled while the rate is on its way.
    expect(result.current.status).toBe('loading');
    expect(result.current.format(1000)).toBe(gbp(1000));

    await waitFor(() => expect(result.current.status).toBe('converted'));
    expect(result.current.currency).toBe('USD');
    expect(result.current.format(1000)).toBe(usd(1250));
    expect(result.current.convertGbp(1000)).toBe(1250);
    expect(mockGetGbpRate).toHaveBeenCalledWith('USD');
  });

  it('keeps GBP when no rate is stored', async () => {
    mockGetGbpRate.mockResolvedValue({
      currency: 'USD',
      gbp_per_unit: null,
      source: 'missing',
    });
    const { result } = renderHook(() => useReportingCurrency(), {
      wrapper: wrapperFor('USD'),
    });

    await waitFor(() => expect(result.current.status).toBe('unavailable'));
    expect(result.current.currency).toBe('GBP');
    expect(result.current.format(1000)).toBe(gbp(1000));
  });

  it('keeps GBP when the rate request fails', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    mockGetGbpRate.mockRejectedValue(new Error('HTTP 500'));
    const { result } = renderHook(() => useReportingCurrency(), {
      wrapper: wrapperFor('USD'),
    });

    await waitFor(() => expect(result.current.status).toBe('unavailable'));
    expect(result.current.format(1000)).toBe(gbp(1000));
    expect(warn).toHaveBeenCalled();
  });

  it('only converts GBP (and GBX-tagged) amounts', async () => {
    mockGetGbpRate.mockResolvedValue({
      currency: 'USD',
      gbp_per_unit: 0.8,
      source: 'cache',
    });
    const { result } = renderHook(() => useReportingCurrency(), {
      wrapper: wrapperFor('USD'),
    });
    await waitFor(() => expect(result.current.status).toBe('converted'));

    expect(result.current.format(100, 'EUR')).toBe(
      new Intl.NumberFormat('en', {
        style: 'currency',
        currency: 'EUR',
      }).format(100)
    );
    expect(result.current.format(100, 'GBX')).toBe(usd(125));
    expect(result.current.format(null)).toBe('—');
  });

  it('shares one rate request between views', async () => {
    mockGetGbpRate.mockResolvedValue({
      currency: 'EUR',
      gbp_per_unit: 0.85,
      source: 'cache',
    });
    const wrapper = wrapperFor('EUR');
    const first = renderHook(() => useReportingCurrency(), { wrapper });
    const second = renderHook(() => useReportingCurrency(), { wrapper });

    await waitFor(() => expect(first.result.current.status).toBe('converted'));
    await waitFor(() => expect(second.result.current.status).toBe('converted'));
    expect(mockGetGbpRate).toHaveBeenCalledTimes(1);
  });
});

describe('PortfolioSummary in a non-GBP base currency', () => {
  const totals = computePortfolioTotals([
    {
      account_type: 'ISA',
      currency: 'GBP',
      value_estimate_gbp: 1000,
      holdings: [
        {
          ticker: 'AAA.L',
          name: 'A',
          units: 10,
          market_value_gbp: 1000,
          cost_basis_gbp: 800,
          effective_cost_basis_gbp: 800,
          gain_gbp: 200,
          gain_pct: 25,
          cost_basis_source: 'book',
        },
      ],
    },
  ]);

  beforeEach(() => {
    clearReportingRateCache();
    mockGetGbpRate.mockReset();
  });

  it('shows converted totals and says how they were converted', async () => {
    mockGetGbpRate.mockResolvedValue({
      currency: 'USD',
      gbp_per_unit: 0.8,
      source: 'cache',
    });
    const Wrapper = wrapperFor('USD');
    render(
      <Wrapper>
        <PortfolioSummary totals={totals} />
      </Wrapper>
    );

    expect(
      await screen.findByText(/translated from GBP at today's rate/)
    ).toBeInTheDocument();
    expect(screen.getAllByText(usd(1250)).length).toBeGreaterThan(0);
    expect(screen.getByText(usd(250))).toBeInTheDocument();
    expect(screen.queryByText(gbp(1000))).not.toBeInTheDocument();
  });

  it('stays in GBP and says why when there is no rate', async () => {
    mockGetGbpRate.mockResolvedValue({
      currency: 'USD',
      gbp_per_unit: null,
      source: 'missing',
    });
    const Wrapper = wrapperFor('USD');
    render(
      <Wrapper>
        <PortfolioSummary totals={totals} />
      </Wrapper>
    );

    expect(
      await screen.findByText(/No GBP rate for USD is stored/)
    ).toBeInTheDocument();
    expect(screen.getAllByText(gbp(1000)).length).toBeGreaterThan(0);
    expect(screen.queryByText(usd(1000))).not.toBeInTheDocument();
  });
});
