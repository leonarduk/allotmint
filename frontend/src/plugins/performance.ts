import { PerformanceDashboard } from "../components/PerformanceDashboard";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin = {
  id: "performance",
  component: PerformanceDashboard,
  priority: 40,
  path: ({ owner }) => (owner ? `/performance/${owner}` : "/performance"),
};

export default plugin;
