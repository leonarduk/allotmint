import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { CsvImportForm } from '@/components/CsvImportForm';
import { importHoldingsCsv, reconcileHoldingsCsv } from '@/api';

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

    await userEvent.selectOptions(screen.getByLabelText('Provider'), 'degiro');
    expect(submit).toBeDisabled();

    const fileInput = screen.getByLabelText('CSV file');
    await userEvent.upload(fileInput, csvFile);
    expect(submit).toBeEnabled();
    expect(reconcile).toBeEnabled();
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

    await userEvent.selectOptions(screen.getByLabelText('Provider'), 'degiro');
    await userEvent.upload(screen.getByLabelText('CSV file'), csvFile);
    await userEvent.click(screen.getByRole('button', { name: 'Import' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Unknown provider: bogus'
    );
  });
});
