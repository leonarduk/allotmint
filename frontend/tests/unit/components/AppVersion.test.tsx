import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import AppVersion from '@/components/AppVersion';
import { UI_VERSION } from '@/appVersion';

describe('AppVersion', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows the UI build version and the API version from /health (#11029)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok', version: 'v0.61.0 (fa1b646)' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<AppVersion />);

    expect(
      await screen.findByText(/API v0\.61\.0 \(fa1b646\)/)
    ).toBeInTheDocument();
    expect(screen.getByTestId('app-version')).toHaveTextContent(
      `UI ${UI_VERSION}`
    );
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/health$/);
  });

  it('shows ? when the backend version cannot be read', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('network down'))
    );

    render(<AppVersion />);

    expect(await screen.findByText(/API \?/)).toBeInTheDocument();
  });
});
