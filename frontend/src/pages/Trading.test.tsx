import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { axe } from 'jest-axe';
import Trading from './Trading';
import * as api from '../api';

vi.mock('../api');

const mockGetTradingSignals = vi.mocked(api.getTradingSignals);

vi.mock('../components/InstrumentDetail', () => ({
  InstrumentDetail: ({
    ticker,
    signal,
    onClose,
  }: {
    ticker: string;
    signal?: { action: string; reason: string };
    onClose: () => void;
  }) => (
    <div data-testid="detail">
      Detail for {ticker}
      {signal && (
        <div>
          {signal.action} - {signal.reason}
        </div>
      )}
      <button onClick={onClose}>x</button>
    </div>
  ),
}));

describe('Trading page', () => {
  it('passes signal to InstrumentDetail', async () => {
    mockGetTradingSignals.mockResolvedValue([
      {
        ticker: 'AAA',
        name: 'AAA',
        action: 'buy',
        reason: 'cheap',
        currency: 'USD',
        instrument_type: 'equity',
      },
    ]);

    render(<Trading />);

    const cell = await screen.findByText('AAA');
    fireEvent.click(cell);

    const detail = await screen.findByTestId('detail');
    expect(detail).toHaveTextContent(/buy/i);
    expect(detail).toHaveTextContent('cheap');
  });

  it('has no accessibility violations', async () => {
    mockGetTradingSignals.mockResolvedValue([
      {
        ticker: 'AAA',
        name: 'AAA',
        action: 'buy',
        reason: 'cheap',
        currency: 'USD',
        instrument_type: 'equity',
      },
    ]);

    const { container } = render(<Trading />);
    await screen.findByText('AAA');
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
