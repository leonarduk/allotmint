import AllocationCharts, {
  type AllocationChartsProps,
} from "../pages/AllocationCharts";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin<AllocationChartsProps> = {
  id: "allocation",
  component: AllocationCharts,
  priority: 85,
  path: () => "/allocation",
};

export default plugin;
