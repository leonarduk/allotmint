import Portfolio from "../pages/Portfolio";
import type { ComponentProps } from "react";
import type { TabPlugin } from "./TabPlugin";

type Props = ComponentProps<typeof Portfolio>;

const plugin: TabPlugin<Props> = {
  id: "owner",
  component: Portfolio,
  priority: 30,
  path: ({ owner }) => (owner ? `/portfolio/${owner}` : "/portfolio"),
};

export default plugin;
