import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.resetModules()
  vi.clearAllMocks()
})

describe('Root configuration states', () => {
  it('shows a loading indicator while configuration is pending', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    const pending = new Promise(() => {})

    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return {
        ...mod,
        getConfig: vi.fn(() => pending),
        getStoredAuthToken: vi.fn()
      }
    })

    document.body.innerHTML = '<div id="root"></div>'
    const { Root } = await import('@/main')

    render(
      <BrowserRouter>
        <Root />
      </BrowserRouter>,
    )

    const status = screen.getByRole('status')
    expect(status).toHaveTextContent(/loading application/i)
  })

  it('renders an offline message when configuration fails', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    const networkError = new Error('Network unreachable')

    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return {
        ...mod,
        getConfig: vi.fn().mockRejectedValue(networkError),
        getStoredAuthToken: vi.fn()
      }
    })

    document.body.innerHTML = '<div id="root"></div>'
    const { Root } = await import('@/main')

    render(
      <BrowserRouter>
        <Root />
      </BrowserRouter>,
    )

    expect(
      await screen.findByText(/couldn't load the application configuration/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/network unreachable/i)).toBeInTheDocument()
  })
})

