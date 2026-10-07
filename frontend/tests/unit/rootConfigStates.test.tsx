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

  it('stops retrying and names the unreachable server once attempts run out (#7788)', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.useFakeTimers({ shouldAdvanceTime: true })

    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    const getConfig = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return { ...mod, getConfig, getStoredAuthToken: vi.fn() }
    })

    document.body.innerHTML = '<div id="root"></div>'
    const { Root } = await import('@/main')
    const { API_BASE } = await import('@/api')

    try {
      render(
        <BrowserRouter>
          <Root />
        </BrowserRouter>,
      )

      // Backoff is 2s, 4s, 8s, 16s between the five attempts.
      await vi.advanceTimersByTimeAsync(60_000)

      const alert = await screen.findByRole('alert')
      expect(alert).toHaveTextContent(
        `Can't reach the AllotMint server at ${API_BASE}.`,
      )
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
      const attempts = getConfig.mock.calls.length
      expect(attempts).toBe(5)

      // No further retries are scheduled once the cap is hit.
      await vi.advanceTimersByTimeAsync(120_000)
      expect(getConfig).toHaveBeenCalledTimes(attempts)
    } finally {
      vi.useRealTimers()
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
        getConfig: vi.fn((_?: RequestInit) =>
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
