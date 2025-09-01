import TopMovers from "../pages/TopMovers";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin = {
  id: "movers",
  component: TopMovers,
  priority: 0,
  path: ({ group }) => (group ? `/movers?group=${group}` : "/movers"),
};

export default plugin;
