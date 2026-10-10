import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { useEffect, useRef } from 'react';
import { Link, MemoryRouter, useLocation } from 'react-router-dom';
// setupTests.ts stubs useNavigate globally; these tests need real navigation
// to check that switching tabs actually moves the router.
vi.mock('react-router-dom', async () =>
  vi.importActual<typeof import('react-router-dom')>('react-router-dom')
);

import WorkspaceTabBar from '../../../src/components/WorkspaceTabBar';
import WorkspaceTabsToggle from '../../../src/components/WorkspaceTabsToggle';
import { CHAT_WINDOW_PATH } from '../../../src/utils/chatWindow';
import {
  RemountOnTabRefresh,
  WorkspaceTabsProvider,
} from '../../../src/WorkspaceTabsContext';
import { readFetchCache, writeFetchCache } from '../../../src/utils/fetchCache';

function CurrentPath() {
  const location = useLocation();
  return (
    <div data-testid="path">{`${location.pathname}${location.search}`}</div>
  );
}

// Counts mounts so the refresh test can tell a remount from a re-render.
const mounts = { count: 0 };
function MountCounter() {
  const counted = useRef(false);
  useEffect(() => {
    if (!counted.current) {
      counted.current = true;
      mounts.count += 1;
    }
  }, []);
  return null;
}

function renderShell(initialPath = '/?group=family') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <WorkspaceTabsProvider>
        <WorkspaceTabBar />
        <WorkspaceTabsToggle />
        <RemountOnTabRefresh>
          <MountCounter />
        </RemountOnTabRefresh>
        <Link to="/research/VWRL.L">go to VWRL</Link>
        <CurrentPath />
      </WorkspaceTabsProvider>
    </MemoryRouter>
  );
}

const path = () => screen.getByTestId('path').textContent;

afterEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
  mounts.count = 0;
});

describe('WorkspaceTabBar', () => {
  it('renders nothing until switched on in settings', () => {
    renderShell();
    expect(screen.queryByRole('navigation')).toBeNull();

    fireEvent.click(screen.getByRole('checkbox'));
    expect(screen.getByRole('navigation')).toBeInTheDocument();
    expect(window.localStorage.getItem('allotmint.workspaceTabs.enabled')).toBe(
      'true'
    );
  });

  it('switches between the group overview and an instrument', () => {
    window.localStorage.setItem('allotmint.workspaceTabs.enabled', 'true');
    renderShell();

    fireEvent.click(screen.getByRole('button', { name: /new tab/i }));
    fireEvent.click(screen.getByText('go to VWRL'));
    expect(path()).toBe('/research/VWRL.L');

    const groupTab = screen.getByRole('button', { name: 'Group: family' });
    fireEvent.click(groupTab);
    expect(path()).toBe('/?group=family');
    expect(groupTab).toHaveAttribute('aria-current', 'page');

    fireEvent.click(screen.getByRole('button', { name: 'VWRL.L' }));
    expect(path()).toBe('/research/VWRL.L');

    // Switching never writes one tab's location into the tab it left.
    const stored = JSON.parse(
      window.sessionStorage.getItem('allotmint.workspaceTabs')!
    );
    expect(stored.tabs.map((t: { path: string }) => t.path)).toEqual([
      '/?group=family',
      '/research/VWRL.L',
    ]);
  });

  it('closing the active tab navigates to its neighbour', () => {
    window.localStorage.setItem('allotmint.workspaceTabs.enabled', 'true');
    renderShell();
    fireEvent.click(screen.getByRole('button', { name: /new tab/i }));
    fireEvent.click(screen.getByText('go to VWRL'));

    fireEvent.click(screen.getByRole('button', { name: /close VWRL\.L/i }));
    expect(path()).toBe('/?group=family');
    expect(screen.queryByRole('button', { name: /close/i })).toBeNull();
  });

  it('refresh clears cached API results and remounts the page', () => {
    window.localStorage.setItem('allotmint.workspaceTabs.enabled', 'true');
    writeFetchCache('portfolio-group/family', { cached: true });
    renderShell();
    expect(mounts.count).toBe(1);

    fireEvent.click(screen.getByRole('button', { name: /refresh/i }));
    expect(readFetchCache('portfolio-group/family')).toBeUndefined();
    expect(mounts.count).toBe(2);
  });

  it('never records the detached chat window as a tab location', () => {
    window.localStorage.setItem('allotmint.workspaceTabs.enabled', 'true');
    window.sessionStorage.setItem(
      'allotmint.workspaceTabs',
      JSON.stringify({
        tabs: [{ id: 't1', path: '/research/VWRL.L' }],
        activeId: 't1',
      })
    );
    renderShell(CHAT_WINDOW_PATH);

    expect(screen.queryByRole('navigation')).toBeNull();
    expect(
      JSON.parse(window.sessionStorage.getItem('allotmint.workspaceTabs')!)
    ).toEqual({
      tabs: [{ id: 't1', path: '/research/VWRL.L' }],
      activeId: 't1',
    });
  });

  it('restores tabs from the session', () => {
    window.localStorage.setItem('allotmint.workspaceTabs.enabled', 'true');
    const { unmount } = renderShell();
    fireEvent.click(screen.getByRole('button', { name: /new tab/i }));
    fireEvent.click(screen.getByText('go to VWRL'));
    unmount();

    renderShell('/research/VWRL.L');
    expect(
      screen.getByRole('button', { name: 'Group: family' })
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'VWRL.L' })).toHaveAttribute(
      'aria-current',
      'page'
    );
  });
});
