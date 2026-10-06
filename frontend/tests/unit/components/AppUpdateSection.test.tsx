import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockGetAppUpdateStatus = vi.hoisted(() => vi.fn());
const mockApplyAppUpdate = vi.hoisted(() => vi.fn());

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api');
  return {
    ...actual,
    getAppUpdateStatus: mockGetAppUpdateStatus,
    applyAppUpdate: mockApplyAppUpdate,
  };
});

import AppUpdateSection from '@/components/AppUpdateSection';

const behindStatus = {
  can_update: true,
  reason: null,
  branch: 'main',
  upstream: 'origin/main',
  current_commit: 'aaaaaaa1111',
  upstream_commit: 'bbbbbbb2222',
  behind: 2,
  ahead: 0,
  dirty: false,
};

async function renderExpanded() {
  render(<AppUpdateSection />);
  const heading = await screen.findByRole('heading', { name: 'Update app' });
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

describe('AppUpdateSection', () => {
  it('renders nothing when the backend has no update route (AWS)', async () => {
    mockGetAppUpdateStatus.mockRejectedValue(
      Object.assign(new Error('Not Found'), { status: 404 })
    );
    const { container } = render(<AppUpdateSection />);
    await act(async () => {});
    expect(mockGetAppUpdateStatus).toHaveBeenCalledWith(false);
    expect(container).toBeEmptyDOMElement();
  });

  it('disables Update now when the checkout cannot be fast-forwarded', async () => {
    mockGetAppUpdateStatus.mockResolvedValue({
      ...behindStatus,
      can_update: false,
      dirty: true,
      reason: 'Working tree has uncommitted changes',
    });
    await renderExpanded();
    expect(
      screen.getByText('Working tree has uncommitted changes')
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Update now' })).toBeDisabled();
  });

  it('checks the remote and applies an update', async () => {
    mockGetAppUpdateStatus.mockResolvedValue(behindStatus);
    mockApplyAppUpdate.mockResolvedValue({
      updated: true,
      previous_commit: 'aaaaaaa1111',
      current_commit: 'bbbbbbb2222',
      changed_files: ['backend/foo.py', 'requirements.txt'],
      dependencies_changed: ['requirements.txt'],
      backend_changed: true,
      frontend_changed: false,
    });
    await renderExpanded();
    expect(screen.getByText('2 new commit(s) available.')).toBeInTheDocument();

    await act(async () => {
      await userEvent.click(
        screen.getByRole('button', { name: 'Check for updates' })
      );
    });
    expect(mockGetAppUpdateStatus).toHaveBeenLastCalledWith(true);

    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: 'Update now' }));
    });
    expect(mockApplyAppUpdate).toHaveBeenCalledTimes(1);
    expect(
      screen.getByText(/Updated aaaaaaa → bbbbbbb \(2 file\(s\) changed\)/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Dependencies changed \(requirements.txt\)/)
    ).toBeInTheDocument();
  });

  it("shows the backend's refusal message when the update fails", async () => {
    mockGetAppUpdateStatus.mockResolvedValue(behindStatus);
    mockApplyAppUpdate.mockRejectedValue(
      Object.assign(new Error('An update is already in progress.'), {
        status: 409,
      })
    );
    await renderExpanded();
    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: 'Update now' }));
    });
    expect(screen.getByRole('alert')).toHaveTextContent(
      'An update is already in progress.'
    );
  });

  it('explains a missing response as a possible backend restart', async () => {
    mockGetAppUpdateStatus.mockResolvedValue(behindStatus);
    mockApplyAppUpdate.mockRejectedValue(new TypeError('Failed to fetch'));
    await renderExpanded();
    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: 'Update now' }));
    });
    expect(screen.getByRole('alert')).toHaveTextContent(
      /Failed to fetch.*may have restarted/
    );
  });
});
