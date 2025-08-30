import { InstrumentTable } from "../components/InstrumentTable";
import type { ComponentProps } from "react";
import type { TabPlugin } from "./TabPlugin";

type Props = ComponentProps<typeof InstrumentTable>;

const plugin: TabPlugin<Props> = {
  id: "instrument",
  component: InstrumentTable,
  priority: 20,
  path: ({ group }) => (group ? `/instrument/${group}` : "/instrument"),
};

export default plugin;
