import type { HTMLAttributes, ReactNode } from "react";

interface Action {
  label: string;
  onClick: () => void;
}

interface EmptyStateProps extends HTMLAttributes<HTMLDivElement> {
  message: string;
  actions?: Action[];
  /** Optional extra content (e.g. a search control) rendered below the message/actions. */
  children?: ReactNode;
}

export function EmptyState({ message, actions = [], children, ...divProps }: EmptyStateProps) {
  return (
    <div className="p-4 text-center text-gray-500" {...divProps}>
      <p>{message}</p>
      {actions.length > 0 && (
        <div className="mt-4 flex justify-center gap-2">
          {actions.map((a) => (
            <button
              key={a.label}
              type="button"
              onClick={a.onClick}
              className="rounded bg-blue-500 px-4 py-2 text-white"
            >
              {a.label}
            </button>
          ))}
        </div>
      )}
      {children}
    </div>
  );
}

export default EmptyState;
