import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ReturnBasisNote from '@/components/ReturnBasisNote';
import type { PortfolioReturnBasisFields } from '@/types';

const renderNote = (fields: PortfolioReturnBasisFields | null) =>
  render(<ReturnBasisNote fields={fields} />);

describe('ReturnBasisNote', () => {
  it('renders nothing without a return basis', () => {
    const { container } = renderNote(null);
    expect(container).toBeEmptyDOMElement();
  });

  it('labels known holding bases', () => {
    renderNote({
      portfolio_return_basis: 'mixed',
      portfolio_price_basis_share: 0.25,
      portfolio_unpriced_holdings: [
        { ticker: 'ABC.L', return_basis: 'price' },
        { ticker: 'XYZ.N', return_basis: 'total' },
      ],
    });

    expect(screen.getByTestId('alpha-unpriced-holdings')).toHaveTextContent(
      'ABC.L (price only), XYZ.N (total return)'
    );
  });

  // #11089: a basis this build has no short label for is shown as sent.
  it('shows an unknown holding basis as sent rather than undefined', () => {
    renderNote({
      portfolio_return_basis: 'mixed',
      portfolio_price_basis_share: 0.5,
      portfolio_unpriced_holdings: [
        { ticker: 'ABC.L', return_basis: 'price' },
        // Cast: the backend may send a basis newer than this build's types.
        { ticker: 'NEW.L', return_basis: 'some_new_basis' as 'price' },
      ],
    });

    const unpriced = screen.getByTestId('alpha-unpriced-holdings');
    expect(unpriced).toHaveTextContent(
      'ABC.L (price only), NEW.L (some_new_basis)'
    );
    expect(unpriced).not.toHaveTextContent('undefined');
  });
});
