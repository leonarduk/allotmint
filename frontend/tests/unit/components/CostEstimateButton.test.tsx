import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CostEstimateButton } from '@/components/CostEstimateButton';
import { estimateCostBasis } from '@/api';
import type { CostBasisGap } from '@/lib/costBasisChecklist';

vi.mock('@/api', () => ({
  estimateCostBasis: vi.fn(),
}));

const gap: CostBasisGap = {
  owner: 'alex',
  account: 'isa',
  ticker: 'AAA.L',
  name: 'Synthetic A',
  units: 10,
  marketValue: 25,
  source: 'unknown',
};

describe('CostEstimateButton (#10095)', () => {
  beforeEach(() => {
    vi.mocked(estimateCostBasis).mockReset();
  });

  it('explains the estimate before recording it, then reloads', async () => {
    vi.mocked(estimateCostBasis).mockResolvedValue({
      owner: 'alex',
      account: 'isa',
      ticker: 'AAA.L',
      units: 10,
      price_gbp: 2.5,
      cost_basis_gbp: 25,
      cost_basis_source: 'estimate',
      estimate_date: '2026-11-02',
    });
    const onEstimated = vi.fn();
    const user = userEvent.setup();
    render(<CostEstimateButton gap={gap} onEstimated={onEstimated} />);

    await user.click(
      screen.getByRole('button', { name: 'Use current price as cost' })
    );
    expect(estimateCostBasis).not.toHaveBeenCalled();
    expect(
      screen.getByText(
        /It is not what you paid: gain\/loss will count from today/
      )
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Record estimate' }));

    expect(estimateCostBasis).toHaveBeenCalledWith('alex', 'isa', 'AAA.L');
    expect(onEstimated).toHaveBeenCalledTimes(1);
  });

  it('records nothing when cancelled', async () => {
    const user = userEvent.setup();
    render(<CostEstimateButton gap={gap} />);

    await user.click(
      screen.getByRole('button', { name: 'Use current price as cost' })
    );
    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(estimateCostBasis).not.toHaveBeenCalled();
    expect(
      screen.getByRole('button', { name: 'Use current price as cost' })
    ).toBeInTheDocument();
  });

  it('shows the refusal reason and does not reload', async () => {
    vi.mocked(estimateCostBasis).mockRejectedValue(
      new Error('AAA.L already has transactions')
    );
    const onEstimated = vi.fn();
    const user = userEvent.setup();
    render(<CostEstimateButton gap={gap} onEstimated={onEstimated} />);

    await user.click(
      screen.getByRole('button', { name: 'Use current price as cost' })
    );
    await user.click(screen.getByRole('button', { name: 'Record estimate' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not record the estimate: AAA.L already has transactions'
    );
    expect(onEstimated).not.toHaveBeenCalled();
  });
});
