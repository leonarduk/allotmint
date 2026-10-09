import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { CashDeploymentRun } from '@/types';
import CashDeploymentCard from '@/components/CashDeploymentCard';
import { orderListText, pounds } from '@/lib/cashDeployment';

const mockGet = vi.hoisted(() => vi.fn());
const mockCreate = vi.hoisted(() => vi.fn());
const mockUpdate = vi.hoisted(() => vi.fn());
const mockDelete = vi.hoisted(() => vi.fn());

vi.mock('@/api', () => ({
  getCashDeployment: mockGet,
  createCashDeploymentSchedule: mockCreate,
  updateCashDeploymentSchedule: mockUpdate,
  deleteCashDeploymentSchedule: mockDelete,
}));

const ACCOUNTS = [{ id: 'isa', label: 'ISA', value: 1000, cash: 100 }];

const SCHEDULE = {
  id: 'abc123',
  created: '2026-01-01T00:00:00+00:00',
  account: 'isa',
  total_amount_minor: 1_200_000,
  tranches: 12,
  cadence: 'monthly' as const,
  start_date: '2026-01-15',
  target_source: 'plan' as const,
  status: 'active' as const,
};

const TRANCHE = {
  index: 0,
  due_date: '2026-01-15',
  amount_minor: 100_000,
  label: 'Draft order list per your plan.',
  keep_as_cash_minor: 0,
  orders: [
    {
      asset_class: 'equity',
      ticker: 'VWX.L',
      vehicle_note: null,
      amount_minor: 70_000,
      price_gbp: 12.5,
      indicative_units: 56,
    },
    {
      asset_class: 'long_gilts',
      ticker: null,
      vehicle_note: null,
      amount_minor: 30_000,
      price_gbp: null,
      indicative_units: null,
    },
  ],
};

function makeRun(
  overrides: Partial<CashDeploymentRun> = {}
): CashDeploymentRun {
  const row = {
    index: 0,
    due_date: '2026-01-15',
    window_end: '2026-02-15',
    amount_minor: 100_000,
    invested_minor: 0,
    status: 'due' as const,
    overdue: false,
  };
  return {
    bot: 'cash_deployment',
    owner: 'alex',
    as_of: '2026-01-15',
    status: 'ok',
    summary: '1 tranche(s) due now',
    warnings: [],
    schedules: [
      {
        schedule: SCHEDULE,
        error: null,
        tranche: TRANCHE,
        progress: {
          as_of: '2026-01-15',
          tranches: [row],
          total_amount_minor: 1_200_000,
          deployed_minor: 0,
          remaining_minor: 1_200_000,
          planned_to_date_minor: 100_000,
          planned_remaining_minor: 1_100_000,
          overdue_count: 0,
          interest_minor: 1234,
          current: row,
          summary:
            'On schedule: £12,000.00 still in cash vs £11,000.00 planned',
        },
      },
    ],
    ...overrides,
  };
}

describe('CashDeploymentCard', () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockCreate.mockReset();
    mockUpdate.mockReset();
    mockDelete.mockReset();
  });

  it('shows progress and the order list per your plan', async () => {
    mockGet.mockResolvedValue(makeRun());
    render(<CashDeploymentCard owner="alex" accounts={ACCOUNTS} />);
    expect(await screen.findByText(/On schedule/)).toBeInTheDocument();
    expect(screen.getByText(/per your plan/i)).toBeInTheDocument();
    expect(screen.getByText('VWX.L')).toBeInTheDocument();
    expect(screen.getByText('No vehicle in your plan')).toBeInTheDocument();
    expect(screen.getByText(/£12\.34 interest credited/)).toBeInTheDocument();
  });

  it('saves the schedule the owner entered, in pence', async () => {
    mockGet.mockResolvedValue(makeRun({ schedules: [] }));
    mockCreate.mockResolvedValue(SCHEDULE);
    render(<CashDeploymentCard owner="alex" accounts={ACCOUNTS} />);
    expect(await screen.findByText('No schedules yet.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Total (£)'), {
      target: { value: '12000.50' },
    });
    fireEvent.change(screen.getByLabelText('Tranches'), {
      target: { value: '6' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save schedule' }));
    await waitFor(() => expect(mockCreate).toHaveBeenCalled());
    expect(mockCreate.mock.calls[0][1]).toMatchObject({
      account: 'isa',
      total_amount_minor: 1_200_050,
      tranches: 6,
      cadence: 'monthly',
    });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.getByLabelText('Total (£)')).toHaveValue(null)
    );
  });

  it('keeps the entered total when saving fails', async () => {
    mockGet.mockResolvedValue(makeRun({ schedules: [] }));
    mockCreate.mockRejectedValue(new Error('Unknown account'));
    render(<CashDeploymentCard owner="alex" accounts={ACCOUNTS} />);
    await screen.findByText('No schedules yet.');
    fireEvent.change(screen.getByLabelText('Total (£)'), {
      target: { value: '500' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save schedule' }));
    expect(
      await screen.findByText(/Could not update the schedule: Unknown account/)
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Total (£)')).toHaveValue(500);
  });

  it('pauses a schedule without changing what the owner chose', async () => {
    mockGet.mockResolvedValue(makeRun());
    mockUpdate.mockResolvedValue({ ...SCHEDULE, status: 'paused' });
    render(<CashDeploymentCard owner="alex" accounts={ACCOUNTS} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Pause' }));
    await waitFor(() => expect(mockUpdate).toHaveBeenCalled());
    const { id: _id, created: _created, ...chosen } = SCHEDULE;
    expect(mockUpdate.mock.calls[0][2]).toEqual({
      ...chosen,
      status: 'paused',
    });
  });

  it('shows a load error', async () => {
    mockGet.mockRejectedValue(new Error('boom'));
    render(<CashDeploymentCard owner="alex" accounts={ACCOUNTS} />);
    expect(
      await screen.findByText(/Could not load schedules: boom/)
    ).toBeInTheDocument();
  });
});

describe('cash deployment helpers', () => {
  it('formats pence and the copyable order list', () => {
    expect(pounds(123_456)).toBe('£1,234.56');
    const text = orderListText(TRANCHE);
    expect(text.split('\n')[0]).toBe('Draft order list per your plan.');
    expect(text).toContain('equity\tVWX.L\t£700.00\t~56');
    expect(text).toContain('long_gilts\t-\t£300.00');
  });
});
