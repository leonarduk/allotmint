import DataAdmin from "../pages/DataAdmin";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin = {
  id: "dataadmin",
  component: DataAdmin,
  priority: 90,
  path: () => "/dataadmin",
};

export default plugin;
