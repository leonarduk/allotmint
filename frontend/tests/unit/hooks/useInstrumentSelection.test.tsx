import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  WorkspaceTabsContext,
  type WorkspaceTabsContextValue,
} from '../../../src/contexts/workspaceTabs';
import { useInstrumentSelection } from '../../../src/hooks/useInstrumentSelection';

// setupTests.ts replaces useNavigate with one shared mock; read it from the
// hook so the test sees the same function the hook under test calls.
function useSelectionAndNavigate() {
  return { ...useInstrumentSelection(), navigate: vi.mocked(useNavigate()) };
}

function wrapperWithTabs(enabled: boolean) {
  const value = {
    enabled,
    setEnabled: () => {},
    tabs: [],
    activeId: '',
    openCurrentInNewTab: () => {},
    selectTab: () => {},
    closeTab: () => {},
    refreshActive: () => {},
    refreshNonce: 0,
  } satisfies WorkspaceTabsContextValue;
  return ({ children }: { children: ReactNode }) => (
    <WorkspaceTabsContext.Provider value={value}>
      {children}
    </WorkspaceTabsContext.Provider>
  );
}

afterEach(() => vi.clearAllMocks());

describe('useInstrumentSelection', () => {
  it('opens the detail drawer when workspace tabs are off', () => {
    const { result } = renderHook(useSelectionAndNavigate, {
      wrapper: wrapperWithTabs(false),
    });
    act(() => result.current.select('VWRL.L', 'Vanguard FTSE All-World'));

    expect(result.current.selected).toEqual({
      ticker: 'VWRL.L',
      name: 'Vanguard FTSE All-World',
      instrumentType: undefined,
    });
    expect(result.current.navigate).not.toHaveBeenCalled();

    act(() => result.current.clear());
    expect(result.current.selected).toBeNull();
  });

  it('goes to the research page when workspace tabs are on', () => {
    const { result } = renderHook(useSelectionAndNavigate, {
      wrapper: wrapperWithTabs(true),
    });
    act(() => result.current.select('USDGBP.FX', 'USD'));

    expect(result.current.navigate).toHaveBeenCalledWith('/research/USDGBP.FX');
    expect(result.current.selected).toBeNull();
  });
});
