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

interface RouteState {
  mode: Mode;
  setMode: (m: Mode) => void;
  selectedOwner: string;
  setSelectedOwner: (s: string) => void;
  selectedGroup: string;
  setSelectedGroup: (s: string) => void;
}

function segmentToMode(segment: string | undefined, segmentCount: number): Mode {
  switch (segment) {
    case undefined:
      return "group";
    case "portfolio":
      return "owner";
    case "instrument":
      return "instrument";
    case "transactions":
      return "transactions";
    case "trading":
      return "trading";
    case "performance":
      return "performance";
    case "screener":
      return "screener";
    case "timeseries":
      return "timeseries";
    case "watchlist":
      return "watchlist";
    case "allocation":
      return "allocation";
    case "rebalance":
      return "rebalance";
    case "market":
      return "market";
    case "movers":
      return "movers";
    case "instrumentadmin":
      return "instrumentadmin";
    case "dataadmin":
      return "dataadmin";
    case "virtual":
      return "virtual";
    case "reports":
      return "reports";
    case "alert-settings":
      return "alertsettings";
    case "trade-compliance":
      return "tradecompliance";
    case "trail":
      return "trail";
    case "support":
      return "support";
    case "pension":
      return "pension";
    case "tax-tools":
      return "taxtools";
    case "settings":
      return "settings";
    case "scenario":
      return "scenario";
    case "research":
      return "research";
    default:
      return segmentCount === 0 ? "group" : "movers";
  }
}

function deriveInitial() {
  const path = window.location.pathname.split("/").filter(Boolean);
  const params = new URLSearchParams(window.location.search);
  const mode = segmentToMode(path[0], path.length);
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

  function pathFor(m: Mode) {
    switch (m) {
      case "group":
        return selectedGroup && !isDefaultGroupSlug(selectedGroup)
          ? `/?group=${selectedGroup}`
          : "/";
      case "instrument":
        return selectedGroup ? `/instrument/${selectedGroup}` : "/instrument";
      case "owner":
        return selectedOwner ? `/portfolio/${selectedOwner}` : "/portfolio";
      case "performance":
        return selectedOwner
          ? `/performance/${selectedOwner}`
          : "/performance";
      case "allocation":
        return "/allocation";
      case "rebalance":
        return "/rebalance";
      case "market":
        return "/market";
      case "movers":
        return "/movers";
      case "trading":
        return "/trading";
      case "scenario":
        return "/scenario";
      case "reports":
        return "/reports";
      case "settings":
        return "/settings";
      case "alertsettings":
        return "/alert-settings";
      case "instrumentadmin":
        return "/instrumentadmin";
      case "tradecompliance":
        return "/trade-compliance";
      case "trail":
        return "/trail";
      case "taxtools":
        return "/tax-tools";
      case "pension":
        return "/pension/forecast";
      default:
        return `/${m}`;
    }
  }

  useEffect(() => {
    const segs = location.pathname.split("/").filter(Boolean);
    const params = new URLSearchParams(location.search);
    const newMode = segmentToMode(segs[0], segs.length);

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

