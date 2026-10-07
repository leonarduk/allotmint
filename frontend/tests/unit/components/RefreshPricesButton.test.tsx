import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as api from '@/api';
import { RefreshPricesButton } from '@/components/RefreshPricesButton';

afterEach(() => vi.restoreAllMocks());

describe('RefreshPricesButton', () => {
  it('refetches the series and reports the row count', async () => {
    const refetch = vi
      .spyOn(api, 'refetchTimeseries')
      .mockResolvedValue({ status: 'ok', rows: 22 });
    const onRefreshed = vi.fn();
    render(
      <RefreshPricesButton
        ticker="XDEB"
        exchange="L"
        onRefreshed={onRefreshed}
      />
    );

    await userEvent.click(
      screen.getByRole('button', { name: 'Refresh prices' })
    );

    expect(refetch).toHaveBeenCalledWith('XDEB', 'L');
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Fetched 22 price rows.'
    );
    expect(onRefreshed).toHaveBeenCalledWith(22);
  });

  it('shows the error and does not call onRefreshed when the refetch fails', async () => {
    vi.spyOn(api, 'refetchTimeseries').mockRejectedValue(new Error('HTTP 502'));
    const onRefreshed = vi.fn();
    render(
      <RefreshPricesButton
        ticker="XDEB"
        exchange="L"
        onRefreshed={onRefreshed}
      />
    );

    await userEvent.click(
      screen.getByRole('button', { name: 'Refresh prices' })
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Price refresh failed: HTTP 502'
    );
    expect(onRefreshed).not.toHaveBeenCalled();
  });
});
