import type { ComponentType } from "react";

export interface TabPlugin {
  id: string;
  priority: number;
  labelKey: string;
  pathFor: (...params: unknown[]) => string;
  Component: ComponentType<unknown>;
}

export const tabPlugins: TabPlugin[] = [];
