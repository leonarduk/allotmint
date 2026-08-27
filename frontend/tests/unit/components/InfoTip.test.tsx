import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { axe } from 'jest-axe';
import InfoTip from '@/components/InfoTip';

describe('InfoTip', () => {
  it('renders a labelled trigger button and keeps the popover closed by default', () => {
    render(<InfoTip label="What does RSI mean?">RSI measures momentum.</InfoTip>);

    const button = screen.getByRole('button', { name: 'What does RSI mean?' });
    expect(button).toHaveAttribute('aria-expanded', 'false');

    const tooltip = screen.getByRole('tooltip', { hidden: true });
    expect(tooltip).toHaveTextContent('RSI measures momentum.');
  });

  it('opens the popover on click and closes it again on a second click', () => {
    render(<InfoTip label="What does RSI mean?">RSI measures momentum.</InfoTip>);

    const button = screen.getByRole('button', { name: 'What does RSI mean?' });
    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'true');

    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'false');
  });

  it('closes when Escape is pressed', () => {
    render(<InfoTip label="What does RSI mean?">RSI measures momentum.</InfoTip>);

    const button = screen.getByRole('button', { name: 'What does RSI mean?' });
    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'true');

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(button).toHaveAttribute('aria-expanded', 'false');
  });

  it('does not render a "Learn more" link when no `to` is given', () => {
    render(<InfoTip label="What does RSI mean?">RSI measures momentum.</InfoTip>);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('renders a "Learn more" link pointing at the glossary anchor when `to` is given', () => {
    render(
      <InfoTip label="What does RSI mean?" to="/metrics-explained#rsi">
        RSI measures momentum.
      </InfoTip>
    );

    const link = screen.getByRole('link', { name: 'Learn more' });
    expect(link).toHaveAttribute('href', '/metrics-explained#rsi');
  });

  it('stops a click on the trigger from reaching an ancestor click handler', () => {
    const onAncestorClick = () => {
      throw new Error('ancestor click handler should not fire');
    };

    render(
      <div onClick={onAncestorClick}>
        <InfoTip label="What does RSI mean?">RSI measures momentum.</InfoTip>
      </div>
    );

    expect(() =>
      fireEvent.click(screen.getByRole('button', { name: 'What does RSI mean?' }))
    ).not.toThrow();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <InfoTip label="What does RSI mean?" to="/metrics-explained#rsi">
        RSI measures momentum.
      </InfoTip>
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
