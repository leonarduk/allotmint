import { useMemo } from "react";
import type { FC } from "react";

/**
 * Build a three-level hierarchy (asset_class -> industry -> region) from
 * instrument summaries.
 */
export interface InstrumentSummary {
  ticker: string;
  market_value_gbp: number;
  asset_class?: string | null;
  industry?: string | null;
  region?: string | null;
}

export interface AllocationNode {
  name: string;
  value?: number;
  children?: AllocationNode[];
}

function addToTree(root: Record<string, AllocationNode>, inst: InstrumentSummary) {
  const ac = inst.asset_class ?? "Unknown";
  const ind = inst.industry ?? "Unknown";
  const reg = inst.region ?? "Unknown";

  const acNode = (root[ac] = root[ac] || { name: ac, children: {} as any });
  const indChildren = (acNode.children as any);
  const indNode = (indChildren[ind] = indChildren[ind] || {
    name: ind,
    children: {} as any,
  });
  const regChildren = (indNode.children as any);
  const regNode = (regChildren[reg] = regChildren[reg] || {
    name: reg,
    value: 0,
  });
  regNode.value! += inst.market_value_gbp;
}

export function buildAllocationHierarchy(
  instruments: InstrumentSummary[],
): AllocationNode[] {
  const root: Record<string, AllocationNode> = {};
  instruments.forEach((inst) => addToTree(root, inst));

  // Convert nested maps to arrays expected by chart libs
  const convert = (node: AllocationNode): AllocationNode => {
    if (node.children) {
      const children = Object.values(node.children).map(convert);
      return { name: node.name, children };
    }
    return node;
  };

  return Object.values(root).map(convert);
}

/**
 * Simple component that renders the hierarchy as JSON.  Charting libraries
 * can consume the ``buildAllocationHierarchy`` result instead.
 */
const AllocationCharts: FC<{ instruments: InstrumentSummary[] }> = ({
  instruments,
}) => {
  const data = useMemo(
    () => buildAllocationHierarchy(instruments),
    [instruments],
  );
  return <pre>{JSON.stringify(data, null, 2)}</pre>;
};

export default AllocationCharts;
