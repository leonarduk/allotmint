import { Screener } from "../pages/Screener";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin = {
  id: "screener",
  component: Screener,
  priority: 60,
  path: () => "/screener",
};

export default plugin;
