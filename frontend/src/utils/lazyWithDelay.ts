import { lazy } from "react";

/**
 * Wraps React.lazy with a minimum delay to keep skeletons visible.
 */
export default function lazyWithDelay<T extends React.ComponentType<any>>(
  factory: () => Promise<{ default: T }>,
  delay = 300,
) {
  return lazy(() =>
    Promise.all([
      factory(),
      new Promise((resolve) => setTimeout(resolve, delay)),
    ]).then(([module]) => module),
  );
}
