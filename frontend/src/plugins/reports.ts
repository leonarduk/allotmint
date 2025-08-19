import Reports from "../pages/Reports";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin = {
  id: "reports",
  component: Reports,
  priority: 100,
  path: () => "/reports",
};

export default plugin;
