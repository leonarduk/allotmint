import TopMovers from "../pages/TopMovers";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin = {
  id: "movers",
  component: TopMovers,
  priority: 10,
  path: () => "/movers",
};

export default plugin;
