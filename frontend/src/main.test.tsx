import { describe, it, expect, vi } from 'vitest';

vi.mock('react-dom/client', () => ({
  createRoot: () => ({ render: vi.fn() })
}));

// Ensure the main entry point loads without throwing.
describe('main', () => {
  it('boots the application', async () => {
    document.body.innerHTML = '<div id="root"></div>';
    await import('./main');
    expect(document.getElementById('root')).not.toBeNull();
  });
});
