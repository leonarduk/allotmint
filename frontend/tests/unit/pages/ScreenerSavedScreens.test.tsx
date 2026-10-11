import {
  render,
  screen,
  fireEvent,
  within,
  waitFor,
} from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { Screener } from '@/pages/Screener';
import * as api from '@/api';
import {
  SAVED_SCREENS_STORAGE_KEY,
  readSavedScreens,
} from '@/lib/savedScreensStore';
import { PRESET_VALUE_PREFIX, SCREEN_PRESETS } from '@/lib/screenerPresets';

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
    const mine = savedSelect().querySelector('optgroup[label="My screens"]');
    expect(mine?.querySelectorAll('option:not([disabled])')).toHaveLength(0);
  });

  it('lists every preset by name', async () => {
    await renderReady();
    const group = savedSelect().querySelector('optgroup[label="Presets"]');
    expect(
      Array.from(group?.querySelectorAll('option') ?? [], (o) => o.textContent)
    ).toEqual(SCREEN_PRESETS.map((p) => p.name));
  });

  it('loads a preset read-only and lets the user fork it', async () => {
    const bar = await renderReady();
    const preset = SCREEN_PRESETS.find((p) => p.id === 'deep-value')!;

    fireEvent.change(savedSelect(), {
      target: { value: PRESET_VALUE_PREFIX + 'deep-value' },
    });
    // Loading only fills the form; nothing runs until the user clicks Run.
    expect(api.getScreener).not.toHaveBeenCalled();

    expect((screen.getByLabelText('Max P/E') as HTMLInputElement).value).toBe(
      preset.filters.pe_max
    );
    expect(bar.getByTestId('preset-description')).toHaveTextContent(
      preset.description
    );
    expect(bar.getByRole('button', { name: 'Update' })).toBeDisabled();
    expect(bar.getByRole('button', { name: 'Delete' })).toBeDisabled();

    const prompt = vi.spyOn(window, 'prompt').mockReturnValue('My value');
    fireEvent.click(bar.getByRole('button', { name: 'Save as…' }));
    expect(prompt).toHaveBeenCalledWith(expect.any(String), preset.name);
    expect(readSavedScreens()).toEqual([
      expect.objectContaining({
        name: 'My value',
        watchlist: preset.watchlist,
        filters: expect.objectContaining(preset.filters),
      }),
    ]);
  });

  it.each(SCREEN_PRESETS.map((p) => [p.name, p] as const))(
    'preset "%s" sends every one of its filters to the backend',
    async (_name, preset) => {
      vi.mocked(api.getScreener).mockResolvedValue([]);
      vi.mocked(api.getScreenerRiskReturn).mockRejectedValue(
        Object.assign(new Error('unavailable'), { status: 402 })
      );
      await renderReady();
      fireEvent.change(savedSelect(), {
        target: { value: PRESET_VALUE_PREFIX + preset.id },
      });

      fireEvent.click(screen.getByRole('button', { name: /run/i }));

      const expected = Object.fromEntries(
        Object.entries(preset.filters).map(([k, v]) => [k, Number(v)])
      );
      await waitFor(() =>
        expect(api.getScreener).toHaveBeenCalledWith(
          expect.any(Array),
          expected
        )
      );
    }
  );
});
