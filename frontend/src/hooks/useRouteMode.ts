import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useConfig } from "../ConfigContext";
import type { Mode } from "../modes";
import useFetch from "./useFetch";
import { getGroups } from "../api";
import {
  isDefaultGroupSlug,
  normaliseGroupSlug,
} from "../utils/groups";
import {
  buildPathForMode,
  deriveModeFromPathname,
} from "../pageManifest";

interface RouteState {
  mode: Mode;
  setMode: (m: Mode) => void;
  selectedOwner: string;
  setSelectedOwner: (s: string) => void;
  selectedGroup: string;
  setSelectedGroup: (s: string) => void;
}

function deriveInitial() {
  const path = window.location.pathname.split("/").filter(Boolean);
  const params = new URLSearchParams(window.location.search);
  const mode = deriveModeFromPathname(window.location.pathname);
  const slug = path[1] ?? "";
  const owner = mode === "owner" || mode === "performance" ? slug : "";
  const group =
    mode === "instrument" ? "" : normaliseGroupSlug(params.get("group"));
  return { mode, owner, group };
}

export function useRouteMode(): RouteState {
  const navigate = useNavigate();
  const location = useLocation();
  const { tabs, disabledTabs } = useConfig();
  const { data: groups } = useFetch(getGroups);

  const initial = deriveInitial();
  const [mode, setMode] = useState<Mode>(initial.mode);
  const [selectedOwner, setSelectedOwner] = useState(initial.owner);
  const [selectedGroup, setSelectedGroup] = useState(initial.group);


  useEffect(() => {
    const segs = location.pathname.split("/").filter(Boolean);
    const params = new URLSearchParams(location.search);
    const newMode = deriveModeFromPathname(location.pathname);

    const isDisabled =
      tabs[newMode] === false || disabledTabs?.includes(newMode);
    if (isDisabled) {
      const firstEnabled = Object.entries(tabs).find(
        ([m, enabled]) =>
          enabled !== false && !disabledTabs?.includes(m as Mode),
      )?.[0] as Mode | undefined;

      if (firstEnabled) {
        if (mode !== firstEnabled) setMode(firstEnabled);
        const targetPath = buildPathForMode(firstEnabled, { owner: selectedOwner, group: selectedGroup });
        if (location.pathname !== targetPath)
          navigate(targetPath, { replace: true });
      } else {
        console.warn("No enabled tabs available for navigation");
      }
      return;
    }
    if (newMode === "movers" && location.pathname !== "/movers") {
      setMode("movers");
      navigate("/movers", { replace: true });
      return;
    }
    setMode(newMode);
    if (newMode === "owner" || newMode === "performance") {
      setSelectedOwner(segs[1] ?? "");
    } else if (newMode === "instrument") {
      const slug = segs[1] ?? "";
      if (!slug) {
        setSelectedGroup("");
      } else if (groups) {
        const isValid = groups.some((g) => g.slug === slug);
        if (isValid) {
          setSelectedGroup(slug);
        } else {
          navigate(`/research/${slug}`, { replace: true });
          return;
        }
      }
    } else if (newMode === "group") {
      const groupParam = params.get("group");
      setSelectedGroup(normaliseGroupSlug(groupParam));
      if (groupParam && isDefaultGroupSlug(groupParam) && location.search) {
        navigate("/", { replace: true });
      }
    }
  }, [
    location.pathname,
    location.search,
    tabs,
    disabledTabs,
    navigate,
    groups,
  ]);

  return {
    mode,
    setMode,
    selectedOwner,
    setSelectedOwner,
    selectedGroup,
    setSelectedGroup,
  };
}

