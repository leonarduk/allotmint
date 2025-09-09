export const tabPluginMap = {
  group: {},
  owner: {},
  instrument: {},
  performance: {},
  transactions: {},
  trading: {},
  screener: {},
  timeseries: {},
  watchlist: {},
  allocation: {},
  rebalance: {},
  movers: {},
  instrumentadmin: {},
  dataadmin: {},
  virtual: {},
  support: {},
  settings: {},
  profile: {},
  alertsettings: {},
  reports: {},
  scenario: {},
  logs: {},
};
export type TabPluginId = keyof typeof tabPluginMap;
export const orderedTabPlugins = [
  { id: "group", priority: 0, section: "user" },
  { id: "movers", priority: 10, section: "user" },
  { id: "instrument", priority: 20, section: "user" },
  { id: "owner", priority: 30, section: "user" },
  { id: "performance", priority: 40, section: "user" },
  { id: "transactions", priority: 50, section: "user" },
  { id: "trading", priority: 55, section: "user" },
  { id: "screener", priority: 60, section: "user" },
  { id: "timeseries", priority: 70, section: "user" },
  { id: "watchlist", priority: 80, section: "user" },
  { id: "allocation", priority: 85, section: "user" },
  { id: "instrumentadmin", priority: 85, section: "support" },
  { id: "dataadmin", priority: 90, section: "support" },
  { id: "reports", priority: 100, section: "user" },
  { id: "settings", priority: 105, section: "user" },
  { id: "profile", priority: 106, section: "user" },
  { id: "alertsettings", priority: 107, section: "user" },
  { id: "support", priority: 110, section: "support" },
  { id: "logs", priority: 115, section: "support" },
  { id: "scenario", priority: 120, section: "user" },
] as const;
export const USER_TABS = orderedTabPlugins
  .filter((p) => p.section === "user")
  .map((p) => p.id);
export const SUPPORT_TABS = orderedTabPlugins
  .filter((p) => p.section === "support")
  .map((p) => p.id);
export type TabPlugin = typeof orderedTabPlugins[number];
