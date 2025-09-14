import { useReducer } from "react";
import { useTranslation } from "react-i18next";

export type FilterState = {
  ticker: string;
  name: string;
  instrument_type: string;
  units: string;
  gain_pct: string;
  sell_eligible: string;
};

export type FilterAction =
  | { type: "set"; key: keyof FilterState; value: string }
  | { type: "clear"; key: keyof FilterState }
  | { type: "clearAll" };

export function filterReducer(state: FilterState, action: FilterAction): FilterState {
  switch (action.type) {
    case "set":
      return { ...state, [action.key]: action.value };
    case "clear":
      return { ...state, [action.key]: "" };
    case "clearAll":
      return Object.keys(state).reduce((acc, key) => ({ ...acc, [key]: "" }), {} as FilterState);
    default:
      return state;
  }
}

export function useFilterReducer(initial?: Partial<FilterState>) {
  const defaultState: FilterState = {
    ticker: "",
    name: "",
    instrument_type: "",
    units: "",
    gain_pct: "",
    sell_eligible: "",
  };
  return useReducer(filterReducer, { ...defaultState, ...initial });
}

export function FilterBar({
  state,
  dispatch,
}: {
  state: FilterState;
  dispatch: React.Dispatch<FilterAction>;
}) {
  const { t } = useTranslation();
  const labels: Record<keyof FilterState, string> = {
    ticker: t("holdingsTable.filters.ticker"),
    name: t("holdingsTable.filters.name"),
    instrument_type: t("holdingsTable.filters.type"),
    units: t("holdingsTable.filters.units"),
    gain_pct: t("holdingsTable.filters.gainPct"),
    sell_eligible: t("holdingsTable.filters.sellEligible"),
  };

  const active = Object.entries(state).filter(([, v]) => v);
  if (!active.length) return null;

  return (
    <div className="mb-2 flex flex-wrap items-center gap-2">
      {active.map(([key, value]) => (
        <button
          key={key}
          type="button"
          className="flex items-center gap-1 rounded bg-gray-200 px-2 py-1 text-sm"
          onClick={() => dispatch({ type: "clear", key: key as keyof FilterState })}
          onKeyDown={(e) => {
            if (e.key === "Backspace" || e.key === "Delete") {
              e.preventDefault();
              dispatch({ type: "clear", key: key as keyof FilterState });
            }
          }}
        >
          <span>{labels[key as keyof FilterState]}: {value}</span>
          <span aria-hidden="true">×</span>
        </button>
      ))}
      <button
        type="button"
        className="ml-2 text-sm underline"
        onClick={() => dispatch({ type: "clearAll" })}
        onKeyDown={(e) => {
          if (e.key === "Backspace" || e.key === "Delete") {
            e.preventDefault();
            dispatch({ type: "clearAll" });
          }
        }}
      >
        Clear all
      </button>
    </div>
  );
}

export default FilterBar;
