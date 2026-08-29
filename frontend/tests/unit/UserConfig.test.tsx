import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import UserConfigPage from '@/pages/UserConfig';
import { AuthContext } from '@/AuthContext';

// #7206: UserConfig.tsx renders an empty-owner prompt, per-field helper
// text, and an Approvals empty state -- all of which previously either
// didn't exist or rendered nothing. These tests cover the new copy and the
// conditions under which it appears, without changing owner-resolution
// behaviour (still driven by getOwners + findOwnerForUser).
const {
  getOwnersMock,
  getUserConfigMock,
  updateUserConfigMock,
  getApprovalsMock,
  addApprovalMock,
  removeApprovalMock,
} = vi.hoisted(() => ({
  getOwnersMock: vi.fn(() =>
    Promise.resolve([
      { owner: 'alex', full_name: 'Alex Example', accounts: ['isa'] },
      { owner: 'sam', full_name: 'Sam Example', accounts: ['sipp'] },
    ])
  ),
  getUserConfigMock: vi.fn(() => Promise.resolve({})),
  updateUserConfigMock: vi.fn(() => Promise.resolve({})),
  getApprovalsMock: vi.fn(() => Promise.resolve({ approvals: [] })),
  addApprovalMock: vi.fn(() => Promise.resolve({ approvals: [] })),
  removeApprovalMock: vi.fn(() => Promise.resolve({ approvals: [] })),
}));

vi.mock('@/api', () => ({
  getOwners: getOwnersMock,
  getUserConfig: getUserConfigMock,
  updateUserConfig: updateUserConfigMock,
  getApprovals: getApprovalsMock,
  addApproval: addApprovalMock,
  removeApproval: removeApprovalMock,
}));

describe('UserConfigPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getOwnersMock.mockResolvedValue([
      { owner: 'alex', full_name: 'Alex Example', accounts: ['isa'] },
      { owner: 'sam', full_name: 'Sam Example', accounts: ['sipp'] },
    ]);
    getApprovalsMock.mockResolvedValue({ approvals: [] });
    getUserConfigMock.mockResolvedValue({});
  });

  it('shows an explicit prompt instead of a blank page when no owner is resolved', async () => {
    // No AuthContext user and no selectedOwner prop means findOwnerForUser
    // has nothing to match, so `owner` stays '' -- the exact blank-page
    // condition described in #7206.
    render(<UserConfigPage />);

    expect(
      await screen.findByText('Choose whose settings to edit.')
    ).toBeInTheDocument();
    // The trading-rules form must not render until an owner is chosen.
    expect(screen.queryByText('Min Hold Days')).not.toBeInTheDocument();
  });

  it('does not show the prompt once an owner is selected', async () => {
    const user = userEvent.setup();
    render(<UserConfigPage />);

    await screen.findByText('Choose whose settings to edit.');
    await user.selectOptions(screen.getByRole('combobox'), 'alex');

    await waitFor(() =>
      expect(
        screen.queryByText('Choose whose settings to edit.')
      ).not.toBeInTheDocument()
    );
    expect(await screen.findByText('Min Hold Days')).toBeInTheDocument();
  });

  it('resolves the owner automatically when selectedOwner matches, still showing helper text', async () => {
    render(<UserConfigPage selectedOwner="sam" />);

    expect(await screen.findByText('Min Hold Days')).toBeInTheDocument();
    expect(
      screen.getByText(
        'The number of days a holding must be kept before it can be sold. Measured in calendar days.'
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'The most trades this account can make in a calendar month. Once reached, further trades need approval.'
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Comma-separated tickers that can always be traded without needing an approval.'
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Comma-separated instrument types (e.g. ETF, Fund) that can always be traded without needing an approval.'
      )
    ).toBeInTheDocument();
  });

  it('still resolves the owner from the logged-in user via findOwnerForUser (multi-owner household case preserved)', async () => {
    getOwnersMock.mockResolvedValue([
      { owner: 'alex', full_name: 'Alex Example', accounts: ['isa'] },
      {
        owner: 'sam',
        full_name: 'Sam Example',
        accounts: ['sipp'],
        email: 'sam@example.com',
      },
    ]);

    render(
      <AuthContext.Provider
        value={{
          user: { email: 'sam@example.com' },
          setUser: vi.fn(),
          logout: null,
          setLogout: vi.fn(),
        }}
      >
        <UserConfigPage />
      </AuthContext.Provider>
    );

    // Owner selection is not locked to a single owner -- the select still
    // renders and can be changed, matching the #7206 constraint that
    // multi-owner households must keep working.
    expect(await screen.findByRole('combobox')).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole('combobox')).toHaveValue('sam')
    );
  });

  it('shows an empty state for the Approvals table instead of a bare header', async () => {
    render(<UserConfigPage selectedOwner="alex" />);

    expect(
      await screen.findByText(
        'No approvals yet. Add one below if a trade needs to go ahead outside the rules above.'
      )
    ).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('renders the Approvals table once an approval exists, and drops the empty state', async () => {
    getApprovalsMock.mockResolvedValue({
      approvals: [{ ticker: 'VUSA.L', approved_on: '2024-01-01' }],
    });

    render(<UserConfigPage selectedOwner="alex" />);

    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(screen.getByText('VUSA.L')).toBeInTheDocument();
    expect(
      screen.queryByText(
        'No approvals yet. Add one below if a trade needs to go ahead outside the rules above.'
      )
    ).not.toBeInTheDocument();
  });

  it('preserves the 403 approvals error message', async () => {
    getApprovalsMock.mockRejectedValue({ status: 403 });

    render(<UserConfigPage selectedOwner="alex" />);

    expect(
      await screen.findByText(
        "You don't have permission to view or manage approvals for this account."
      )
    ).toBeInTheDocument();
  });

  it('uses the page heading "Trading Rules" rather than "User Settings"', async () => {
    render(<UserConfigPage selectedOwner="alex" />);

    expect(
      await screen.findByRole('heading', { name: 'Trading Rules' })
    ).toBeInTheDocument();
  });
});
