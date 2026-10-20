import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mockGetDataSyncStatus = vi.hoisted(() => vi.fn());
const mockStartDataSync = vi.hoisted(() => vi.fn());

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api');
  return {
    ...actual,
    getDataSyncStatus: mockGetDataSyncStatus,
    startDataSync: mockStartDataSync,
  };
});

import DataSyncSection from '@/components/DataSyncSection';

const configured = {
  configured: true,
  repo: 'leonarduk/allotmint-data',
  pulls_url: 'https://github.com/leonarduk/allotmint-data/pulls',
  runs: {
    pull: {
      status: 'completed',
      conclusion: 'success',
      html_url: 'https://github.com/leonarduk/allotmint-data/actions/runs/1',
      created_at: '2026-10-20T21:00:00Z',
      actor: 'leonarduk',
    },
    push: null,
  },
};

async function renderExpanded() {
  render(<DataSyncSection />);
  const heading = await screen.findByRole('heading', {
    name: 'Data sync with git',
  });
  const trigger = within(heading.parentElement as HTMLElement).getByLabelText(
    'Expand'
  );
  await act(async () => {
    await userEvent.click(trigger);
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('DataSyncSection', () => {
  it('renders nothing for anyone but the owner', async () => {
    mockGetDataSyncStatus.mockRejectedValue(
      Object.assign(new Error('Forbidden'), { status: 403 })
    );
    const { container } = render(<DataSyncSection />);
    await act(async () => {});
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the latest runs and links to them', async () => {
    mockGetDataSyncStatus.mockResolvedValue(configured);
    await renderExpanded();
    expect(screen.getByRole('link', { name: 'success' })).toHaveAttribute(
      'href',
      configured.runs.pull.html_url
    );
    expect(screen.getByText(/Last push: never run/)).toBeInTheDocument();
  });

  it('disables the sync buttons when not configured', async () => {
    mockGetDataSyncStatus.mockResolvedValue({
      configured: false,
      repo: 'leonarduk/allotmint-data',
      runs: {},
    });
    await renderExpanded();
    expect(screen.getByText(/Data sync is not configured/)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Pull from git' })
    ).toBeDisabled();
    expect(
      screen.getByRole('button', { name: 'Push to git (PR)' })
    ).toBeDisabled();
  });

  it('does not pull unless the owner confirms', async () => {
    mockGetDataSyncStatus.mockResolvedValue(configured);
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    await renderExpanded();
    await act(async () => {
      await userEvent.click(
        screen.getByRole('button', { name: 'Pull from git' })
      );
    });
    expect(mockStartDataSync).not.toHaveBeenCalled();
  });

  it('starts a confirmed pull', async () => {
    mockGetDataSyncStatus.mockResolvedValue(configured);
    mockStartDataSync.mockResolvedValue({ dispatched: 'pull' });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    await renderExpanded();
    await act(async () => {
      await userEvent.click(
        screen.getByRole('button', { name: 'Pull from git' })
      );
    });
    expect(mockStartDataSync).toHaveBeenCalledWith('pull');
    expect(screen.getByRole('status')).toHaveTextContent('Pull started');
  });

  it('starts a push without confirming and links to the pull requests', async () => {
    mockGetDataSyncStatus.mockResolvedValue(configured);
    mockStartDataSync.mockResolvedValue({ dispatched: 'push' });
    const confirm = vi.spyOn(window, 'confirm');
    await renderExpanded();
    await act(async () => {
      await userEvent.click(
        screen.getByRole('button', { name: 'Push to git (PR)' })
      );
    });
    expect(confirm).not.toHaveBeenCalled();
    expect(mockStartDataSync).toHaveBeenCalledWith('push');
    expect(
      screen.getByRole('link', { name: 'Open pull requests' })
    ).toHaveAttribute('href', configured.pulls_url);
  });

  it('shows why a sync could not start', async () => {
    mockGetDataSyncStatus.mockResolvedValue(configured);
    mockStartDataSync.mockRejectedValue(
      Object.assign(new Error('A data sync is already running'), {
        status: 409,
      })
    );
    await renderExpanded();
    await act(async () => {
      await userEvent.click(
        screen.getByRole('button', { name: 'Push to git (PR)' })
      );
    });
    expect(screen.getByRole('alert')).toHaveTextContent(
      'A data sync is already running'
    );
  });
});
