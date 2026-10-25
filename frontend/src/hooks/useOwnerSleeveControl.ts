import { useCallback, useEffect, useState } from "react";
import { assignSleeve, getSleeves } from "../api";
import type { SleeveList } from "../types";
import type { SleeveControl } from "../components/HoldingSleeveCell";

const CORE_ID = "core";

/**
 * Sleeve tagging for one owner's holdings view (#9839). Undefined (no control)
 * for a group view, while loading, when sleeves can't be loaded, or when the
 * owner has only the core sleeve, so the default table is unchanged.
 */
export function useOwnerSleeveControl(owner: string | null): SleeveControl | undefined {
  const [list, setList] = useState<SleeveList | null>(null);

  useEffect(() => {
    setList(null);
    if (!owner) return;
    let active = true;
    getSleeves(owner)
      .then((res) => {
        if (active) setList(res);
      })
      .catch((err) => {
        // The control is an optional convenience; the Strategy page still tags holdings.
        console.warn("Sleeve tagging unavailable for owner", owner, err);
      });
    return () => {
      active = false;
    };
  }, [owner]);

  const onAssign = useCallback(
    async (ticker: string, sleeveId: string) => {
      if (!owner) return;
      // The core id removes the tag; the response is the updated listing.
      setList(await assignSleeve(owner, ticker, sleeveId === CORE_ID ? null : sleeveId));
    },
    [owner],
  );

  if (!owner || !Array.isArray(list?.sleeves) || list.sleeves.length <= 1) return undefined;
  return { sleeves: list.sleeves, assignments: list.assignments ?? {}, onAssign };
}
