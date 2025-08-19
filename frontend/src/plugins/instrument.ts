import { InstrumentTable } from "../components/InstrumentTable";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin = {
  id: "instrument",
  component: InstrumentTable,
  priority: 20,
  path: ({ group }) => (group ? `/instrument/${group}` : "/instrument"),
};

export default plugin;
