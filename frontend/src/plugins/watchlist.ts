import Watchlist from "../pages/Watchlist";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin = {
  id: "watchlist",
  component: Watchlist,
  priority: 80,
  path: () => "/watchlist",
};

export default plugin;
