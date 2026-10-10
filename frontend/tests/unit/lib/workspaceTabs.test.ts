import { afterEach, describe, expect, it } from 'vitest';
import {
  MAX_WORKSPACE_TABS,
  closeTab,
  createInitialState,
  describeTabPath,
  loadTabsEnabled,
  loadTabsState,
  openTab,
  saveTabsEnabled,
  saveTabsState,
  selectTab,
  syncActivePath,
} from '../../../src/lib/workspaceTabs';

afterEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
});

describe('workspace tab state', () => {
  it('opens a new tab right of the active one and activates it', () => {
    let state = createInitialState('/?group=family');
    state = openTab(state, '/research/VWRL.L');
    state = selectTab(state, 't1');
    state = openTab(state, '/research/AIGE.L');

    expect(state.tabs.map((t) => t.path)).toEqual([
      '/?group=family',
      '/research/AIGE.L',
      '/research/VWRL.L',
    ]);
    expect(state.activeId).toBe('t3');
  });

  it('stops opening tabs at the limit', () => {
    let state = createInitialState('/');
    for (let i = 0; i < MAX_WORKSPACE_TABS + 3; i += 1) {
      state = openTab(state, `/research/T${i}`);
    }
    expect(state.tabs).toHaveLength(MAX_WORKSPACE_TABS);
  });

  it('follows the router location in the active tab only', () => {
    let state = openTab(createInitialState('/?group=family'), '/movers');
    state = syncActivePath(state, '/research/VWRL.L');
    expect(state.tabs.map((t) => t.path)).toEqual([
      '/?group=family',
      '/research/VWRL.L',
    ]);
    expect(syncActivePath(state, '/research/VWRL.L')).toBe(state);
  });

  it('never closes the last tab', () => {
    const state = createInitialState('/');
    expect(closeTab(state, 't1')).toBe(state);
  });

  it('activates the right neighbour, else the left, when closing the active tab', () => {
    let state = createInitialState('/a');
    state = openTab(state, '/b');
    state = openTab(state, '/c');
    state = selectTab(state, 't2');

    const middleClosed = closeTab(state, 't2');
    expect(middleClosed.activeId).toBe('t3');

    const lastClosed = closeTab(selectTab(state, 't3'), 't3');
    expect(lastClosed.activeId).toBe('t2');
  });

  it('keeps the active tab when closing a background one', () => {
    let state = openTab(createInitialState('/a'), '/b');
    state = closeTab(state, 't1');
    expect(state).toEqual({ tabs: [{ id: 't2', path: '/b' }], activeId: 't2' });
  });
});

describe('workspace tab storage', () => {
  it('round-trips tabs through sessionStorage', () => {
    const state = openTab(createInitialState('/?group=family'), '/research/X');
    saveTabsState(state);
    expect(loadTabsState('/elsewhere')).toEqual(state);
  });

  it('falls back to a single tab for missing or malformed state', () => {
    expect(loadTabsState('/x')).toEqual(createInitialState('/x'));
    window.sessionStorage.setItem('allotmint.workspaceTabs', '{"tabs":[]}');
    expect(loadTabsState('/x')).toEqual(createInitialState('/x'));
    window.sessionStorage.setItem(
      'allotmint.workspaceTabs',
      JSON.stringify({
        tabs: [
          { id: 't1', path: '/a' },
          { id: 't1', path: '/b' },
        ],
        activeId: 't1',
      })
    );
    expect(loadTabsState('/x')).toEqual(createInitialState('/x'));
    window.sessionStorage.setItem('allotmint.workspaceTabs', 'not json');
    expect(loadTabsState('/x')).toEqual(createInitialState('/x'));
  });

  it('is off by default and remembers the preference', () => {
    expect(loadTabsEnabled()).toBe(false);
    saveTabsEnabled(true);
    expect(loadTabsEnabled()).toBe(true);
  });
});

describe('describeTabPath', () => {
  it('names instruments, groups and other pages', () => {
    expect(describeTabPath('/research/VWRL.L')).toEqual({
      kind: 'instrument',
      ticker: 'VWRL.L',
    });
    expect(describeTabPath('/research/USDGBP.FX?range=1y')).toEqual({
      kind: 'instrument',
      ticker: 'USDGBP.FX',
    });
    expect(describeTabPath('/?group=family')).toEqual({
      kind: 'group',
      group: 'family',
    });
    expect(describeTabPath('/movers')).toEqual({
      kind: 'page',
      pathname: '/movers',
    });
  });
});
