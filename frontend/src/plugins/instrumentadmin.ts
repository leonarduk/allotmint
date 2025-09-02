import InstrumentAdmin from "../pages/InstrumentAdmin";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin = {
  id: "instrumentadmin",
  component: InstrumentAdmin,
  priority: 85,
  path: () => "/instrumentadmin",
};

export default plugin;
