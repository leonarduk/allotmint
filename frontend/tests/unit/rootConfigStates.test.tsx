import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.resetModules()
  vi.clearAllMocks()
  localStorage.clear()
})

describe('Root config states', () => {
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

    const { unmount } = render(
      <BrowserRouter>
        <Root />
      </BrowserRouter>,
    )

    expect(screen.getByText(/loading configuration/i)).toBeInTheDocument()
    unmount()
  })

  it('keeps the loading state visible while configuration retries after a failure', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return {
        ...mod,
        getConfig: vi.fn().mockRejectedValue(new Error('network error')),
        getStoredAuthToken: vi.fn()
      }
    })

    document.body.innerHTML = '<div id="root"></div>'
    const { Root } = await import('@/main')

    try {
      render(
        <BrowserRouter>
          <Root />
        </BrowserRouter>,
      )

      expect(
        await screen.findByText(/loading\.\.\./i),
      ).toBeInTheDocument()
    } finally {
      consoleError.mockRestore()
    }
  })

  it('keeps the loading state visible while configuration retries after a timeout', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return {
        ...mod,
        getConfig: vi.fn((_init?: RequestInit) =>
          Promise.reject(new DOMException('Aborted', 'AbortError'))
        ),
        getStoredAuthToken: vi.fn()
      }
    })

    document.body.innerHTML = '<div id="root"></div>'
    const { Root } = await import('@/main')

    try {
      render(
        <BrowserRouter>
          <Root />
        </BrowserRouter>,
      )

      expect(
        await screen.findByText(/loading\.\.\./i),
      ).toBeInTheDocument()
    } finally {
      consoleError.mockRestore()
    }
  })
})
