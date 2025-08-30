import { PortfolioView } from "../components/PortfolioView";
import type { ComponentProps } from "react";
import type { TabPlugin } from "./TabPlugin";

type Props = ComponentProps<typeof PortfolioView>;

const plugin: TabPlugin<Props> = {
  id: "owner",
  component: PortfolioView,
  priority: 30,
  path: ({ owner }) => (owner ? `/member/${owner}` : "/member"),
};

export default plugin;
