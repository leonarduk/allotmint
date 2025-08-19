import { PortfolioView } from "../components/PortfolioView";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin = {
  id: "owner",
  component: PortfolioView,
  priority: 30,
  path: ({ owner }) => (owner ? `/member/${owner}` : "/member"),
};

export default plugin;
