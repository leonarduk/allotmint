import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'

afterEach(() => {
  vi.resetModules()
})

describe('Root login behaviour', () => {
  it('shows error when clientId is missing', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    vi.doMock('./api', () => ({
      getConfig: vi.fn().mockResolvedValue({
        google_auth_enabled: true,
        google_client_id: ''
      })
    }))

    vi.doMock('./LoginPage', () => ({
      default: () => <div data-testid="login-page">login-page</div>
    }))

    document.body.innerHTML = '<div id="root"></div>'
    const { Root } = await import('./main')
    render(<Root />)
    expect(await screen.findByText(/google login is not configured/i)).toBeInTheDocument()
    expect(screen.queryByTestId('login-page')).toBeNull()
  })
})
