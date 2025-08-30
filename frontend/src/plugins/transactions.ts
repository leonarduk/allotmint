import { TransactionsPage } from "../components/TransactionsPage";
import type { ComponentProps } from "react";
import type { TabPlugin } from "./TabPlugin";

type Props = ComponentProps<typeof TransactionsPage>;

const plugin: TabPlugin<Props> = {
  id: "transactions",
  component: TransactionsPage,
  priority: 50,
  path: () => "/transactions",
};

export default plugin;
