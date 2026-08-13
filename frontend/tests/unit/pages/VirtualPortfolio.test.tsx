import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import VirtualPortfolio from '@/pages/VirtualPortfolio';
import * as api from '@/api';

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api');
  return {
    ...actual,
    logAnalyticsEvent: vi.fn().mockResolvedValue(undefined),
    createAccount: vi.fn(),
    createManualHolding: vi.fn(),
  };
});

const STORAGE_KEY = 'familyManualPortfolio.v1';

function renderPage(owner = '') {
  return render(
    <MemoryRouter>
      <VirtualPortfolio owner={owner} />
    </MemoryRouter>
  );
}

describe('VirtualPortfolio page', () => {
  afterEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it('sends a view analytics event', () => {
    const mockLogAnalyticsEvent = vi.mocked(api.logAnalyticsEvent);
    renderPage();
    expect(mockLogAnalyticsEvent).toHaveBeenCalledWith(
      expect.objectContaining({ source: 'virtual_portfolio', event: 'view' })
    );
  });

  it('clearly identifies browser-only drafts and links to the saved portfolio', () => {
    renderPage();

    expect(screen.getByText('Local draft')).toBeInTheDocument();
    expect(
      screen.getByText(/not saved to your AllotMint account/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/cannot currently be transferred automatically/i)
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Open saved portfolio' })
    ).toHaveAttribute('href', '/portfolio');
  });

  it('adds multiple accounts and holdings', () => {
    renderPage();

    const addInput = screen.getByPlaceholderText(/Account name/i);
    fireEvent.change(addInput, { target: { value: 'ISA' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add account' }));

    fireEvent.change(addInput, { target: { value: 'Pension' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add account' }));

    expect(screen.getAllByLabelText('Account name')).toHaveLength(2);

    fireEvent.click(screen.getAllByRole('button', { name: 'Add holding' })[0]);

    const tickerInputs = screen.getAllByPlaceholderText('AAPL');
    expect(tickerInputs.length).toBeGreaterThanOrEqual(3);
  });

  it('persists and hydrates from localStorage', () => {
    renderPage();

    const addInput = screen.getByPlaceholderText(/Account name/i);
    fireEvent.change(addInput, { target: { value: 'Brokerage' } });
    fireEvent.submit(addInput.closest('form')!);

    // Rename via the account name input: change + blur to commit.
    const accountNameInput = screen.getByLabelText('Account name');
    fireEvent.change(accountNameInput, { target: { value: 'Brokerage Main' } });
    fireEvent.blur(accountNameInput);

    const stored = window.localStorage.getItem(STORAGE_KEY);
    expect(stored).toContain('Brokerage Main');

    renderPage();
    expect(
      screen.getAllByDisplayValue('Brokerage Main').length
    ).toBeGreaterThan(0);
  });

  it('prevents duplicate account names and shows feedback', () => {
    renderPage();

    const addInput = screen.getByPlaceholderText(/Account name/i);
    fireEvent.change(addInput, { target: { value: 'ISA' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add account' }));

    fireEvent.change(addInput, { target: { value: 'isa' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add account' }));

    expect(screen.getByText('Use a unique account name.')).toBeInTheDocument();
    expect(screen.getAllByLabelText('Account name')).toHaveLength(1);
  });

  it('filters malformed holdings from stored payload', () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([
        {
          id: 'a-1',
          name: 'ISA',
          holdings: [{ ticker: 'AAPL' }],
        },
      ])
    );

    renderPage();

    expect(screen.getByLabelText('Account name')).toHaveValue('ISA');
    // Malformed holding was stripped; account still gets one blank holding row.
    expect(screen.getByPlaceholderText('AAPL')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('AAPL')).toHaveValue('');
  });

  it('shows a status message when localStorage write fails', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota');
    });

    renderPage();

    const addInput = screen.getByPlaceholderText(/Account name/i);
    fireEvent.change(addInput, { target: { value: 'ISA' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add account' }));

    expect(
      screen.getByText(
        'Changes were not saved in this browser. Try freeing local storage space.'
      )
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('Account name')).not.toBeInTheDocument();
  });

  it('allows typing an intermediate empty value without snapping back', () => {
    renderPage();

    const addInput = screen.getByPlaceholderText(/Account name/i);
    fireEvent.change(addInput, { target: { value: 'ISA' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add account' }));

    const accountNameInput = screen.getByLabelText('Account name');

    // Clear the field mid-edit — input should show empty, not snap back to "ISA".
    fireEvent.change(accountNameInput, { target: { value: '' } });
    expect(accountNameInput).toHaveValue('');

    // Blur without a valid value — input reverts to saved name, warning shown.
    fireEvent.blur(accountNameInput);
    expect(
      screen.getByText('Account name cannot be empty.')
    ).toBeInTheDocument();
    expect(accountNameInput).toHaveValue('ISA');
  });

  it('rejects duplicate account renames on blur', () => {
    renderPage();

    const addInput = screen.getByPlaceholderText(/Account name/i);
    fireEvent.change(addInput, { target: { value: 'ISA' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add account' }));
    fireEvent.change(addInput, { target: { value: 'Pension' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add account' }));

    // Try to rename Pension to ISA (case-insensitive).
    const [, pensionInput] = screen.getAllByLabelText('Account name');
    fireEvent.change(pensionInput, { target: { value: 'isa' } });
    fireEvent.blur(pensionInput);

    expect(
      screen.getByText('Account names must stay unique.')
    ).toBeInTheDocument();
    // Input should revert to "Pension", not remain as "isa".
    expect(pensionInput).toHaveValue('Pension');
  });

  it('confirms and copies draft holdings into the saved portfolio', async () => {
    vi.mocked(api.createAccount).mockResolvedValue({
      status: 'created',
      owner: 'family',
      account: 'isa',
      currency: 'GBP',
    });
    vi.mocked(api.createManualHolding).mockResolvedValue({
      status: 'created',
      owner: 'family',
      account: 'isa',
      holding: {},
    });
    renderPage('family');

    fireEvent.change(screen.getByPlaceholderText(/Account name/i), {
      target: { value: 'ISA' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add account' }));
    fireEvent.change(screen.getByPlaceholderText('AAPL'), {
      target: { value: 'VWRL' },
    });
    fireEvent.change(screen.getByPlaceholderText('25000'), {
      target: { value: '12500' },
    });

    fireEvent.click(
      screen.getByRole('button', { name: 'Commit to portfolio' })
    );
    expect(
      screen.getByRole('dialog', { name: 'Commit this draft?' })
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm commit' }));

    await waitFor(() =>
      expect(api.createManualHolding).toHaveBeenCalledWith({
        owner: 'family',
        account: 'isa',
        ticker: 'VWRL',
        value_gbp: 12500,
      })
    );
    expect(window.localStorage.getItem(STORAGE_KEY)).toContain('VWRL');
  });

  it('disables the Remove button when only one holding remains', () => {
    renderPage();

    const addInput = screen.getByPlaceholderText(/Account name/i);
    fireEvent.change(addInput, { target: { value: 'ISA' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add account' }));

    // Single holding row — Remove button must be disabled.
    const removeButton = screen.getByRole('button', { name: 'Remove holding' });
    expect(removeButton).toBeDisabled();

    // Add a second holding — Remove should now be enabled.
    fireEvent.click(screen.getByRole('button', { name: 'Add holding' }));
    const removeButtons = screen.getAllByRole('button', {
      name: 'Remove holding',
    });
    expect(removeButtons).toHaveLength(2);
    removeButtons.forEach((btn) => expect(btn).not.toBeDisabled());
  });
});
