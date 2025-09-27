import { GroupPortfolioView } from "../components/GroupPortfolioView";
import type { ComponentProps } from "react";
import type { TabPlugin } from "./TabPlugin";
import { isDefaultGroupSlug } from "../utils/groups";

type Props = ComponentProps<typeof GroupPortfolioView>;

const plugin: TabPlugin<Props> = {
  id: "group",
  component: GroupPortfolioView,
  priority: 10,
  path: ({ group }) =>
    group && !isDefaultGroupSlug(group) ? `/?group=${group}` : "/",
};

export default plugin;
