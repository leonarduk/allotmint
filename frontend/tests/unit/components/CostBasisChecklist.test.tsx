import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import {
  CHECKLIST_TOP_COUNT,
  CostBasisChecklist,
} from '@/components/CostBasisChecklist';
import type { Account, Holding } from '@/types';

function holdings(count: number): Holding[] {
  return Array.from({ length: count }, (_, i) => ({
    ticker: `T${i}.L`,
    name: `Holding ${i}`,
    units: 1,
    market_value_gbp: (i + 1) * 100,
    cost_basis_source: 'unknown',
  }));
}

function renderChecklist(hs: Holding[]) {
  const accounts: Account[] = [
    {
      owner: 'alex',
      account_type: 'isa',
      currency: 'GBP',
      value_estimate_gbp: 0,
      holdings: hs,
    },
  ];
  return render(
    <MemoryRouter>
      <CostBasisChecklist accounts={accounts} />
    </MemoryRouter>
  );
}

describe('CostBasisChecklist', () => {
  it('renders nothing when no holding is missing a cost basis', () => {
    renderChecklist([
      {
        ticker: 'OK.L',
        name: 'Fine',
        units: 1,
        market_value_gbp: 10,
        cost_basis_source: 'book',
      },
    ]);
    expect(
      screen.queryByTestId('cost-basis-checklist')
    ).not.toBeInTheDocument();
  });

  it('lists the largest holdings first with a prefilled add-cost link', async () => {
    const user = userEvent.setup();
    renderChecklist(holdings(12));

    expect(
      screen.getByText(
        'Fill in cost basis: 12 holdings have no reliable cost basis'
      )
    ).toBeInTheDocument();
    const links = screen.getAllByRole('link', { name: 'Add cost' });
    expect(links).toHaveLength(CHECKLIST_TOP_COUNT);
    // Largest market value (T11.L) comes first.
    expect(links[0]).toHaveAttribute(
      'href',
      '/input?owner=alex&account=isa&ticker=T11.L&units=1'
    );

    await user.click(screen.getByRole('button', { name: 'Show all 12' }));
    expect(screen.getAllByRole('link', { name: 'Add cost' })).toHaveLength(12);
  });

  it('distinguishes a suspect recorded cost from a missing one', () => {
    renderChecklist([
      {
        ticker: 'SUS.L',
        name: 'Suspect',
        units: 1,
        market_value_gbp: 10,
        cost_basis_source: 'book_suspect',
      },
      {
        ticker: 'MIS.L',
        name: 'Missing',
        units: 1,
        market_value_gbp: 5,
        cost_basis_source: 'unknown',
      },
    ]);
    expect(screen.getByText('Recorded cost looks wrong')).toBeInTheDocument();
    expect(screen.getByText('No cost on record')).toBeInTheDocument();
  });
});
