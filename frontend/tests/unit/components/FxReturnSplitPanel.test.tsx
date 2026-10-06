import { act, render, screen, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import i18n from '@/i18n';
import type { FxReturnSplit } from '@/types';

vi.mock('@/api', () => ({ getInstrumentFxSplit: vi.fn() }));
import { getInstrumentFxSplit } from '@/api';
import { FxReturnSplitPanel } from '@/components/FxReturnSplitPanel';
import { signedPercent } from '@/lib/money';

const mockSplit = getInstrumentFxSplit as unknown as Mock;

const SPLIT: FxReturnSplit = {
  ticker: 'USCO.N',
  currency: 'USD',
  applicable: true,
  basis: 'price',
  reason: null,
  start: '2024-03-01',
  end: '2024-03-28',
  start_rate: 0.8,
  end_rate: 0.76,
  local_return: 0.1,
  fx_return: -0.05,
  cross_term: -0.005,
  gbp_return: 0.045,
};

const renderPanel = (days = 365) =>
  render(
    <FxReturnSplitPanel
      ticker="USCO.N"
      days={days}
      mutedColor="#555"
      positiveColor="green"
      negativeColor="red"
    />
  );

describe('FxReturnSplitPanel', () => {
  beforeEach(async () => {
    mockSplit.mockReset();
    await i18n.changeLanguage('en');
  });

  it("shows local, FX, cross term and GBP return for the page's range", async () => {
    mockSplit.mockResolvedValue(SPLIT);

    renderPanel(30);

    const panel = await screen.findByTestId('fx-split-panel');
    expect(mockSplit).toHaveBeenCalledWith(
      'USCO.N',
      30,
      expect.any(AbortSignal)
    );
    expect(
      within(panel).getByText('Local vs currency return')
    ).toBeInTheDocument();
    expect(
      within(panel).getByText(
        'Price return (excludes dividends), 2024-03-01 to 2024-03-28'
      )
    ).toBeInTheDocument();
    const value = (key: string) =>
      within(screen.getByTestId(`fx-split-${key}`)).getByRole('cell')
        .textContent;
    expect(value('local_return')).toBe('+10.00%');
    expect(value('fx_return')).toBe('-5.00%');
    expect(value('cross_term')).toBe('-0.50%');
    expect(value('gbp_return')).toBe('+4.50%');
    expect(
      within(screen.getByTestId('fx-split-fx_return')).getByRole('rowheader')
        .textContent
    ).toBe('Currency move (USD→GBP)');
  });

  it('renders nothing for a GBP or GBX instrument', async () => {
    mockSplit.mockResolvedValue({
      ...SPLIT,
      currency: 'GBP',
      applicable: false,
      reason: 'sterling_instrument',
    });

    const { container } = renderPanel();

    expect(mockSplit).toHaveBeenCalled();
    await act(async () => {
      await mockSplit.mock.results[0].value;
    });
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId('fx-split-panel')).toBeNull();
  });

  it('shows the reason, not numbers, when an FX rate is missing', async () => {
    mockSplit.mockResolvedValue({
      ...SPLIT,
      reason: 'missing_fx_rate',
      end_rate: null,
      local_return: null,
      fx_return: null,
      cross_term: null,
      gbp_return: null,
    });

    renderPanel();

    expect(await screen.findByTestId('fx-split-reason')).toHaveTextContent(
      'No split: no stored USD→GBP rate close enough to 2024-03-01 or 2024-03-28.'
    );
    expect(screen.queryByTestId('fx-split-gbp_return')).toBeNull();
  });

  it('says the split is unavailable when the request fails', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    mockSplit.mockRejectedValue(new Error('boom'));

    renderPanel();

    expect(await screen.findByTestId('fx-split-error')).toHaveTextContent(
      'The local vs currency split could not be loaded.'
    );
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it('uses the active locale', async () => {
    mockSplit.mockResolvedValue(SPLIT);
    await i18n.changeLanguage('fr');

    renderPanel();

    expect(
      await screen.findByText('Rendement local vs rendement de change')
    ).toBeInTheDocument();
  });
});

describe('signedPercent', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('prefixes gains with a plus and leaves losses and zero alone', () => {
    expect(signedPercent(0.1)).toBe('+10.00%');
    expect(signedPercent(-0.005)).toBe('-0.50%');
    expect(signedPercent(0)).toBe('0.00%');
  });
});
