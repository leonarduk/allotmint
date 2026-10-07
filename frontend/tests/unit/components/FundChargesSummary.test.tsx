import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { FundChargesSummary } from '@/components/FundChargesSummary';

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
