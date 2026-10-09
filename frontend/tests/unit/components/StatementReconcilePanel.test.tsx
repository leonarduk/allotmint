import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { StatementReconcilePanel } from '@/components/StatementReconcilePanel';
import {
  applyStatementSuggestion,
  getReconciliationProvider,
  reconcileStatement,
  type StatementReconciliation,
} from '@/api';

vi.mock('@/api', () => ({
  applyStatementSuggestion: vi.fn(),
  getReconciliationProvider: vi.fn(),
  reconcileStatement: vi.fn(),
}));

vi.mock('@/hooks/useDemoReadOnly', () => ({
  useDemoReadOnly: () => ({ demoReadOnly: false, reason: () => undefined }),
}));

const interestRequest = {
  method: 'POST' as const,
  path: '/transactions',
  body: { owner: 'alice', account: 'isa', type: 'INTEREST', amount_minor: 250 },
};

const RESULT: StatementReconciliation = {
  extracted: {
    document_type: 'statement',
    period_start: '2026-01-01',
    period_end: '2026-03-31',
    opening_cash_minor: 0,
    closing_cash_minor: 399055,
    rows: [],
    warnings: [],
  },
  matched: [{ statement_index: 0, ledger_id: 'alice:isa:0' }],
  diffs: [
    {
      kind: 'missing_from_ledger',
      message:
        'INTEREST on 2026-03-31 is on the statement but not in the ledger',
      statement_index: 2,
      ledger_id: null,
      ticker: null,
      date: '2026-03-31',
      statement_minor: 250,
      ledger_minor: null,
      difference_minor: null,
      statement_units: null,
      ledger_units: null,
      suggestion: {
        description: 'Add this INTEREST row (£2.50)',
        request: interestRequest,
      },
    },
    {
      kind: 'cash_mismatch',
      message:
        'Closing cash on the statement is £3,990.55; the ledger implies £4,000.00',
      statement_index: null,
      ledger_id: null,
      ticker: null,
      date: '2026-03-31',
      statement_minor: 399055,
      ledger_minor: 400000,
      difference_minor: -945,
      statement_units: null,
      ledger_units: null,
      suggestion: {
        description: 'Accept the missing rows above first',
        request: null,
      },
    },
  ],
  warnings: [
    'Row 2 (2026-01-10, BUY): units x price does not equal the consideration',
  ],
  llm_provider: 'ollama',
  sent_to_cloud: false,
  explanation: 'Interest probably not imported.',
};

const pdf = new File(['%PDF-1.4'], 'statement.pdf', {
  type: 'application/pdf',
});

async function reconcile() {
  render(
    <StatementReconcilePanel
      owner="alice"
      accountTypes={['isa']}
      onApplied={onApplied}
    />
  );
  await userEvent.upload(screen.getByLabelText('Statement (PDF or CSV)'), pdf);
  await userEvent.click(
    screen.getByRole('button', { name: 'Reconcile statement' })
  );
  await screen.findByRole('status', { name: 'Statement reconciliation' });
}

const onApplied = vi.fn();

describe('StatementReconcilePanel', () => {
  beforeEach(() => {
    vi.mocked(applyStatementSuggestion).mockReset();
    vi.mocked(reconcileStatement).mockReset().mockResolvedValue(RESULT);
    vi.mocked(getReconciliationProvider)
      .mockReset()
      .mockResolvedValue({ llm_provider: 'ollama', sent_to_cloud: false });
    onApplied.mockReset();
  });

  it('warns when the document text goes to a cloud provider', async () => {
    vi.mocked(getReconciliationProvider).mockResolvedValue({
      llm_provider: 'bedrock',
      sent_to_cloud: true,
    });
    render(<StatementReconcilePanel owner="alice" accountTypes={['isa']} />);

    expect(await screen.findByRole('note')).toHaveTextContent(
      'will be sent to the configured AI provider (bedrock)'
    );
  });

  it('says a local provider keeps the document on this machine', async () => {
    render(<StatementReconcilePanel owner="alice" accountTypes={['isa']} />);

    expect(await screen.findByRole('note')).toHaveTextContent(
      'does not leave this machine'
    );
  });

  it('disables reconcile until a file is chosen', async () => {
    render(<StatementReconcilePanel owner="alice" accountTypes={['isa']} />);
    const button = screen.getByRole('button', { name: 'Reconcile statement' });

    expect(button).toBeDisabled();
    await userEvent.upload(
      screen.getByLabelText('Statement (PDF or CSV)'),
      pdf
    );
    expect(button).toBeEnabled();
  });

  it('shows differences, warnings and amounts in pounds without writing anything', async () => {
    await reconcile();

    expect(reconcileStatement).toHaveBeenCalledWith('alice', 'isa', pdf, false);
    expect(screen.getByText(/1 matched · 2 differences/)).toBeInTheDocument();
    expect(screen.getByText('Missing from ledger')).toBeInTheDocument();
    expect(screen.getByText('Closing cash differs')).toBeInTheDocument();
    expect(screen.getByText('£3,990.55')).toBeInTheDocument();
    expect(screen.getByText('£4,000.00')).toBeInTheDocument();
    expect(
      screen.getByText(/units x price does not equal/)
    ).toBeInTheDocument();
    expect(
      screen.getByText('Interest probably not imported.')
    ).toBeInTheDocument();
    expect(applyStatementSuggestion).not.toHaveBeenCalled();
  });

  it('passes the explain option through', async () => {
    render(<StatementReconcilePanel owner="alice" accountTypes={['isa']} />);
    await userEvent.upload(
      screen.getByLabelText('Statement (PDF or CSV)'),
      pdf
    );
    await userEvent.click(
      screen.getByLabelText('Ask the assistant to explain unmatched rows')
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'Reconcile statement' })
    );

    await waitFor(() =>
      expect(reconcileStatement).toHaveBeenCalledWith('alice', 'isa', pdf, true)
    );
  });

  it('only offers Accept where a suggestion can be applied', async () => {
    await reconcile();

    expect(screen.getAllByRole('button', { name: 'Accept' })).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: 'Dismiss' })).toHaveLength(2);
  });

  it('applies a suggestion only after confirmation', async () => {
    vi.mocked(applyStatementSuggestion).mockResolvedValue({} as never);
    await reconcile();

    await userEvent.click(screen.getByRole('button', { name: 'Accept' }));
    expect(applyStatementSuggestion).not.toHaveBeenCalled();

    await userEvent.click(
      screen.getByRole('button', { name: 'Confirm change' })
    );

    expect(applyStatementSuggestion).toHaveBeenCalledWith(interestRequest);
    expect(await screen.findByText('Applied')).toBeInTheDocument();
    expect(onApplied).toHaveBeenCalledTimes(1);
  });

  it('cancelling a confirmation writes nothing', async () => {
    await reconcile();

    await userEvent.click(screen.getByRole('button', { name: 'Accept' }));
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(applyStatementSuggestion).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Accept' })).toBeInTheDocument();
  });

  it('shows an error when applying fails and lets the user retry', async () => {
    vi.mocked(applyStatementSuggestion).mockRejectedValue(
      new Error('reason is required')
    );
    await reconcile();

    await userEvent.click(screen.getByRole('button', { name: 'Accept' }));
    await userEvent.click(
      screen.getByRole('button', { name: 'Confirm change' })
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'reason is required'
    );
    expect(screen.getByRole('button', { name: 'Accept' })).toBeInTheDocument();
    expect(onApplied).not.toHaveBeenCalled();
  });

  it('dismisses a row with a reason', async () => {
    await reconcile();

    const [, cashDismiss] = screen.getAllByRole('button', { name: 'Dismiss' });
    await userEvent.click(cashDismiss);
    // The cash row now shows a reason box and its own (disabled) Dismiss.
    const confirmDismiss = () =>
      screen.getAllByRole('button', { name: 'Dismiss' }).at(-1)!;
    expect(confirmDismiss()).toBeDisabled();
    await userEvent.type(
      screen.getByLabelText('Reason for dismissing'),
      'Timing difference'
    );
    await userEvent.click(confirmDismiss());

    expect(
      screen.getByText('Dismissed: Timing difference')
    ).toBeInTheDocument();
    expect(applyStatementSuggestion).not.toHaveBeenCalled();
  });

  it('shows the backend error when reconciliation fails', async () => {
    vi.mocked(reconcileStatement).mockRejectedValue(
      new Error('The document has no text layer (it may be a scanned image)')
    );
    render(<StatementReconcilePanel owner="alice" accountTypes={['isa']} />);
    await userEvent.upload(
      screen.getByLabelText('Statement (PDF or CSV)'),
      pdf
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'Reconcile statement' })
    );

    expect(await screen.findByRole('alert')).toHaveTextContent('scanned image');
  });
});
