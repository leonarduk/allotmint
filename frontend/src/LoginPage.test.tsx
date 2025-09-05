import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import LoginPage from './LoginPage'

describe.skip('Google login guard', () => {
  it('shows error when client ID missing', async () => {
    vi.mock('./api', async () => {
      const actual = await vi.importActual<typeof import('./api')>('./api')
      return {
        ...actual,
        getConfig: () =>
          Promise.resolve({ google_auth_enabled: true, google_client_id: '' })
      }
    })
    document.body.innerHTML = '<div id="root"></div>'
    const { Root } = await import('./main')
    render(<Root />)
    expect(await screen.findByText(/Google client ID missing/i)).toBeInTheDocument()
    expect(
      await screen.findByText(/client ID missing\. Login is unavailable/i)
    ).toBeInTheDocument()
    render(
      <BrowserRouter>
        <Root />
      </BrowserRouter>,
    )
    expect(
      await screen.findByText(
        /Google client ID missing\. Login is unavailable\./i,
      ),
    ).toBeInTheDocument()
    expect(
      await screen.findByText(/Google login is not configured/i),
    ).toBeInTheDocument()
  })
})

describe.skip('LoginPage error handling', () => {
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

    render(<LoginPage clientId="cid" onSuccess={() => {}} />)

    const script = document.head.querySelector('script[src="https://accounts.google.com/gsi/client"]') as HTMLScriptElement
    script.onload?.(new Event('load'))
    await initialize.mock.results[0].value
    await callback({ credential: 'token' })

    expect(await screen.findByText('bad')).toBeInTheDocument()

    fetchMock.mockRestore()
  })
})
