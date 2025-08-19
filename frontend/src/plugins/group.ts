import { GroupPortfolioView } from "../components/GroupPortfolioView";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin = {
  id: "group",
  component: GroupPortfolioView,
  priority: 10,
  path: ({ group }) => (group ? `/?group=${group}` : "/movers"),
};

export default plugin;
