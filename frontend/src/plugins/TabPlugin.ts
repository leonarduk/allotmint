import type { ComponentType } from "react";

/** Context passed to route helpers when building URLs. */
export interface RouteContext {
  owner?: string;
  group?: string;
}

/**
 * Definition of a tab plugin used to extend the navigation bar.
 * Each plugin exposes the React component to render when active,
 * a priority used for ordering, and a helper to build the tab's path.
 *
 * The component's props type can be specified via the generic `P`, which
 * defaults to `unknown` for components without props.
 */
export interface TabPlugin<P = unknown> {
  /** Unique identifier corresponding to the app mode (e.g. "movers"). */
  id: string;
  /** React component rendered when the tab is selected. */
  component: ComponentType<P>;
  /** Lower numbers appear further to the left in the navigation bar. */
  priority: number;
  /** Build a URL path for the tab based on current selections. */
  path: (ctx: RouteContext) => string;
}
