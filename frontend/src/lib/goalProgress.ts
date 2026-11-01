import type { Goal } from "./goalForm";

/** Projection returned by ``GET/POST /goals/{name}`` (see backend/common/goal_projection.py). */
export type GoalProjection = {
  status: "projected" | "reached" | "insufficient_history" | "not_progressing";
  method: string;
  points: number;
  min_points: number;
  min_days: number;
  history_start: string | null;
  history_end: string | null;
  projected_date: string | null;
  on_track: boolean | null;
  monthly_rate: number | null;
};

export type GoalTrade = { action: string; amount: number; ticker: string };

/** Goal detail; ``progress``/``current_amount`` are null when the amount saved is unknown. */
export type GoalDetail = Goal & {
  progress: number | null;
  current_amount: number | null;
  trades: GoalTrade[] | null;
  projection: GoalProjection | null;
};

/**
 * Parse the "current amount" input. An empty or invalid entry is unknown
 * (null), never 0 -- otherwise an unentered amount would show as 0% (#7829).
 */
export function parseCurrentAmount(raw: string): number | null {
  if (raw.trim() === "") return null;
  const amount = Number(raw);
  return Number.isFinite(amount) && amount >= 0 ? amount : null;
}

/** Progress fraction (0..1) as a whole percentage clamped to 0..100. */
export function progressPercent(progress: number): number {
  if (!Number.isFinite(progress)) return 0;
  return Math.round(Math.min(Math.max(progress, 0), 1) * 100);
}
