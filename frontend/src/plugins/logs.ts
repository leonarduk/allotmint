import Logs from "../pages/Logs";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin = {
  id: "logs",
  component: Logs,
  priority: 115,
  path: () => "/logs",
};

export default plugin;
