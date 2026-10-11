import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useWorkspaceTabs } from '../contexts/workspaceTabs';

export interface SelectedInstrument {
  ticker: string;
  name: string;
  instrumentType?: string | null;
}

/**
 * Which holding's detail drawer is open. With workspace tabs on, picking a
 * holding opens its research page instead, which lands in its own tab
 * (#10711), so the drawer never opens.
 */
export function useInstrumentSelection() {
  const { enabled: tabsEnabled } = useWorkspaceTabs();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<SelectedInstrument | null>(null);

  const select = useCallback(
    (ticker: string, name: string, instrumentType?: string | null) => {
      if (tabsEnabled) {
        navigate(`/research/${encodeURIComponent(ticker)}`);
      } else {
        setSelected({ ticker, name, instrumentType });
      }
    },
    [navigate, tabsEnabled]
  );

  const clear = useCallback(() => setSelected(null), []);

  return { selected, select, clear };
}
