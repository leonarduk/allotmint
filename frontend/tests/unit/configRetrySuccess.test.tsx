import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.resetModules()
  vi.clearAllMocks()
  localStorage.clear()
})

describe('Root config retry flow', () => {
  it('recovers from a transient failure and renders the route marker', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    const nativeSetTimeout = window.setTimeout
    const nativeClearTimeout = window.clearTimeout

    const setTimeoutSpy = vi
      .spyOn(window, 'setTimeout')
      .mockImplementation(((callback: TimerHandler, delay?: number, ...args: unknown[]) => {
        if (typeof callback === 'function' && delay === 2000) {
          callback(...args)
          return 0 as unknown as ReturnType<typeof window.setTimeout>
        }
        return nativeSetTimeout(callback as TimerHandler, (delay ?? 0) as number, ...(args as []))
      }) as typeof window.setTimeout)

    const clearTimeoutSpy = vi
      .spyOn(window, 'clearTimeout')
      .mockImplementation(((handle?: number) => {
        if (handle === 0) return
        nativeClearTimeout(handle as number)
      }) as typeof window.clearTimeout)

    try {
      vi.doMock('react-dom/client', () => ({
        createRoot: () => ({ render: vi.fn() })
      }))

      const getConfig = vi
        .fn()
        .mockRejectedValueOnce(new Error('network down'))
        .mockResolvedValue({ google_auth_enabled: false, google_client_id: '' })

      vi.doMock('@/api', async importOriginal => {
        const mod = await importOriginal<typeof import('@/api')>()
        return {
          ...mod,
          getConfig,
          getStoredAuthToken: vi.fn()
        }
      })

      vi.doMock('@/App.tsx', () => ({
        default: () => (
          <div
            data-testid="active-route-marker"
            data-mode="group"
            data-pathname="/"
          >
            App Loaded
          </div>
        )
      }))

      document.body.innerHTML = '<div id="root"></div>'
      const { Root } = await import('@/main')

      render(
        <BrowserRouter>
          <Root />
        </BrowserRouter>,
      )

      await waitFor(() => expect(getConfig).toHaveBeenCalledTimes(2))

      const marker = await screen.findByTestId('active-route-marker')
      expect(marker).toHaveAttribute('data-mode', 'group')
      expect(marker).toHaveAttribute('data-pathname', '/')
    } finally {
      setTimeoutSpy.mockRestore()
      clearTimeoutSpy.mockRestore()
      consoleError.mockRestore()
    }
  })
})
