import TopMovers from "../pages/TopMovers";
import type { TabPlugin } from "./TabPlugin";
import { isDefaultGroupSlug } from "../utils/groups";

const plugin: TabPlugin = {
  id: "movers",
  component: TopMovers,
  priority: 0,
  path: ({ group }) =>
    group && !isDefaultGroupSlug(group) ? `/movers?group=${group}` : "/movers",
};

export default plugin;
