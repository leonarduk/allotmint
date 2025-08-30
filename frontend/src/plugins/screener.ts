import ScreenerQuery from "../pages/ScreenerQuery";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin = {
  id: "screener",
  component: ScreenerQuery,
  priority: 60,
  path: () => "/screener",
};

export default plugin;
