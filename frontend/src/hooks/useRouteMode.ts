import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useConfig } from '../ConfigContext';
import type { Mode } from '../modes';
import useFetch from './useFetch';
import { getGroups } from '../api';
import { normaliseGroupSlug } from '../utils/groups';
import { buildPathForMode, deriveModeFromLocation, deriveRouteFromPathname, readRouteScopeQuery } from '../pageManifest';

interface RouteState {
  mode: Mode;
  setMode: (mode: Mode) => void;
  selectedOwner: string;
  setSelectedOwner: (owner: string) => void;
  selectedAccount: string;
  setSelectedAccount: (account: string) => void;
  selectedGroup: string;
  setSelectedGroup: (group: string) => void;
}

function deriveInitialState() {
  const scope = readRouteScopeQuery(window.location.search);
  const route = deriveRouteFromPathname(window.location.pathname);
  const mode = deriveModeFromLocation(window.location.pathname, window.location.search);
  const owner =
    route.mode === 'owner' || route.mode === 'performance'
      ? route.slug || scope.owner || ''
      : scope.owner ?? '';
  const group = route.mode === 'instrument' ? route.slug : normaliseGroupSlug(scope.group);
  const account = scope.account ?? '';

  return {
    mode,
    owner,
    account,
    group,
  };
}

export function useRouteMode(): RouteState {
  const navigate = useNavigate();
  const location = useLocation();
  const { tabs, disabledTabs } = useConfig();
  const { data: groups } = useFetch(getGroups);

  const initial = deriveInitialState();
  const [mode, setMode] = useState<Mode>(initial.mode);
  const [selectedOwner, setSelectedOwner] = useState(initial.owner);
  const [selectedAccount, setSelectedAccount] = useState(initial.account);
  const [selectedGroup, setSelectedGroup] = useState(initial.group);

  useEffect(() => {
    const scope = readRouteScopeQuery(location.search);
    const route = deriveRouteFromPathname(location.pathname);
    const nextMode = deriveModeFromLocation(location.pathname, location.search);
    const isDisabled = tabs[nextMode] === false || disabledTabs?.includes(nextMode);

    if (isDisabled) {
      const firstEnabled = (Object.entries(tabs).find(
        ([tabMode, enabled]) => enabled !== false && !disabledTabs?.includes(tabMode as Mode),
      )?.[0] ?? 'group') as Mode;
      setMode(firstEnabled);
      navigate(
        buildPathForMode(firstEnabled, {
          selectedOwner,
          selectedGroup,
        }),
        { replace: true },
      );
      return;
    }

    setMode(nextMode);

    if (nextMode === 'owner' || nextMode === 'performance') {
      const nextOwner = route.slug || scope.owner || '';
      const nextAccount = scope.account ?? '';
      if (selectedOwner !== nextOwner) setSelectedOwner(nextOwner);
      if (selectedAccount !== nextAccount) setSelectedAccount(nextAccount);
      return;
    }

    if (nextMode === 'instrument') {
      if (!route.slug) {
        setSelectedGroup('');
        return;
      }

      if (!groups) {
        setSelectedGroup(route.slug);
        return;
      }

      const isValidGroup = groups.some((group) => group.slug === route.slug);
      if (isValidGroup) {
        setSelectedGroup(route.slug);
      } else {
        navigate(`/research/${route.slug}`, { replace: true });
      }
      return;
    }

    if (nextMode === 'group') {
      const nextOwner = scope.owner ?? '';
      const nextAccount = scope.account ?? '';
      if (selectedOwner !== nextOwner) setSelectedOwner(nextOwner);
      if (selectedAccount !== nextAccount) setSelectedAccount(nextAccount);
      setSelectedGroup(normaliseGroupSlug(scope.group));
    }
  }, [disabledTabs, groups, location.pathname, location.search, navigate, selectedAccount, selectedGroup, selectedOwner, tabs]);

  return {
    mode,
    setMode,
    selectedOwner,
    setSelectedOwner,
    selectedAccount,
    setSelectedAccount,
    selectedGroup,
    setSelectedGroup,
  };
}
