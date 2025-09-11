import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { axe, toHaveNoViolations } from 'jest-axe';
import Alerts from './Alerts';
import * as api from '../api';

vi.mock('../api');
const mockGetAlerts = vi.mocked(api.getAlerts);
expect.extend(toHaveNoViolations);

describe('Alerts page', () => {
  it('renders alerts and has no accessibility violations', async () => {
    mockGetAlerts.mockResolvedValue([{ ticker: 'AAA', message: 'price up' }]);

    const { container } = render(<Alerts />);
    await screen.findByText(/price up/i);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
