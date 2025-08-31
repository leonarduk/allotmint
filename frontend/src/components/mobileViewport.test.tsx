import { render } from '@testing-library/react'
import { describe, it, beforeEach, expect } from 'vitest'
import { PortfolioView } from './PortfolioView'
import { AccountBlock } from './AccountBlock'
import { HoldingsTable } from './HoldingsTable'
import type { Portfolio, Account, Holding } from '../types'

const holding: Holding = {
  ticker: 'AAA',
  name: 'AAA Ltd',
  units: 1,
  acquired_date: '2024-01-01',
  market_value_gbp: 100,
}

const account: Account = {
  account_type: 'Test',
  currency: 'GBP',
  value_estimate_gbp: 100,
  holdings: [holding],
}

const portfolio: Portfolio = {
  owner: 'tester',
  as_of: '2024-01-01',
  trades_this_month: 0,
  trades_remaining: 0,
  total_value_estimate_gbp: 100,
  accounts: [account],
}

describe('mobile viewport rendering', () => {
  beforeEach(() => {
    window.innerWidth = 500
    window.dispatchEvent(new Event('resize'))
  })

  it('applies spacing classes in PortfolioView', () => {
    const { container } = render(<PortfolioView data={portfolio} />)
    expect(container.querySelector('.mt-0')).not.toBeNull()
  })

  it('wraps AccountBlock content', () => {
    const { container } = render(<AccountBlock account={account} />)
    expect(container.querySelector('.account-block')).not.toBeNull()
  })

  it('renders HoldingsTable in responsive wrapper', () => {
    const { container } = render(<HoldingsTable holdings={account.holdings} />)
    expect(container.querySelector('.table-responsive')).not.toBeNull()
  })
})
