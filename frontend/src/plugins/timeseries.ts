import { TimeseriesEdit } from "../pages/TimeseriesEdit";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin = {
  id: "timeseries",
  component: TimeseriesEdit,
  priority: 70,
  path: () => "/timeseries",
};

export default plugin;
