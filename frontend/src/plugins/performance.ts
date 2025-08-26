import { PerformanceDashboard } from "../components/PerformanceDashboard";
import type { ComponentProps } from "react";
import type { TabPlugin } from "./TabPlugin";

type Props = ComponentProps<typeof PerformanceDashboard>;

const plugin: TabPlugin<Props> = {
  id: "performance",
  component: PerformanceDashboard,
  priority: 40,
  path: ({ owner }) => (owner ? `/performance/${owner}` : "/performance"),
};

export default plugin;
