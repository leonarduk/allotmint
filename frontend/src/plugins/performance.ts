import type { ComponentProps } from "react";
import lazyWithDelay from "../utils/lazyWithDelay";
import type { TabPlugin } from "./TabPlugin";

const PerformanceDashboard = lazyWithDelay(
  () => import("../components/PerformanceDashboard"),
);
type Props = ComponentProps<typeof PerformanceDashboard>;

const plugin: TabPlugin<Props> = {
  id: "performance",
  component: PerformanceDashboard,
  priority: 40,
  path: ({ owner }) => (owner ? `/performance/${owner}` : "/performance"),
};

export default plugin;
