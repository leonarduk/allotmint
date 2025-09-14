import type { ComponentProps } from "react";
import lazyWithDelay from "../utils/lazyWithDelay";
import type { TabPlugin } from "./TabPlugin";

const PortfolioDashboard = lazyWithDelay(() => import("../pages/PortfolioDashboard"));
type Props = ComponentProps<typeof PortfolioDashboard>;

const plugin: TabPlugin<Props> = {
  id: "performance",
  component: PortfolioDashboard,
  priority: 40,
  path: ({ owner }) => (owner ? `/performance/${owner}` : "/performance"),
};

export default plugin;
