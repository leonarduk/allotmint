import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { StrategyList, StrategyStressResult } from '@/types';

const mockGetEvents = vi.hoisted(() => vi.fn());
const mockRunStrategyStress = vi.hoisted(() => vi.fn());
const mockApplyStrategy = vi.hoisted(() => vi.fn());

vi.mock('@/api', () => ({
  getEvents: mockGetEvents,
  runStrategyStress: mockRunStrategyStress,
  applyStrategy: mockApplyStrategy,
}));

import StrategyStressPanel from '@/components/StrategyStressPanel';

const DATA: StrategyList = { strategies: [], active: null };

function horizon(return_pct: number | null, missing: string[] = []) {
  return {
    return_pct,
    coverage_pct: missing.length ? 70 : 100,
    return_basis: return_pct == null ? null : 'total',
    missing,
  };
}

const RESULT: StrategyStressResult = {
  event: { id: 'covid', name: 'Covid crash', date: '2020-02-19' },
  horizons: ['1m', '1y'],
  portfolio: {
    baseline_total_value_gbp: 1000,
    horizons: {
      '1m': {
        return_pct: -15,
        coverage_pct: 92,
        return_basis: 'total',
        missing: [],
      },
      '1y': {
        return_pct: 3,
        coverage_pct: 100,
        return_basis: 'total',
        missing: [],
      },
    },
  },
  strategies: [
    {
      id: '60_40',
      name: '60/40',
      builtin: true,
      targets: { equity: 60, intermediate_gilts: 40 },
      horizons: { '1m': horizon(-11.2), '1y': horizon(2.6) },
      series: { equity: ['VWRL.L'], intermediate_gilts: ['IGLT.L'] },
    },
    {
      id: 'swensen',
      name: 'Swensen',
      builtin: true,
      targets: { equity: 70, property: 30 },
      horizons: {
        '1m': horizon(null, ['property']),
        '1y': horizon(null, ['property']),
      },
      series: { equity: ['VWRL.L'], property: [] },
    },
    {
      id: 'permanent',
      name: 'Permanent Portfolio',
      builtin: true,
      targets: { equity: 25, cash: 75 },
      horizons: { '1m': horizon(-5), '1y': horizon(1) },
      series: { equity: ['VWRL.L'], cash: ['cash (held flat)'] },
    },
  ],
  pro_history: false,
  disclaimer: 'Not advice.',
};

function renderPanel(
  url = '/strategy',
  props: Partial<{ hasTargets: boolean }> = {}
) {
  const onChanged = vi.fn().mockResolvedValue(undefined);
  render(
    <MemoryRouter initialEntries={[url]}>
      <StrategyStressPanel
        owner="alex"
        data={DATA}
        hasTargets={props.hasTargets ?? false}
        onChanged={onChanged}
      />
    </MemoryRouter>
  );
  return { onChanged };
}

describe('StrategyStressPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetEvents.mockResolvedValue([{ id: 'covid', name: 'Covid crash' }]);
    mockRunStrategyStress.mockResolvedValue(RESULT);
    mockApplyStrategy.mockResolvedValue({});
  });

  it('runs the chosen event and lists the portfolio first, then each strategy', async () => {
    renderPanel();
    const select = await screen.findByRole('combobox', { name: 'Event' });
    await screen.findByRole('option', { name: 'Covid crash' });
    fireEvent.change(select, { target: { value: 'covid' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run stress test' }));

    await screen.findByText('Your current portfolio');
    expect(mockRunStrategyStress).toHaveBeenCalledWith('alex', {
      event_id: 'covid',
      horizons: ['1m', '3m', '1y'],
    });
    const rows = screen.getAllByRole('row');
    expect(
      within(rows[1]).getByText('Your current portfolio')
    ).toBeInTheDocument();
    expect(within(rows[1]).getByText('-15.00%')).toBeInTheDocument();
    expect(within(rows[1]).getByText('92% priced')).toBeInTheDocument();
    expect(within(rows[2]).getByText('-11.20%')).toBeInTheDocument();
    expect(within(rows[2]).getByText(/Equity: VWRL\.L/)).toBeInTheDocument();
  });

  it('shows "not enough data" naming the missing asset class instead of a number', async () => {
    renderPanel('/strategy?stress_event=covid');
    const row = (await screen.findByText('Swensen')).closest('tr')!;
    expect(within(row).getAllByText('Not enough data')).toHaveLength(2);
    expect(
      within(row).getByText('No price history for: Property')
    ).toBeInTheDocument();
    expect(within(row).queryByText(/%$/)).toBeNull();
  });

  it('runs straight away when opened from the scenario page with an event and horizons', async () => {
    renderPanel('/strategy?stress_event=covid&horizons=1w,1y,bogus');
    await waitFor(() =>
      expect(mockRunStrategyStress).toHaveBeenCalledWith('alex', {
        event_id: 'covid',
        horizons: ['1w', '1y'],
      })
    );
    expect(mockRunStrategyStress).toHaveBeenCalledTimes(1);
  });

  it('uses a custom date when no event is chosen', async () => {
    renderPanel();
    fireEvent.change(screen.getByLabelText('Event date'), {
      target: { value: '2008-09-15' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Run stress test' }));
    await waitFor(() =>
      expect(mockRunStrategyStress).toHaveBeenCalledWith('alex', {
        date: '2008-09-15',
        horizons: ['1m', '3m', '1y'],
      })
    );
  });

  it('sorts strategies best first by a horizon, rows without data last', async () => {
    renderPanel('/strategy?stress_event=covid');
    await screen.findByText('Swensen');
    fireEvent.click(screen.getByRole('button', { name: 'Sort by 1m' }));
    const names = screen
      .getAllByRole('row')
      .slice(2)
      .map((r) => r.cells[0].firstChild?.textContent);
    expect(names).toEqual(['Permanent Portfolio', '60/40', 'Swensen']);
  });

  it('applies a strategy from its row after confirming, then reloads', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const { onChanged } = renderPanel('/strategy?stress_event=covid', {
      hasTargets: true,
    });
    fireEvent.click(await screen.findByRole('button', { name: 'Apply 60/40' }));
    await screen.findByRole('status');
    expect(confirm).toHaveBeenCalled();
    expect(mockApplyStrategy).toHaveBeenCalledWith('alex', '60_40');
    expect(onChanged).toHaveBeenCalled();
    confirm.mockRestore();
  });

  it('does not apply when the replace is declined', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPanel('/strategy?stress_event=covid', { hasTargets: true });
    fireEvent.click(await screen.findByRole('button', { name: 'Apply 60/40' }));
    expect(mockApplyStrategy).not.toHaveBeenCalled();
    confirm.mockRestore();
  });

  it('lists missing asset classes once per row, alphabetically by label', async () => {
    mockRunStrategyStress.mockResolvedValue({
      ...RESULT,
      strategies: [
        {
          ...RESULT.strategies[1],
          horizons: {
            '1m': horizon(null, ['property', 'other_commodities']),
            '1y': horizon(null, ['property', 'equity']),
          },
        },
      ],
    });
    renderPanel('/strategy?stress_event=covid');
    expect(
      await screen.findByText(
        'No price history for: Equity, Other commodities, Property'
      )
    ).toBeInTheDocument();
  });

  it('says so once when nothing has data for the event, instead of a table of blanks', async () => {
    mockRunStrategyStress.mockResolvedValue({
      ...RESULT,
      event: { id: '1987-10-19', name: 'Black Monday', date: '1987-10-19' },
      portfolio: {
        baseline_total_value_gbp: 1000,
        horizons: { '1m': horizon(null), '1y': horizon(null) },
      },
      strategies: [RESULT.strategies[1]],
    });
    renderPanel('/strategy?stress_event=1987-10-19');
    expect(await screen.findByRole('note')).toHaveTextContent(
      'stored prices around 1987-10-19'
    );
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('shows the API error', async () => {
    mockRunStrategyStress.mockRejectedValue(
      new Error('HTTP 404 – unknown event')
    );
    renderPanel('/strategy?stress_event=gone');
    expect(
      await screen.findByText('HTTP 404 – unknown event')
    ).toBeInTheDocument();
  });
});
