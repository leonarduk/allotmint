import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

describe('Google login guard', () => {
  it('shows error when client ID missing', async () => {
    vi.mock('./api', () => ({
      getConfig: () => Promise.resolve({ google_auth_enabled: true, google_client_id: '' })
    }))
    document.body.innerHTML = '<div id="root"></div>'
    const { Root } = await import('./main')
    render(<Root />)
    expect(await screen.findByText(/Google login is not configured/i)).toBeInTheDocument()
  })
})
