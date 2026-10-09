import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { FundUpkeepProposal } from '@/types';

vi.mock('@/api', () => ({
  getFundUpkeepProposals: vi.fn(),
  decideFundUpkeepProposal: vi.fn(),
}));

import { FundUpkeepProposals } from '@/components/FundUpkeepProposals';
import { decideFundUpkeepProposal, getFundUpkeepProposals } from '@/api';

const pending: FundUpkeepProposal = {
  id: 'p1',
  kind: 'ongoing_charge',
  ticker: 'FUNDX.L',
  value: 0.22,
  source_url: 'https://issuer.example.com/docs/fundx-kiid.pdf',
  document_date: '2026-09-01',
  status: 'pending',
  created_at: '2026-10-09T08:00:00Z',
};

describe('FundUpkeepProposals (#10482)', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows each proposal with its value, source link and document date', async () => {
    vi.mocked(getFundUpkeepProposals).mockResolvedValue([
      pending,
      { ...pending, id: 'p2', status: 'rejected' },
    ]);

    render(<FundUpkeepProposals />);

    const row = await screen.findByTestId('fund-upkeep-proposal-p1');
    expect(row).toHaveTextContent('FUNDX.L');
    expect(row).toHaveTextContent('Ongoing charge: 0.22%');
    expect(row).toHaveTextContent('dated 2026-09-01');
    const link = screen.getByRole('link', { name: 'Source document' });
    expect(link).toHaveAttribute('href', pending.source_url);
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    // Rejected proposals are not listed.
    expect(screen.queryByTestId('fund-upkeep-proposal-p2')).not.toBeInTheDocument();
  });

  it('shows the proposed look-through breakdown before approval', async () => {
    vi.mocked(getFundUpkeepProposals).mockResolvedValue([
      {
        ...pending,
        id: 'lt1',
        kind: 'look_through',
        value: {
          countries: { Japan: 40, 'United States': 60 },
          sectors: { Technology: 100 },
        },
      },
    ]);

    render(<FundUpkeepProposals />);

    expect(await screen.findByTestId('fund-upkeep-proposal-lt1')).toHaveTextContent(
      'Look-through breakdown: United States 60.00%, Japan 40.00%; Technology 100.00%'
    );
  });

  it('approves a proposal and reloads the list, offering undo', async () => {
    vi.mocked(getFundUpkeepProposals)
      .mockResolvedValueOnce([pending])
      .mockResolvedValueOnce([{ ...pending, status: 'approved' }]);
    vi.mocked(decideFundUpkeepProposal).mockResolvedValue({
      ...pending,
      status: 'approved',
    });

    render(<FundUpkeepProposals />);
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));

    await waitFor(() =>
      expect(decideFundUpkeepProposal).toHaveBeenCalledWith('p1', 'approve')
    );
    expect(await screen.findByRole('button', { name: 'Undo' })).toBeInTheDocument();
    expect(screen.getByText(/Approved/)).toBeInTheDocument();
  });

  it('reports a failed action instead of swallowing it', async () => {
    vi.mocked(getFundUpkeepProposals).mockResolvedValue([pending]);
    vi.mocked(decideFundUpkeepProposal).mockRejectedValue(new Error('HTTP 409'));

    render(<FundUpkeepProposals />);
    fireEvent.click(await screen.findByRole('button', { name: 'Reject' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Action failed: HTTP 409'
    );
  });

  it('says when nothing is waiting', async () => {
    vi.mocked(getFundUpkeepProposals).mockResolvedValue([]);

    render(<FundUpkeepProposals />);

    expect(
      await screen.findByText('No proposals waiting for review.')
    ).toBeInTheDocument();
  });
});
