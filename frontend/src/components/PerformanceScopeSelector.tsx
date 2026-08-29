import type { OwnerSummary, GroupSummary } from "../types";
import { useTranslation } from "react-i18next";
import { useCallback, memo } from "react";
import type { ChangeEventHandler } from "react";

export type PerformanceScope =
  | { kind: "owner"; owner: string }
  | { kind: "group"; slug: string };

type Props = {
  owners: OwnerSummary[];
  groups: GroupSummary[];
  /** Currently active scope, or null while nothing is selected yet. */
  value: PerformanceScope | null;
  onSelect: (scope: PerformanceScope) => void;
};

const OWNER_PREFIX = "owner:";
const GROUP_PREFIX = "group:";

const ownerOptionValue = (owner: string) => `${OWNER_PREFIX}${owner}`;
const groupOptionValue = (slug: string) => `${GROUP_PREFIX}${slug}`;

/**
 * Owner/group scope picker for the Performance page (#7228). Mirrors how
 * `/instrument` already scopes to a group, extended to also offer every
 * individual owner -- the household ("All"/`all`) as well as each member --
 * in one dropdown so combined performance is reachable, not just
 * per-owner performance.
 *
 * Renders its own <select> (rather than the shared Selector primitive) so
 * groups and owners can sit under distinct <optgroup> labels instead of
 * being concatenated flat, which would otherwise put "At a glance" /
 * "Adults" / "Children" indistinguishably above four people's names.
 */
export const PerformanceScopeSelector = memo(function PerformanceScopeSelector({
  owners,
  groups,
  value,
  onSelect,
}: Props) {
  const { t } = useTranslation();

  const handleChange = useCallback<ChangeEventHandler<HTMLSelectElement>>(
    (e) => {
      const raw = e.target.value;
      if (raw.startsWith(GROUP_PREFIX)) {
        onSelect({ kind: "group", slug: raw.slice(GROUP_PREFIX.length) });
      } else if (raw.startsWith(OWNER_PREFIX)) {
        onSelect({ kind: "owner", owner: raw.slice(OWNER_PREFIX.length) });
      }
    },
    [onSelect],
  );

  const selectedValue = value
    ? value.kind === "group"
      ? groupOptionValue(value.slug)
      : ownerOptionValue(value.owner)
    : "";

  return (
    <label
      style={{
        display: "inline-block",
        marginRight: "0.5rem",
        marginBottom: "1rem",
      }}
    >
      {t("dashboard.performanceScopeLabel")}:
      <select
        value={selectedValue}
        onChange={handleChange}
        style={{ marginLeft: "0.5rem" }}
      >
        {groups.length > 0 && (
          <optgroup label={t("dashboard.performanceScopeGroups")}>
            {groups.map((g) => (
              <option key={groupOptionValue(g.slug)} value={groupOptionValue(g.slug)}>
                {g.name}
              </option>
            ))}
          </optgroup>
        )}
        {owners.length > 0 && (
          <optgroup label={t("dashboard.performanceScopeOwners")}>
            {owners.map((o) => (
              <option key={ownerOptionValue(o.owner)} value={ownerOptionValue(o.owner)}>
                {o.full_name?.trim() ? o.full_name : o.owner}
              </option>
            ))}
          </optgroup>
        )}
      </select>
    </label>
  );
});
