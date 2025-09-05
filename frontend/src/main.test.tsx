import { describe, it, expect, vi } from 'vitest';

vi.mock('react-dom/client', () => ({
  createRoot: () => ({ render: vi.fn() })
}));

const setAuthToken = vi.fn();
const getStoredAuthToken = vi.fn(() => localStorage.getItem('authToken'));
vi.mock('./api', () => ({
  getConfig: vi.fn().mockResolvedValue({}),
  setAuthToken,
  getStoredAuthToken
}));

// Ensure the main entry point loads without throwing and restores token.
describe('main', () => {
  it('boots the application', async () => {
    localStorage.setItem('authToken', 'persisted');
    document.body.innerHTML = '<div id="root"></div>';
    await import('./main');
    expect(setAuthToken).toHaveBeenCalledWith('persisted');
    expect(document.getElementById('root')).not.toBeNull();
  });
});
