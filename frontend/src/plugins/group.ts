import { GroupPortfolioView } from "../components/GroupPortfolioView";
import type { ComponentProps } from "react";
import type { TabPlugin } from "./TabPlugin";

type Props = ComponentProps<typeof GroupPortfolioView>;

const plugin: TabPlugin<Props> = {
  id: "group",
  component: GroupPortfolioView,
  priority: 0,
  path: ({ group }) => (group ? `/?group=${group}` : "/"),
};

export default plugin;
