import { describe, expect, it } from 'vitest';
import { crateState, stampClass } from '@/utils/crateProgress';
import type { StampStyles } from '@/utils/crateProgress';
import { buildStreakPath } from '@/gamified/seasonModel';

const styles: StampStyles = {
  stamp: 'stamp',
  stampDone: 'stampDone',
  stampPartial: 'stampPartial',
  stampMissed: 'stampMissed',
};

describe('stampClass', () => {
  it('marks a fully completed day as done', () => {
    const [day] = buildStreakPath(
      { '2026-08-26': { completed: 4, total: 4 } },
      '2026-08-26',
      1
    );
    expect(stampClass(day, styles)).toBe('stamp stampDone');
  });

  it('marks a partially completed day as partial', () => {
    const [day] = buildStreakPath(
      { '2026-08-26': { completed: 2, total: 4 } },
      '2026-08-26',
      1
    );
    expect(stampClass(day, styles)).toBe('stamp stampPartial');
  });

  it('marks a tracked-but-unfinished day as missed', () => {
    const [day] = buildStreakPath(
      { '2026-08-26': { completed: 0, total: 4 } },
      '2026-08-26',
      1
    );
    expect(stampClass(day, styles)).toBe('stamp stampMissed');
  });

  it('leaves an untracked day as the plain hollow stamp', () => {
    const [day] = buildStreakPath(null, '2026-08-26', 1);
    expect(stampClass(day, styles)).toBe('stamp');
  });
});

describe('crateState', () => {
  it('reports a neutral message when nothing at all is tracked', () => {
    const days = buildStreakPath(null, '2026-08-26');
    expect(crateState(days)).toEqual({
      open: false,
      label: 'No chores tracked yet this week',
    });
  });

  it('frames a first tracked day as progress, not a failed week', () => {
    const days = buildStreakPath(
      { '2026-08-26': { completed: 4, total: 4 } },
      '2026-08-26'
    );
    expect(crateState(days)).toEqual({
      open: false,
      label: '1 of 7 days down — keep going to fill the crate',
    });
  });

  it('counts a day still in progress toward "down", not as a miss', () => {
    const days = buildStreakPath(
      { '2026-08-26': { completed: 2, total: 4 } },
      '2026-08-26'
    );
    expect(crateState(days).label).toBe(
      '1 of 7 days down — keep going to fill the crate'
    );
  });

  it('does not count a genuinely untouched tracked day as "down"', () => {
    const days = buildStreakPath(
      { '2026-08-26': { completed: 0, total: 4 } },
      '2026-08-26'
    );
    expect(crateState(days).label).toBe(
      '0 of 7 days down — keep going to fill the crate'
    );
  });

  it('does not say "Finish every day" for a mixed tracked/untracked week with a miss', () => {
    // 3 tracked days (2 done, 1 missed) + 3 untracked days. The untracked
    // days must not be treated as misses, so the crate stays in the
    // "keep going" state rather than the "Finish every day" failure state.
    const days = buildStreakPath(
      {
        '2026-08-24': { completed: 4, total: 4 },
        '2026-08-25': { completed: 4, total: 4 },
        '2026-08-26': { completed: 0, total: 4 },
      },
      '2026-08-26'
    );
    const state = crateState(days);
    expect(state.open).toBe(false);
    expect(state.label).toBe(
      '2 of 7 days down — keep going to fill the crate'
    );
    expect(state.label).not.toMatch(/finish every day/i);
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
    expect(crateState(days)).toEqual({
      open: false,
      label: 'Finish every day this week to fill the crate',
    });
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
    expect(crateState(days)).toEqual({
      open: true,
      label: 'Full week of chores done',
    });
  });
});
