import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CostBasisCsvImport } from '@/components/CostBasisCsvImport';
import { importCostBasisCsv } from '@/api';
import type { CostBasisGap } from '@/lib/costBasisChecklist';

vi.mock('@/api', () => ({
  importCostBasisCsv: vi.fn(),
}));

const gaps: CostBasisGap[] = [
  {
    owner: 'alex',
    account: 'isa',
    ticker: 'AAA.L',
    name: 'Synthetic A',
    units: 10,
    marketValue: 100,
    source: 'unknown',
  },
];

const csvFile = () =>
  new File(
    ['ticker,date,units,unit_cost\nAAA.L,2020-01-02,10,2\n'],
    'lots.csv',
    {
      type: 'text/csv',
    }
  );

describe('CostBasisCsvImport', () => {
  beforeEach(() => {
    vi.mocked(importCostBasisCsv).mockReset();
  });

  it('uploads the CSV for the single owner, reports the outcome and reloads', async () => {
    vi.mocked(importCostBasisCsv).mockResolvedValue({
      updated: [
        {
          owner: 'alex',
          account: 'isa',
          ticker: 'AAA.L',
          units: 10,
          cost_basis_gbp: 20,
          lots: 1,
        },
      ],
      skipped: [
        {
          line: 3,
          ticker: 'ZZZ.L',
          account: 'isa',
          skip_reason: 'no ZZZ.L holding in this account',
        },
      ],
    });
    const onImported = vi.fn();
    const user = userEvent.setup();
    render(<CostBasisCsvImport gaps={gaps} onImported={onImported} />);

    const file = csvFile();
    await user.upload(
      screen.getByLabelText('Upload purchase prices CSV'),
      file
    );

    expect(importCostBasisCsv).toHaveBeenCalledWith(file, 'alex');
    expect(
      await screen.findByText(/Recorded a cost for 1 holding\. 1 row skipped\./)
    ).toBeInTheDocument();
    expect(
      screen.getByText('Line 3 (ZZZ.L): no ZZZ.L holding in this account')
    ).toBeInTheDocument();
    expect(onImported).toHaveBeenCalledTimes(1);
  });

  it('does not reload when nothing was recorded', async () => {
    vi.mocked(importCostBasisCsv).mockResolvedValue({
      updated: [],
      skipped: [],
    });
    const onImported = vi.fn();
    const user = userEvent.setup();
    render(<CostBasisCsvImport gaps={gaps} onImported={onImported} />);

    await user.upload(
      screen.getByLabelText('Upload purchase prices CSV'),
      csvFile()
    );

    expect(
      await screen.findByText(/Recorded a cost for 0 holdings\./)
    ).toBeInTheDocument();
    expect(onImported).not.toHaveBeenCalled();
  });

  it('shows the error when the upload fails', async () => {
    vi.mocked(importCostBasisCsv).mockRejectedValue(
      new Error('Missing column(s): unit_cost')
    );
    const user = userEvent.setup();
    render(<CostBasisCsvImport gaps={gaps} />);

    await user.upload(
      screen.getByLabelText('Upload purchase prices CSV'),
      csvFile()
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Import failed: Missing column(s): unit_cost'
    );
  });
});
