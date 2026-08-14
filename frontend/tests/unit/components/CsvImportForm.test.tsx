import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { CsvImportForm } from '@/components/CsvImportForm';
import {
  importHoldingsCsv,
  reconcileHoldingsCsv,
  type ReconcileHoldingsCsvResponse,
} from '@/api';

vi.mock('@/api', () => ({
  importHoldingsCsv: vi.fn(),
  reconcileHoldingsCsv: vi.fn(),
}));

describe('CsvImportForm', () => {
  beforeEach(() => {
    vi.mocked(importHoldingsCsv).mockReset();
    vi.mocked(reconcileHoldingsCsv).mockReset();
  });

  const csvFile = new File(['a,b\n1,2'], 'holdings.csv', { type: 'text/csv' });

  it('disables submit until a provider and file are chosen', async () => {
    render(<CsvImportForm owner="alice" accountTypes={['ISA', 'SIPP']} />);

    const submit = screen.getByRole('button', { name: 'Import' });
    const reconcile = screen.getByRole('button', { name: /Reconcile/ });
    expect(submit).toBeDisabled();
    expect(reconcile).toBeDisabled();

    await userEvent.selectOptions(screen.getByLabelText('Provider'), 'hargreaves');
    expect(submit).toBeDisabled();

    const fileInput = screen.getByLabelText('CSV file');
    await userEvent.upload(fileInput, csvFile);
    expect(submit).toBeEnabled();
    expect(reconcile).toBeEnabled();
  });

  it('renders duplicate account types without a React key warning', () => {
    const consoleError = vi
      .spyOn(console, 'error')
      .mockImplementation(() => undefined);

    render(
      <CsvImportForm owner="alice" accountTypes={['ISA', 'ISA', 'SIPP']} />
    );

    expect(screen.getAllByRole('option', { name: /ISA|SIPP/ })).toHaveLength(3);
    expect(consoleError.mock.calls.flat().join(' ')).not.toContain('same key');
    consoleError.mockRestore();
  });

  it('previews a readable reconciliation without importing', async () => {
    vi.mocked(reconcileHoldingsCsv).mockResolvedValue({
      added: [{ ticker: 'NEW.L', units: 5, value_gbp: 10 }],
      removed: [{ ticker: 'OLD.L', units: 2, value_gbp: 6 }],
      quantity_changed: [
        { ticker: 'AAA.L', stored_units: 8, imported_units: 10, delta: 2 },
      ],
      value_changed: [
        {
          ticker: 'AAA.L',
          stored_value_gbp: 11.2,
          imported_value_gbp: 15,
          delta_gbp: 3.8,
        },
      ],
      cash_balance: { stored_gbp: 100, imported_gbp: 110, delta_gbp: 10 },
    });

    render(<CsvImportForm owner="alice" accountTypes={['ISA']} />);
    await userEvent.selectOptions(
      screen.getByLabelText('Provider'),
      'hargreaves'
    );
    await userEvent.upload(screen.getByLabelText('CSV file'), csvFile);
    await userEvent.click(screen.getByRole('button', { name: /Reconcile/ }));

    expect(reconcileHoldingsCsv).toHaveBeenCalledWith(
      'alice',
      'ISA',
      'hargreaves',
      csvFile
    );
    expect(importHoldingsCsv).not.toHaveBeenCalled();
    const preview = await screen.findByRole('status', {
      name: 'Reconciliation preview',
    });
    expect(preview).toHaveTextContent('Preview only');
    expect(preview).toHaveTextContent('NEW.L');
    expect(preview).toHaveTextContent('OLD.L');
    expect(preview).toHaveTextContent('AAA.L');
    expect(preview).toHaveTextContent('£100.00 → £110.00 (+£10.00)');
  });

  it('preserves a small fractional unit delta instead of showing "+0"', async () => {
    vi.mocked(reconcileHoldingsCsv).mockResolvedValue({
      added: [],
      removed: [],
      quantity_changed: [
        {
          ticker: 'FRAC.L',
          stored_units: 1.0001,
          imported_units: 1.0002,
          delta: 0.0001,
        },
      ],
      value_changed: [],
      cash_balance: { stored_gbp: 0, imported_gbp: 0, delta_gbp: 0 },
    });

    render(<CsvImportForm owner="alice" accountTypes={['ISA']} />);
    await userEvent.selectOptions(screen.getByLabelText('Provider'), 'hargreaves');
    await userEvent.upload(screen.getByLabelText('CSV file'), csvFile);
    await userEvent.click(screen.getByRole('button', { name: /Reconcile/ }));

    const preview = await screen.findByRole('status', {
      name: 'Reconciliation preview',
    });
    expect(preview).toHaveTextContent('1.0001 → 1.0002 (+0.0001)');
    expect(preview).not.toHaveTextContent('(+0)');
  });

  it('clears a completed preview when the account changes', async () => {
    vi.mocked(reconcileHoldingsCsv).mockResolvedValue({
      added: [{ ticker: 'NEW.L', units: 5, value_gbp: 10 }],
      removed: [],
      quantity_changed: [],
      value_changed: [],
      cash_balance: { stored_gbp: 0, imported_gbp: 0, delta_gbp: 0 },
    });

    render(<CsvImportForm owner="alice" accountTypes={['ISA', 'SIPP']} />);
    await userEvent.selectOptions(screen.getByLabelText('Provider'), 'hargreaves');
    await userEvent.upload(screen.getByLabelText('CSV file'), csvFile);
    await userEvent.click(screen.getByRole('button', { name: /Reconcile/ }));
    await screen.findByRole('status', { name: 'Reconciliation preview' });

    await userEvent.selectOptions(screen.getByLabelText('Account'), 'SIPP');

    expect(
      screen.queryByRole('status', { name: 'Reconciliation preview' })
    ).not.toBeInTheDocument();
  });

  it('ignores a reconcile response that resolves after the account changed', async () => {
    let resolveReconcile:
      | ((value: ReconcileHoldingsCsvResponse) => void)
      | undefined;
    vi.mocked(reconcileHoldingsCsv).mockReturnValue(
      new Promise((resolve) => {
        resolveReconcile = resolve;
      })
    );

    render(<CsvImportForm owner="alice" accountTypes={['ISA', 'SIPP']} />);
    await userEvent.selectOptions(screen.getByLabelText('Provider'), 'hargreaves');
    await userEvent.upload(screen.getByLabelText('CSV file'), csvFile);
    await userEvent.click(screen.getByRole('button', { name: /Reconcile/ }));

    // The account changes while the reconcile request for "ISA" is still in flight.
    await userEvent.selectOptions(screen.getByLabelText('Account'), 'SIPP');

    await act(async () => {
      resolveReconcile?.({
        added: [{ ticker: 'STALE.L', units: 1, value_gbp: 1 }],
        removed: [],
        quantity_changed: [],
        value_changed: [],
        cash_balance: { stored_gbp: 0, imported_gbp: 0, delta_gbp: 0 },
      });
      await Promise.resolve();
    });

    expect(
      screen.queryByRole('status', { name: 'Reconciliation preview' })
    ).not.toBeInTheDocument();
  });

  it('submits the selected account, provider and file as multipart data', async () => {
    vi.mocked(importHoldingsCsv).mockResolvedValue({
      path: '/data/accounts/alice/ISA.json',
    });

    render(<CsvImportForm owner="alice" accountTypes={['ISA', 'SIPP']} />);

    await userEvent.selectOptions(screen.getByLabelText('Account'), 'SIPP');
    await userEvent.selectOptions(
      screen.getByLabelText('Provider'),
      'hargreaves'
    );
    await userEvent.upload(screen.getByLabelText('CSV file'), csvFile);
    await userEvent.click(screen.getByRole('button', { name: 'Import' }));

    expect(importHoldingsCsv).toHaveBeenCalledWith(
      'alice',
      'SIPP',
      'hargreaves',
      csvFile
    );
    expect(
      await screen.findByText(/Imported successfully/)
    ).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(
      '/data/accounts/alice/ISA.json'
    );
  });

  it('shows the backend error message for an unknown provider', async () => {
    vi.mocked(importHoldingsCsv).mockRejectedValue(
      new Error('Unknown provider: bogus')
    );

    render(<CsvImportForm owner="alice" accountTypes={['ISA']} />);

    await userEvent.selectOptions(screen.getByLabelText('Provider'), 'hargreaves');
    await userEvent.upload(screen.getByLabelText('CSV file'), csvFile);
    await userEvent.click(screen.getByRole('button', { name: 'Import' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Unknown provider: bogus'
    );
  });

  it('does not emit duplicate-key warnings when the same ticker appears in a diff section (#6505)', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.mocked(reconcileHoldingsCsv).mockResolvedValue({
      added: [
        { ticker: 'CASH', units: 5, value_gbp: 10 },
        { ticker: 'CASH', units: 3, value_gbp: 6 },
      ],
      removed: [],
      quantity_changed: [],
      value_changed: [],
      cash_balance: { stored_gbp: 100, imported_gbp: 110, delta_gbp: 10 },
    });

    render(<CsvImportForm owner="alice" accountTypes={['ISA']} />);
    await userEvent.selectOptions(
      screen.getByLabelText('Provider'),
      'hargreaves'
    );
    await userEvent.upload(screen.getByLabelText('CSV file'), csvFile);
    await userEvent.click(screen.getByRole('button', { name: /Reconcile/ }));

    expect(await screen.findAllByText('CASH')).toHaveLength(2);
    const keyWarnings = errorSpy.mock.calls.filter((args) =>
      String(args[0]).includes('same key')
    );
    expect(keyWarnings).toEqual([]);
    errorSpy.mockRestore();
  });
});
