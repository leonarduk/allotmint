import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { axe, toHaveNoViolations } from 'jest-axe';
import Alerts from '@/pages/Alerts';
import * as api from '@/api';

vi.mock('@/api');
const mockGetAlerts = vi.mocked(api.getAlerts);
expect.extend(toHaveNoViolations);

describe('Alerts page', () => {
  it('renders alerts and has no accessibility violations', async () => {
    mockGetAlerts.mockResolvedValue([
      { ticker: '', message: 'portfolio drawdown breach', change_pct: 0, timestamp: '2026-01-01T00:00:00Z' },
      { ticker: 'AAA', message: 'price up', change_pct: 5, timestamp: '2026-01-02T00:00:00Z' },
    ]);

    const { container } = render(<Alerts />);
    await screen.findByRole('heading', { name: 'Alerts' });
    await screen.findByText('Alert');
    await screen.findByText(/portfolio drawdown breach/i);
    await screen.findByText(/price up/i);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('shows heading while loading', async () => {
    // Never resolves so we catch the loading state
    mockGetAlerts.mockReturnValue(new Promise(() => {}));
    render(<Alerts />);
    await screen.findByRole('heading', { name: 'Alerts' });
    await screen.findByRole('status');
  });

  it('shows heading on error', async () => {
    mockGetAlerts.mockRejectedValue(new Error('network error'));
    render(<Alerts />);
    await screen.findByRole('heading', { name: 'Alerts' });
    await screen.findByRole('alert');
  });

  it('uses virtualRow index to disambiguate duplicate messages', async () => {
    // Two alerts with the same label, message, and timestamp — keys must not collide
    mockGetAlerts.mockResolvedValue([
      { ticker: '', message: 'same message', change_pct: 0, timestamp: '2026-01-01T00:00:00Z' },
      { ticker: '', message: 'same message', change_pct: 0, timestamp: '2026-01-01T00:00:00Z' },
    ]);
    const { container } = render(<Alerts />);
    await screen.findByRole('heading', { name: 'Alerts' });
    // Both rows should render (no React key collision warning will suppress duplicate renders)
    const items = container.querySelectorAll('li[style]');
    expect(items.length).toBeGreaterThanOrEqual(2);
  });
});
