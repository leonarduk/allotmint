// src/components/GroupPortfolioView.tsx
import { useState, useEffect, useCallback } from "react";

import type {
  GroupPortfolio,
  Account,
  SectorContribution,
  RegionContribution,
} from "../types";
import {
  getGroupPortfolio,
  getGroupAlphaVsBenchmark,
  getGroupTrackingError,
  getGroupMaxDrawdown,
  getGroupSectorContributions,
  getGroupRegionContributions,
} from "../api";
import { HoldingsTable } from "./HoldingsTable";
import { InstrumentDetail } from "./InstrumentDetail";
import { TopMoversSummary } from "./TopMoversSummary";
import { money, percent, percentOrNa } from "../lib/money";
import PortfolioSummary, { computePortfolioTotals } from "./PortfolioSummary";
import { translateInstrumentType } from "../lib/instrumentType";
import { useFetch } from "../hooks/useFetch";
import tableStyles from "../styles/table.module.css";
import { useTranslation } from "react-i18next";
import { useConfig } from "../ConfigContext";
import { RelativeViewToggle } from "./RelativeViewToggle";
import metricStyles from "../styles/metrics.module.css";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
  BarChart,
  Bar,
  XAxis,
  YAxis,
} from "recharts";

const PIE_COLORS = [
  "#8884d8",
  "#82ca9d",
  "#ffc658",
  "#ff8042",
  "#8dd1e1",
  "#a4de6c",
  "#d0ed57",
  "#ffc0cb",
];

type SelectedInstrument = {
  ticker: string;
  name: string;
};

type Props = {
  slug: string;
  /** when clicking an owner you may want to jump to the member tab */
  onSelectMember?: (owner: string) => void;
  onTradeInfo?: (info: { trades_this_month?: number; trades_remaining?: number } | null) => void;
};

/* ────────────────────────────────────────────────────────────
 * Component
 * ────────────────────────────────────────────────────────── */
export function GroupPortfolioView({ slug, onSelectMember, onTradeInfo }: Props) {
  const fetchPortfolio = useCallback(() => getGroupPortfolio(slug), [slug]);
  const { data: portfolio, loading, error } = useFetch<GroupPortfolio>(
    fetchPortfolio,
    [slug],
    !!slug
  );
  const fetchSector = useCallback(() => getGroupSectorContributions(slug), [slug]);
  const fetchRegion = useCallback(() => getGroupRegionContributions(slug), [slug]);
  const { data: sectorContrib } = useFetch<SectorContribution[]>(
    fetchSector,
    [slug],
    !!slug
  );
  const { data: regionContrib } = useFetch<RegionContribution[]>(
    fetchRegion,
    [slug],
    !!slug
  );
  const [selected, setSelected] = useState<SelectedInstrument | null>(null);
  const { t } = useTranslation();
  const { relativeViewEnabled } = useConfig();
  const [selectedAccounts, setSelectedAccounts] = useState<string[]>([]);
  const [alpha, setAlpha] = useState<number | null>(null);
  const [trackingError, setTrackingError] = useState<number | null>(null);
  const [maxDrawdown, setMaxDrawdown] = useState<number | null>(null)
