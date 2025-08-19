export const tabPlugins = {
  group: {},
  owner: {},
  instrument: {},
  performance: {},
  transactions: {},
  screener: {},
  timeseries: {},
  watchlist: {},
  movers: {},
  dataadmin: {},
  virtual: {},
  support: {},
  reports: {},
  scenario: {},
};
export type TabPluginId = keyof typeof tabPlugins;
