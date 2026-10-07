import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { Screener } from '@/pages/Screener';
import * as api from '@/api';
import {
  SAVED_SCREENS_STORAGE_KEY,
  readSavedScreens,
} from '@/lib/savedScreensStore';

vi.mock('@/api');

const mockCheckScreenerAvailable = vi.mocked(api.checkScreenerAvailable);

async function renderReady() {
  render(<Screener />);
  return within(await screen.findByTestId('saved-screens'));
}

function savedSelect() {
  return screen.getByLabelText('Saved screens') as HTMLSelectElement;
}

describe('Screener saved screens', () => {
  beforeEach(() => {
    localStorage.clear();
    mockCheckScreenerAvailable.mockResolvedValue(true);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('saves the current form under a name and reloads it later', async () => {
    const bar = await renderReady();
    fireEvent.change(screen.getByLabelText('Max P/E'), {
      target: { value: '12' },
    });
    vi.spyOn(window, 'prompt').mockReturnValue('  Cheap  ');

    fireEvent.click(bar.getByRole('button', { name: 'Save as…' }));

    expect(readSavedScreens()).toEqual([
      expect.objectContaining({
        name: 'Cheap',
        watchlist: 'FTSE 100',
        filters: expect.objectContaining({ pe_max: '12' }),
      }),
    ]);
    expect(savedSelect().value).toBe('Cheap');

    // Change the form, then pick the saved screen to restore it.
    fireEvent.change(screen.getByLabelText('Max P/E'), {
      target: { value: '40' },
    });
    fireEvent.change(savedSelect(), { target: { value: '' } });
    fireEvent.change(savedSelect(), { target: { value: 'Cheap' } });
    expect((screen.getByLabelText('Max P/E') as HTMLInputElement).value).toBe(
      '12'
    );
  });

  it('updates, renames and deletes the selected screen', async () => {
    localStorage.setItem(
      SAVED_SCREENS_STORAGE_KEY,
      JSON.stringify([
        {
          name: 'Mine',
          watchlist: 'Custom',
          tickers: 'AAA.L',
          filters: { pe_max: '10' },
        },
      ])
    );
    const bar = await renderReady();
    expect(bar.getByRole('button', { name: 'Update' })).toBeDisabled();

    fireEvent.change(savedSelect(), { target: { value: 'Mine' } });
    expect((screen.getByLabelText(/Tickers/i) as HTMLInputElement).value).toBe(
      'AAA.L'
    );

    fireEvent.change(screen.getByLabelText('Max P/E'), {
      target: { value: '15' },
    });
    fireEvent.click(bar.getByRole('button', { name: 'Update' }));
    expect(readSavedScreens()[0].filters.pe_max).toBe('15');

    vi.spyOn(window, 'prompt').mockReturnValue('Renamed');
    fireEvent.click(bar.getByRole('button', { name: 'Rename' }));
    expect(readSavedScreens().map((s) => s.name)).toEqual(['Renamed']);
    expect(savedSelect().value).toBe('Renamed');

    vi.spyOn(window, 'confirm').mockReturnValue(true);
    fireEvent.click(bar.getByRole('button', { name: 'Delete' }));
    expect(readSavedScreens()).toEqual([]);
    expect(savedSelect().value).toBe('');
  });

  it("refuses to rename onto another screen's name", async () => {
    localStorage.setItem(
      SAVED_SCREENS_STORAGE_KEY,
      JSON.stringify([
        { name: 'A', watchlist: 'FTSE 100', tickers: '', filters: {} },
        { name: 'B', watchlist: 'FTSE 100', tickers: '', filters: {} },
      ])
    );
    const bar = await renderReady();
    fireEvent.change(savedSelect(), { target: { value: 'A' } });
    vi.spyOn(window, 'prompt').mockReturnValue('b');
    const alert = vi.spyOn(window, 'alert').mockImplementation(() => {});

    fireEvent.click(bar.getByRole('button', { name: 'Rename' }));

    expect(alert).toHaveBeenCalled();
    expect(readSavedScreens().map((s) => s.name)).toEqual(['A', 'B']);
  });

  it('does not overwrite an existing screen when the user declines', async () => {
    localStorage.setItem(
      SAVED_SCREENS_STORAGE_KEY,
      JSON.stringify([
        {
          name: 'A',
          watchlist: 'FTSE 100',
          tickers: '',
          filters: { pe_max: '1' },
        },
      ])
    );
    const bar = await renderReady();
    vi.spyOn(window, 'prompt').mockReturnValue('a');
    vi.spyOn(window, 'confirm').mockReturnValue(false);

    fireEvent.click(bar.getByRole('button', { name: 'Save as…' }));

    expect(readSavedScreens()).toEqual([
      expect.objectContaining({ name: 'A', filters: { pe_max: '1' } }),
    ]);
  });

  it('ignores corrupt storage', async () => {
    localStorage.setItem(SAVED_SCREENS_STORAGE_KEY, '{not json');
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    await renderReady();
    expect(savedSelect().options).toHaveLength(1);
  });
});
