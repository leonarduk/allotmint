import Support from "../pages/Support";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin = {
  id: "support",
  component: Support,
  priority: 110,
  path: () => "/support",
};

export default plugin;
