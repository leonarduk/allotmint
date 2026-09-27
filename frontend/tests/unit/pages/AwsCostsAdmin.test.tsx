import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

const mockGetAwsCosts = vi.hoisted(() => vi.fn());

vi.mock('@/api', () => ({
  getAwsCosts: mockGetAwsCosts,
}));

import AwsCostsAdmin from '@/pages/AwsCostsAdmin';

const response = {
  start: '2026-09-01',
  end: '2026-09-27',
  total: { amount: 4.75, unit: 'USD' },
  services: [
    { service: 'AWS Lambda', amount: 3.25, unit: 'USD' },
    { service: 'Amazon Simple Storage Service', amount: 1.5, unit: 'USD' },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <AwsCostsAdmin />
    </MemoryRouter>
  );
}

describe('AwsCostsAdmin page', () => {
  it('renders the per-service breakdown and total', async () => {
    mockGetAwsCosts.mockResolvedValue(response);
    renderPage();

    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(screen.getByText('AWS Lambda')).toBeInTheDocument();
    expect(
      screen.getByText('Amazon Simple Storage Service')
    ).toBeInTheDocument();
    expect(screen.getByText('3.25 USD')).toBeInTheDocument();
    expect(screen.getByText('4.75 USD')).toBeInTheDocument();
  });

  it('shows a not-authorized message on a 403 response', async () => {
    const err = new Error('Not authorized for AWS cost data');
    (err as { status?: number }).status = 403;
    mockGetAwsCosts.mockRejectedValue(err);
    renderPage();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'You are not authorized to view AWS cost data.'
    );
  });

  it('shows a generic error message on a non-403 failure', async () => {
    mockGetAwsCosts.mockRejectedValue(new Error('boom'));
    renderPage();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Failed to load AWS cost data.');
    expect(alert).toHaveTextContent('boom');
  });

  it('shows an empty state when there is no cost data', async () => {
    mockGetAwsCosts.mockResolvedValue({ ...response, services: [] });
    renderPage();

    expect(
      await screen.findByText('No cost data found for this period.')
    ).toBeInTheDocument();
  });
});
