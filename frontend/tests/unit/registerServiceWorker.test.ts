import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  SERVICE_WORKER_URL,
  registerServiceWorker,
} from '../../src/registerServiceWorker';

function stubServiceWorker(register: ReturnType<typeof vi.fn>) {
  Object.defineProperty(navigator, 'serviceWorker', {
    configurable: true,
    value: { register },
  });
}

describe('registerServiceWorker', () => {
  afterEach(() => {
    delete (navigator as { serviceWorker?: unknown }).serviceWorker;
  });

  it('registers the worker on load in production', () => {
    const register = vi.fn().mockResolvedValue({});
    stubServiceWorker(register);
    registerServiceWorker(true);
    window.dispatchEvent(new Event('load'));
    expect(register).toHaveBeenCalledWith(SERVICE_WORKER_URL);
  });

  it('does nothing outside production', () => {
    const register = vi.fn().mockResolvedValue({});
    stubServiceWorker(register);
    registerServiceWorker(false);
    window.dispatchEvent(new Event('load'));
    expect(register).not.toHaveBeenCalled();
  });

  it('logs registration failures instead of swallowing them', async () => {
    const error = new Error('blocked');
    const register = vi.fn().mockRejectedValue(error);
    const consoleError = vi
      .spyOn(console, 'error')
      .mockImplementation(() => {});
    stubServiceWorker(register);
    registerServiceWorker(true);
    window.dispatchEvent(new Event('load'));
    await vi.waitFor(() =>
      expect(consoleError).toHaveBeenCalledWith(
        'Service worker registration failed:',
        error
      )
    );
  });
});
