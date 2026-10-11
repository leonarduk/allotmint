import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { WorkspaceTabsInlineToggle } from '../../../src/components/WorkspaceTabsInlineToggle';
import { WorkspaceTabsContext } from '../../../src/contexts/workspaceTabs';
import type { WorkspaceTabsContextValue } from '../../../src/contexts/workspaceTabs';

function renderWith(enabled: boolean, setEnabled = vi.fn()) {
  const value = {
    enabled,
    setEnabled,
    tabs: [],
    activeId: '',
    openCurrentInNewTab: () => {},
    selectTab: () => {},
    closeTab: () => {},
    refreshActive: () => {},
    refreshNonce: 0,
  } satisfies WorkspaceTabsContextValue;
  render(
    <WorkspaceTabsContext.Provider value={value}>
      <WorkspaceTabsInlineToggle />
    </WorkspaceTabsContext.Provider>
  );
  return setEnabled;
}

describe('WorkspaceTabsInlineToggle', () => {
  it('reflects the current preference', () => {
    renderWith(true);
    expect(
      screen.getByRole('checkbox', { name: 'Workspace tabs' })
    ).toBeChecked();
  });

  it('switches tabs on when ticked', () => {
    const setEnabled = renderWith(false);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Workspace tabs' }));
    expect(setEnabled).toHaveBeenCalledWith(true);
  });
});
