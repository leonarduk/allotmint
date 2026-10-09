import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RetirementReadinessReport } from '@/api';

const mockLatest = vi.hoisted(() => vi.fn());
const mockHistory = vi.hoisted(() => vi.fn());
const mockRun = vi.hoisted(() => vi.fn());

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api');
  return {
    ...actual,
    getRetirementReadinessLatest: mockLatest,
    getRetirementReadinessHistory: mockHistory,
    runRetirementReadiness: mockRun,
  };
});

import RetirementReadinessCard from '@/components/RetirementReadinessCard';

// Synthetic figures only.
const report: RetirementReadinessReport = {
  owner: 'alex',
  run_date: '2030-04-15',
  headline: { survival_pct: 95, income_gbp: 9100.55 },
  inputs: { pot_gbp: 110000, retirement_age: 60, death_age: 90 },
  results: {
    projection: {
      projected_pot_nominal_gbp: 250000,
      start_pot_real_gbp: 200000,
      years_to_retirement: 6,
    },
    simulation: {
      horizon_years: 30,
      windows: { count: 4 },
      sustainable_income: [
        { survival_pct: 95, income_gbp: 9100.55 },
        { survival_pct: 100, income_gbp: 8700.25 },
      ],
      worst: {
        start_year: 1992,
        end_year: 2021,
        sustainable_income_gbp: 8700.25,
      },
      median: {
        start_year: 1993,
        end_year: 2022,
        sustainable_income_gbp: 9400,
      },
      best: { start_year: 1994, end_year: 2023, sustainable_income_gbp: 9900 },
      floor: null,
    },
    mapping: { proxy_share_pct: 60 },
    data_notes: [
      'No gold_gbp data for 1871-1927; windows touching those years are excluded.',
    ],
  },
  attribution: {
    previous_run_date: '2030-01-15',
    change_gbp: 400.3,
    parts_gbp: {
      contributions: 400.3,
      markets: 0,
      assumptions: 0,
      data_revision: 0,
    },
  },
  assumption_changes: [{ label: 'retirement age' }],
  market: { flags: ['UK CPI inflation was 4% in 2029.'] },
  caveats: [
    'Past sequences of returns are not a forecast.',
    'Information only, not advice.',
  ],
  narrative: { text: 'Template text', source: 'template', note: null },
};

const trend = [
  {
    run_date: '2030-01-15',
    survival_pct: 95,
    sustainable_income_gbp: 8700.25,
    pot_gbp: 100000,
  },
  {
    run_date: '2030-04-15',
    survival_pct: 95,
    sustainable_income_gbp: 9100.55,
    pot_gbp: 110000,
  },
];

describe('RetirementReadinessCard', () => {
  beforeEach(() => {
    mockLatest.mockReset();
    mockHistory.mockReset();
    mockRun.mockReset();
  });

  it('renders the stored figures, trend, attribution, flags and caveats', async () => {
    mockLatest.mockResolvedValue(report);
    mockHistory.mockResolvedValue({ owner: 'alex', trend });
    render(<RetirementReadinessCard owner="alex" />);

    expect(await screen.findByText('95%')).toBeInTheDocument();
    expect(mockLatest).toHaveBeenCalledWith('alex');
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByText(/1992–2021/)).toBeInTheDocument();
    expect(
      screen.getByTestId('retirement-readiness-trend')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('retirement-readiness-attribution')
    ).toHaveTextContent('2030-01-15');
    expect(
      screen.getByText('UK CPI inflation was 4% in 2029.')
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Changed since the last run: retirement age/)
    ).toBeInTheDocument();
    expect(
      screen.getByText('Information only, not advice.')
    ).toBeInTheDocument();
    expect(screen.getByText(/No gold_gbp data/)).toBeInTheDocument();
    // The template narrative duplicates the figures above, so it is not shown.
    expect(
      screen.queryByTestId('retirement-readiness-narrative')
    ).not.toBeInTheDocument();
  });

  it('shows a model narrative when there is one', async () => {
    mockLatest.mockResolvedValue({
      ...report,
      narrative: { text: 'Model summary', source: 'llm', note: null },
    });
    mockHistory.mockResolvedValue({ owner: 'alex', trend });
    render(<RetirementReadinessCard owner="alex" />);
    expect(
      await screen.findByTestId('retirement-readiness-narrative')
    ).toHaveTextContent('Model summary');
  });

  it('offers a run when no report is stored, then shows the result', async () => {
    mockLatest.mockRejectedValueOnce(
      Object.assign(new Error('not found'), { status: 404 })
    );
    mockHistory.mockResolvedValueOnce({ owner: 'alex', trend: [] });
    render(<RetirementReadinessCard owner="alex" />);
    expect(
      await screen.findByText(/No readiness report yet/)
    ).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    mockRun.mockResolvedValue(report);
    mockLatest.mockResolvedValue(report);
    mockHistory.mockResolvedValue({ owner: 'alex', trend: trend.slice(1) });
    await userEvent.click(screen.getByRole('button', { name: 'Run now' }));
    await waitFor(() => expect(mockRun).toHaveBeenCalledWith('alex'));
    expect(await screen.findByText('95%')).toBeInTheDocument();
    // A single run has no trend line yet.
    expect(
      screen.queryByTestId('retirement-readiness-trend')
    ).not.toBeInTheDocument();
  });

  it('surfaces a failed run', async () => {
    mockLatest.mockRejectedValue(
      Object.assign(new Error('not found'), { status: 404 })
    );
    mockHistory.mockResolvedValue({ owner: 'alex', trend: [] });
    mockRun.mockRejectedValue(new Error('no investment plan saved for alex'));
    render(<RetirementReadinessCard owner="alex" />);
    await userEvent.click(
      await screen.findByRole('button', { name: 'Run now' })
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'no investment plan'
    );
  });
});
