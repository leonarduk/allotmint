export type Mode =
  | "owner"
  | "group"
  | "instrument"
  | "transactions"
  | "performance"
  | "screener"
  | "timeseries"
  | "watchlist"
  | "movers"
  | "instrumentadmin"
  | "dataadmin"
  | "settings"
  | "profile"
  | "trail"
  | "support"
  | "scenario";

export const MODES: Mode[] = [
  "group",
  "movers",
  "instrument",
  "owner",
  "performance",
  "transactions",
  "screener",
  "timeseries",
  "watchlist",
  "instrumentadmin",
  "dataadmin",
  "settings",
  "profile",
  "trail",
  "support",
  "scenario",
];
