
export const tabPlugins = [
  { id: "movers", priority: 0 },
  { id: "group", priority: 10 },
  { id: "instrument", priority: 20 },
  { id: "owner", priority: 30 },
  { id: "performance", priority: 40 },
  { id: "transactions", priority: 50 },
  { id: "screener", priority: 60 },
  { id: "timeseries", priority: 70 },
  { id: "watchlist", priority: 80 },
  { id: "dataadmin", priority: 90 },
  { id: "reports", priority: 100 },
  { id: "support", priority: 110 },
  { id: "scenario", priority: 120 },
] as const;
export type TabPlugin = typeof tabPlugins[number];
