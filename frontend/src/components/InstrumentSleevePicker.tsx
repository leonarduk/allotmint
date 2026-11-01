import { useId, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useOwnerSleeveControl } from "../hooks/useOwnerSleeveControl";
import type { InstrumentPosition } from "../types";
import { SleeveSelect } from "./HoldingSleeveCell";

/**
 * One owner's sleeve picker for the instrument. Renders nothing while loading,
 * when the owner has only the core sleeve (or sleeves can't be loaded), or
 * when the owner's own holdings listing doesn't include this ticker.
 */
function OwnerSleevePicker({ owner, ticker }: { owner: string; ticker: string }) {
  const { t } = useTranslation();
  // One picker per owner on the page, so the label id must be per instance.
  const labelId = useId();
  const control = useOwnerSleeveControl(owner);
  // Match and write with the same key the backend stores tags under.
  const key = ticker.trim().toUpperCase();
  if (!control?.heldTickers?.has(key)) return null;
  const label = t("sleeves.assign.sleeveForOwner", { ticker: key, owner });
  return (
    <div style={{ marginBottom: "0.5rem" }}>
      {/* The visible text is the select's only accessible name (#11173). */}
      <span id={labelId} style={{ marginRight: "0.5rem" }}>
        {label}
      </span>
      <SleeveSelect control={control} ticker={key} labelledBy={labelId} />
    </div>
  );
}

/**
 * Sleeve tagging on the instrument research page (#9839). The page has no
 * selected owner, so the owners come from the positions (as Buy/Sell does):
 * each owner holding the ticker gets their own picker, writing only their own
 * tag, so a ticker held by several owners is never tagged for all of them.
 */
export function InstrumentSleevePicker({ ticker, positions }: { ticker: string; positions: InstrumentPosition[] }) {
  const owners = useMemo(
    () => Array.from(new Set(positions.map((p) => p.owner).filter((o): o is string => Boolean(o)))).sort(),
    [positions],
  );
  if (!ticker || owners.length === 0) return null;
  return (
    <div>
      {owners.map((owner) => (
        <OwnerSleevePicker key={owner} owner={owner} ticker={ticker} />
      ))}
    </div>
  );
}
