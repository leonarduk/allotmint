import AllocationCharts from "../pages/AllocationCharts";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin = {
  id: "allocation",
  component: AllocationCharts,
  priority: 85,
  path: () => "/allocation",
};

export default plugin;
