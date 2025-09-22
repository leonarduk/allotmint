import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useConfig } from "../ConfigContext";
import type { Mode } from "../modes";
import useFetch from "./useFetch";
import { getGroups } from "../api";

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
  const mode: Mode =
    path[0] === "portfolio" ? "owner" :
    path[0] === "instrument" ? "instrument" :
    path[0] === "transactions" ? "transactions" :
    path[0] === "performance" ? "performance" :
    path[0] === "screener" ? "screener" :
    path[0] === "timeseries" ? "timeseries" :
    path[0] === "watchlist" ? "watchlist" :
    path[0] === "movers" ? "movers" :
    path[0] === "instrumentadmin" ? "instrumentadmin" :
    path[0] === "dataadmin" ? "dataadmin" :
    path[0] === "profile" ? "profile" :
    path[0] === "trail" ? "trail" :
    path[0] === "support" ? "support" :
    path[0] === "scenario" ? "scenario" :
    path[0] === "logs" ? "logs" :
    path.length === 0 ? "group" : "movers";
  const slug = path[1] ?? "";
  const owner = mode === "owner" ? slug : "";
  const group =
    mode === "instrument" ? "" : params.get("group") ?? "";
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

  function pathFor(m: Mode) {
    switch (m) {
      case "group":
        return selectedGroup ? `/?group=${selectedGroup}` : "/";
      case "instrument":
        return selectedGroup ? `/instrument/${selectedGroup}` : "/instrument";
      case "owner":
        return selectedOwner ? `/portfolio/${selectedOwner}` : "/portfolio";
      case "performance":
        return selectedOwner
          ? `/performance/${selectedOwner}`
          : "/performance";
      case "movers":
        return "/movers";
      case "scenario":
        return "/scenario";
      case "settings":
        return "/settings";
      case "logs":
        return "/logs";
      case "instrumentadmin":
        return "/instrumentadmin";
      case "profile":
        return "/profile";
      case "trail":
        return "/trail";
      default:
        return `/${m}`;
    }
  }

  useEffect(() => {
    const segs = location.pathname.split("/").filter(Boolean);
    const params = new URLSearchParams(location.search);
    let newMode: Mode;
    switch (segs[0]) {
      case "portfolio":
        newMode = "owner";
        break;
      case "instrument":
        newMode = "instrument";
        break;
      case "transactions":
        newMode = "transactions";
        break;
      case "performance":
        newMode = "performance";
        break;
      case "screener":
        newMode = "screener";
        break;
      case "timeseries":
        newMode = "timeseries";
        break;
      case "watchlist":
        newMode = "watchlist";
        break;
      case "movers":
        newMode = "movers";
        break;
      case "instrumentadmin":
        newMode = "instrumentadmin";
        break;
      case "dataadmin":
        newMode = "dataadmin";
        break;
      case "profile":
        newMode = "profile";
        break;
      case "trail":
        newMode = "trail";
        break;
      case "support":
        newMode = "support";
        break;
      case "logs":
        newMode = "logs";
        break;
      case "settings":
        newMode = "settings";
        break;
      case "scenario":
        newMode = "scenario";
        break;
      default:
        newMode = segs.length === 0 ? "group" : "movers";
    }

    if (tabs[newMode] !== true || disabledTabs?.includes(newMode)) {
      const firstEnabled = Object.entries(tabs).find(
        ([m, enabled]) =>
          enabled === true && !disabledTabs?.includes(m as Mode),
      )?.[0] as Mode | undefined;

      if (firstEnabled) {
        if (mode !== firstEnabled) setMode(firstEnabled);
        const targetPath = pathFor(firstEnabled);
        if (location.pathname !== targetPath)
          navigate(targetPath, { replace: true });
      } else {
        // eslint-disable-next-line no-console
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
    if (newMode === "owner") {
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
      setSelectedGroup(params.get("group") ?? "");
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

