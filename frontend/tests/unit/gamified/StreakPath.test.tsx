import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import StreakPath from '@/gamified/components/StreakPath';
import { buildStreakPath } from '@/gamified/seasonModel';

describe('StreakPath', () => {
  it('gives an untracked day a different look than a missed one', () => {
    // A tracked day with 0 of 4 done, versus a day the backend has no
    // record for at all. Both used to render as the same blank disc (#7204).
    const days = buildStreakPath(
      {
        '2026-08-20': { completed: 0, total: 4 },
        '2026-08-26': { completed: 4, total: 4 },
      },
      '2026-08-26'
    );
    const { container } = render(<StreakPath days={days} streak={1} />);

    const untrackedStamp = container.querySelector(
      'span[title="2026-08-21: no chores recorded"]'
    );
    const zeroOfFourStamp = container.querySelector(
      'span[title="2026-08-20: 0 of 4 chores done"]'
    );

    expect(untrackedStamp).toBeTruthy();
    expect(zeroOfFourStamp).toBeTruthy();
    // A tracked-but-failed day gets a different class than an untracked one.
    expect(zeroOfFourStamp?.className).not.toBe(untrackedStamp?.className);
  });

  it('renders every day disc as a single labelled stamp, oldest first', () => {
    const days = buildStreakPath(
      { '2026-08-26': { completed: 4, total: 4 } },
      '2026-08-26'
    );
    const { container } = render(<StreakPath days={days} streak={1} />);
    // 7 day discs + 1 crate, each carrying its own title.
    expect(container.querySelectorAll('li span[title]')).toHaveLength(8);

    const untrackedTitles = Array.from(
      container.querySelectorAll('li span[title]')
    )
      .slice(0, 6)
      .map((el) => el.getAttribute('title'));
    expect(
      untrackedTitles.every((title) => title?.endsWith('no chores recorded'))
    ).toBe(true);
  });

  it('frames a first tracked day as progress, not a failed week', () => {
    const days = buildStreakPath(
      { '2026-08-26': { completed: 4, total: 4 } },
      '2026-08-26'
    );
    const { container } = render(<StreakPath days={days} streak={1} />);
    const crateTitle = container
      .querySelector('li:last-child span[title]')
      ?.getAttribute('title');

    expect(crateTitle).toBe('1 day down — keep going to fill the crate');
    expect(crateTitle).not.toMatch(/finish every day/i);
  });

  it('still calls out a genuinely failed full week', () => {
    const totals: Record<string, { completed: number; total: number }> = {};
    for (const date of [
      '2026-08-20',
      '2026-08-21',
      '2026-08-22',
      '2026-08-23',
      '2026-08-24',
      '2026-08-25',
    ]) {
      totals[date] = { completed: 4, total: 4 };
    }
    totals['2026-08-26'] = { completed: 0, total: 4 };
    const days = buildStreakPath(totals, '2026-08-26');
    const { container } = render(<StreakPath days={days} streak={0} />);
    const crateTitle = container
      .querySelector('li:last-child span[title]')
      ?.getAttribute('title');

    expect(crateTitle).toBe('Finish every day this week to fill the crate');
  });

  it('opens the crate for a genuine full week', () => {
    const totals: Record<string, { completed: number; total: number }> = {};
    for (const date of [
      '2026-08-20',
      '2026-08-21',
      '2026-08-22',
      '2026-08-23',
      '2026-08-24',
      '2026-08-25',
      '2026-08-26',
    ]) {
      totals[date] = { completed: 4, total: 4 };
    }
    const days = buildStreakPath(totals, '2026-08-26');
    const { container } = render(<StreakPath days={days} streak={7} />);
    const crateTitle = container
      .querySelector('li:last-child span[title]')
      ?.getAttribute('title');

    expect(crateTitle).toBe('Full week of chores done');
  });

  it('shows a neutral message when nothing at all is tracked', () => {
    const days = buildStreakPath(null, '2026-08-26');
    const { container } = render(<StreakPath days={days} streak={0} />);
    const crateTitle = container
      .querySelector('li:last-child span[title]')
      ?.getAttribute('title');

    expect(crateTitle).toBe('No chores tracked yet this week');
  });
});
