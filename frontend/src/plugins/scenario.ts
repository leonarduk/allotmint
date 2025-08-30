import ScenarioTester from "../pages/ScenarioTester";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin = {
  id: "scenario",
  component: ScenarioTester,
  priority: 120,
  path: () => "/scenario",
};

export default plugin;
