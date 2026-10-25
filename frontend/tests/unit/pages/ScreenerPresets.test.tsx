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
import { readSavedScreens } from '@/lib/savedScreensStore';
import { SCREEN_PRESETS } from '@/lib/screenerPresets';

vi.mock('@/api');

async function renderReady() {
  render(<Screener />);
  return within(await screen.findByTestId('screen-presets'));
}

function presetButton(name: string) {
  return within(screen.getByRole('group', { name: 'Presets' })).getByRole(
    'button',
    { name }
  );
}

describe('Screener presets', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(api.checkScreenerAvailable).mockResolvedValue("available");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows a button for every preset above the form', async () => {
    const presets = await renderReady();
    expect(presets.getAllByRole('button').map((b) => b.textContent)).toEqual(
      SCREEN_PRESETS.map((p) => p.name)
    );
  });

  it('fills the form without running, and marks the preset active', async () => {
    const presets = await renderReady();
    const preset = SCREEN_PRESETS.find((p) => p.id === 'deep-value')!;

    fireEvent.click(presetButton(preset.name));

    expect(api.getScreener).not.toHaveBeenCalled();
    expect((screen.getByLabelText('Max P/E') as HTMLInputElement).value).toBe(
      preset.filters.pe_max
    );
    expect(presetButton(preset.name)).toHaveAttribute('aria-pressed', 'true');
    expect(presets.getByTestId('preset-description')).toHaveTextContent(
      preset.description
    );
  });

  it('deselects the preset once the user edits a filter', async () => {
    const presets = await renderReady();
    const preset = SCREEN_PRESETS.find((p) => p.id === 'deep-value')!;
    fireEvent.click(presetButton(preset.name));

    fireEvent.change(screen.getByLabelText('Max P/E'), {
      target: { value: '15' },
    });

    expect(presetButton(preset.name)).toHaveAttribute('aria-pressed', 'false');
    expect(presets.queryByTestId('preset-description')).toBeNull();
  });

  it('offers the preset name when forking it with Save as…', async () => {
    await renderReady();
    const preset = SCREEN_PRESETS.find((p) => p.id === 'income')!;
    fireEvent.click(presetButton(preset.name));

    const prompt = vi.spyOn(window, 'prompt').mockReturnValue('My income');
    fireEvent.click(screen.getByRole('button', { name: 'Save as…' }));

    expect(prompt).toHaveBeenCalledWith(expect.any(String), preset.name);
    expect(readSavedScreens()).toEqual([
      expect.objectContaining({
        name: 'My income',
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
      fireEvent.click(presetButton(preset.name));

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
