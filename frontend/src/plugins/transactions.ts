import { TransactionsPage } from "../components/TransactionsPage";
import type { TabPlugin } from "./TabPlugin";

const plugin: TabPlugin = {
  id: "transactions",
  component: TransactionsPage,
  priority: 50,
  path: () => "/transactions",
};

export default plugin;
