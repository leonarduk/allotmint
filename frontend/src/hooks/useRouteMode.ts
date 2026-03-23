import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useConfig } from '../ConfigContext';
import type { Mode } from '../modes';
import useFetch from './useFetch';
import { getGroups } from '../api';
import { normaliseGroupSlug } from '../utils/groups';
import { buildPathForMode, deriveRouteFromPathname } from '../pageManifest';

interface RouteState {
  mode: Mode;
  setMode: (mode: Mode) => void;
  selectedOwner: string;
  setSelectedOwner: (owner: string) => void;
  selectedGroup: string;
  setSelectedGroup: (group: string) => void;
}

function deriveInitialState() {
  const params = new URLSearchParams(window.location.search);
  const route = deriveRouteFromPathname(window.location.pathname);
  const owner = route.mode === 'owner' || route.mode === 'performance' ? route.slug : '';
  const group = route.mode === 'instrument' ? route.slug : normaliseGroupSlug(params.get('group'));

  return {
    mode: route.mode,
    owner,
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
  const [selectedGroup, setSelectedGroup] = useState(initial.group);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const route = deriveRouteFromPathname(location.pathname);
    const nextMode = route.mode;
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
      setSelectedOwner(route.slug);
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
      setSelectedGroup(normaliseGroupSlug(params.get('group')));
    }
  }, [disabledTabs, groups, location.pathname, location.search, navigate, selectedGroup, selectedOwner, tabs]);

  return {
    mode,
    setMode,
    selectedOwner,
    setSelectedOwner,
    selectedGroup,
    setSelectedGroup,
  };
}
