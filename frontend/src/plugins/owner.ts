import Member from "../pages/Member";
import type { ComponentProps } from "react";
import type { TabPlugin } from "./TabPlugin";

type Props = ComponentProps<typeof Member>;

const plugin: TabPlugin<Props> = {
  id: "owner",
  component: Member,
  priority: 30,
  path: ({ owner }) => (owner ? `/member/${owner}` : "/member"),
};

export default plugin;
