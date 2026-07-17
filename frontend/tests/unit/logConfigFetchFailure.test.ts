import { afterEach, describe, expect, it, vi } from 'vitest'
import { logConfigFetchFailure } from '@/configFetchLogging'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('logConfigFetchFailure', () => {
  it('logs at warn when a retry is scheduled', () => {
    const consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const err = new Error('network down')

    logConfigFetchFailure(err, true)

    expect(consoleWarn).toHaveBeenCalledWith(
      'Failed to load configuration, retrying',
      err,
    )
    expect(consoleError).not.toHaveBeenCalled()
  })

  it('logs at error once retries are exhausted', () => {
    const consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const err = new Error('network down')

    logConfigFetchFailure(err, false)

    expect(consoleError).toHaveBeenCalledWith('Failed to load configuration', err)
    expect(consoleWarn).not.toHaveBeenCalled()
  })
})
