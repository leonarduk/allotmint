import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  AUTH_USER_STORAGE_KEY,
  USER_PROFILE_STORAGE_KEY,
} from '@/authStorage'

afterEach(() => {
  localStorage.clear()
  vi.resetModules()
})

describe('Root login behaviour', () => {
  it('shows error when clientId is missing', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          google_auth_enabled: true,
          google_client_id: ''
        }),
        getStoredAuthToken: vi.fn()
      }
    })

    vi.doMock('@/LoginPage', () => ({
      default: () => <div data-testid="login-page">login-page</div>
    }))

    document.body.innerHTML = '<div id="root"></div>'
    const { Root } = await import('@/main')
    render(
      <BrowserRouter>
        <Root />
      </BrowserRouter>,
    )
    expect(await screen.findByText(/google login is not configured/i)).toBeInTheDocument()
    expect(screen.queryByTestId('login-page')).toBeNull()
  })

  it('skips the login screen when an auth token already exists', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          google_auth_enabled: true,
          google_client_id: 'mock-client'
        }),
        getStoredAuthToken: vi.fn(() => 'persisted-token')
      }
    })

    const loginRender = vi.fn(() => <div data-testid="login-page">login</div>)
    vi.doMock('@/LoginPage', () => ({
      default: loginRender
    }))

    vi.doMock('@/App.tsx', () => ({
      default: () => <div data-testid="app-shell">app-shell</div>
    }))

    localStorage.setItem(
      AUTH_USER_STORAGE_KEY,
      JSON.stringify({ email: 'user@example.com' })
    )
    localStorage.setItem(
      USER_PROFILE_STORAGE_KEY,
      JSON.stringify({ email: 'user@example.com' })
    )

    document.body.innerHTML = '<div id="root"></div>'
    const { Root } = await import('@/main')
    render(
      <BrowserRouter>
        <Root />
      </BrowserRouter>,
    )

    expect(await screen.findByTestId('app-shell')).toBeInTheDocument()
    expect(loginRender).not.toHaveBeenCalled()
  })
})
