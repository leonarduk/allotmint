import PortfolioDashboard from "../pages/PortfolioDashboard";
import type { ComponentProps } from "react";
import type { TabPlugin } from "./TabPlugin";

type Props = ComponentProps<typeof PortfolioDashboard>;

const plugin: TabPlugin<Props> = {
  id: "performance",
  component: PortfolioDashboard,
  priority: 40,
  path: ({ owner }) => (owner ? `/performance/${owner}` : "/performance"),
};

export default plugin;
