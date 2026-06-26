import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import LoginPage from '@/LoginPage'
import type { AwsUiAuthConfig } from '@/awsUiAuth'

vi.mock('@/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api')>()
  return {
    ...actual,
    getConfig: () =>
      Promise.resolve({ google_auth_enabled: true, google_client_id: '' })
  }
})

describe('Google login guard', () => {
  it('shows error when client ID missing', async () => {
    document.body.innerHTML = '<div id="root"></div>'
    const { Root } = await import('@/main')
    render(
      <BrowserRouter>
        <Root />
      </BrowserRouter>,
    )
    expect(
      await screen.findByText(/Google login is not configured/i),
    ).toBeInTheDocument()
  })
})

describe('LoginPage error handling', () => {
  it('shows error message when login fails', async () => {
    const initialize = vi.fn()
    ;(window as any).google = { accounts: { id: { initialize, renderButton: vi.fn() } } }
    let callback!: (resp: { credential: string }) => Promise<void> | void
    initialize.mockImplementation((opts: { callback: typeof callback }) => {
      callback = opts.callback
      return Promise.resolve()
    })

    const fetchMock = vi
      .spyOn(global, 'fetch')
      .mockResolvedValue({
        ok: false,
        json: async () => ({ detail: 'bad' })
      } as any)

    render(
      <BrowserRouter>
        <LoginPage clientId="cid" onSuccess={() => {}} />
      </BrowserRouter>,
    )

    const script = document.head.querySelector('script[src="https://accounts.google.com/gsi/client"]') as HTMLScriptElement
    script.onload?.(new Event('load'))
    await initialize.mock.results[0].value
    await callback({ credential: 'token' })

    expect(await screen.findByText(/bad/)).toBeInTheDocument()

    fetchMock.mockRestore()
  })
})

describe('LoginPage awsUiAuth mode', () => {
  it('shows only the Cognito sign-in button when awsUiAuth.enabled is true', () => {
    const awsUiAuth: AwsUiAuthConfig = { enabled: true, clientId: 'test-pool-client' }

    render(
      <BrowserRouter>
        <LoginPage clientId="" awsUiAuth={awsUiAuth} onSuccess={() => {}} />
      </BrowserRouter>,
    )

    // Cognito sign-in button must be present
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()

    // Google GIS script must NOT be injected
    expect(
      document.head.querySelector('script[src="https://accounts.google.com/gsi/client"]'),
    ).toBeNull()

    // Google sign-in container must NOT be rendered
    expect(document.getElementById('google-signin')).toBeNull()
  })

  it('shows only the Google sign-in container when awsUiAuth is not enabled', () => {
    render(
      <BrowserRouter>
        <LoginPage clientId="google-cid" onSuccess={() => {}} />
      </BrowserRouter>,
    )

    // Google sign-in container must be present
    expect(document.getElementById('google-signin')).toBeInTheDocument()

    // Cognito sign-in button must NOT be rendered
    expect(screen.queryByRole('button', { name: /sign in/i })).toBeNull()
  })
})
