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
  | "dataadmin"
  | "support"
  | "scenario";

export const MODES: Mode[] = [
  "movers",
  "group",
  "instrument",
  "owner",
  "performance",
  "transactions",
  "screener",
  "timeseries",
  "watchlist",
  "dataadmin",
  "support",
  "scenario",
];
