import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { FundChargesSummary } from '@/components/FundChargesSummary';
import { computeFundCharges } from '@/lib/fundCharges';
import type { Account } from '@/types';

describe('FundChargesSummary (#7834)', () => {
  it('shows the weighted charge, annual cost and the unknown-data note', () => {
    render(
      <FundChargesSummary
        charges={{
          weightedChargePct: 0.4,
          annualCostGbp: 16,
          holdingCount: 3,
          unknownCount: 1,
        }}
      />
    );
    expect(screen.getByTestId('fund-charges-weighted')).toHaveTextContent(
      '0.40%'
    );
    expect(screen.getByTestId('fund-charges-annual')).toHaveTextContent('16');
    expect(
      screen.getByText(/1 of 3 holdings with no fee data/)
    ).toBeInTheDocument();
  });

  it('renders a weighted % (not Unknown) from backend-shaped holdings', () => {
    // Same holdings as tests/test_fund_charges_e2e.py builds via the real
    // instrument catalogue: one fund at 0.22%, one with no fee data, cash.
    const accounts = [
      {
        account_type: 'isa',
        currency: 'GBP',
        value_estimate_gbp: 1600,
        holdings: [
          {
            ticker: 'VWRL.L',
            name: 'All-World Fund',
            units: 10,
            market_value_gbp: 1000,
            ongoing_charge_pct: 0.22,
          },
          {
            ticker: 'NOFEE.L',
            name: 'No Fee Data',
            units: 5,
            market_value_gbp: 500,
            ongoing_charge_pct: null,
          },
          {
            ticker: 'CASH.GBP',
            name: 'Cash',
            units: 100,
            market_value_gbp: 100,
            instrument_type: 'cash',
          },
        ],
      },
    ] as unknown as Account[];

    render(<FundChargesSummary charges={computeFundCharges(accounts)} />);

    const weighted = screen.getByTestId('fund-charges-weighted');
    expect(weighted).toHaveTextContent('0.22%');
    expect(weighted).not.toHaveTextContent('Unknown');
    expect(screen.getByTestId('fund-charges-annual')).toHaveTextContent('2.20');
    expect(
      screen.getByText(/1 of 2 holdings with no fee data/)
    ).toBeInTheDocument();
  });

  it('renders unknown, never 0%, when no charge is known', () => {
    render(
      <FundChargesSummary
        charges={{
          weightedChargePct: null,
          annualCostGbp: null,
          holdingCount: 2,
          unknownCount: 2,
        }}
      />
    );
    expect(screen.getByTestId('fund-charges-weighted')).toHaveTextContent(
      'Unknown'
    );
    expect(screen.getByTestId('fund-charges-annual')).toHaveTextContent(
      'Unknown'
    );
    expect(screen.queryByText('0.00%')).not.toBeInTheDocument();
  });

  it('renders nothing without any priced non-cash holdings', () => {
    const { container } = render(
      <FundChargesSummary
        charges={{
          weightedChargePct: null,
          annualCostGbp: null,
          holdingCount: 0,
          unknownCount: 0,
        }}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });
});
