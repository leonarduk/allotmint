/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  completeQuest,
  completeTrailTask,
  getAllowances,
  getOwners,
  getPortfolio,
  getQuests,
  getTrailTasks,
} from '../api';
import type {
  OwnerSummary,
  Portfolio,
  QuestResponse,
  TrailResponse,
} from '../types';
import {
  buildPlotSnapshot,
  type AllowanceMap,
  type PlotSnapshot,
} from './plotModel';
import { parseTaxYear, type DailyTotals, type Season } from './seasonModel';

/** A chore is either a Trail task or a daily Quest, normalised for the UI. */
export interface Chore {
  id: string;
  title: string;
  note: string | null;
  kind: 'daily' | 'once';
  completed: boolean;
  /** Only quests expose a per-task XP value; Trail tasks leave this null. */
  xp: number | null;
  source: 'trail' | 'quest';
}

export interface PlotDataValue {
  loading: boolean;
  /** Fatal error — the portfolio itself could not be loaded. */
  error: string | null;
  owner: string;
  owners: OwnerSummary[];
  setOwner: (owner: string) => void;
  snapshot: PlotSnapshot;
  chores: Chore[];
  choresAvailable: boolean;
  /**
   * Returns the promise for this specific completion attempt (#7188), so a
   * caller (ChoresScreen) can track a per-chore pending state and surface a
   * rejection as an inline error, while the chain internally always
   * continues to the next queued completion regardless of this one's
   * outcome.
   */
  completeChore: (id: string) => Promise<void>;
  refresh: () => void;
  /** Raw allowance rows, for the season ladder's "feed the beds" goals. */
  allowances: AllowanceMap | null;
  /**
   * True when the last `/tax/allowances` fetch failed (HTTP error, e.g. the
   * upstream 402 billing gate) rather than genuinely returning no data. The
   * FEED meter, the Season page's countdown, and the "Feed the beds"
   * milestone tier all key off this to show one consistent error notice
   * instead of reusing the "no allowances set up" empty-state copy (#7005).
   */
  allowancesUnavailable: boolean;
  /** The UK tax year this plot is in, when the backend reports one. */
  season: Season | null;
  /** Per-day chore totals from the Trail, for the streak path. */
  dailyTotals: DailyTotals | null;
  /** The Trail's idea of today, so the streak path anchors to server time. */
  today: string;
}

const EMPTY_SNAPSHOT = buildPlotSnapshot({ portfolio: null });

const plotDataContext = createContext<PlotDataValue>({
  loading: true,
  error: null,
  owner: '',
  owners: [],
  setOwner: () => {},
  snapshot: EMPTY_SNAPSHOT,
  chores: [],
  choresAvailable: false,
  completeChore: () => Promise.resolve(),
  refresh: () => {},
  allowances: null,
  allowancesUnavailable: false,
  season: null,
  dailyTotals: null,
  today: '',
});

export function usePlotData(): PlotDataValue {
  return useContext(plotDataContext);
}

function choresFromTrail(payload: TrailResponse): Chore[] {
  return payload.tasks.map((task) => ({
    id: task.id,
    title: task.title,
    note: task.commentary || null,
    kind: task.type === 'once' ? 'once' : 'daily',
    completed: task.completed,
    xp: null,
    source: 'trail' as const,
  }));
}

function choresFromQuests(payload: QuestResponse): Chore[] {
  return payload.quests.map((quest) => ({
    id: quest.id,
    title: quest.title,
    note: null,
    kind: 'daily' as const,
    completed: quest.completed,
    xp: quest.xp,
    source: 'quest' as const,
  }));
}

interface ProgressState {
  chores: Chore[];
  xp: number;
  streak: number;
  source: 'trail' | 'quest' | null;
  dailyTotals: DailyTotals | null;
  today: string;
}

const EMPTY_PROGRESS: ProgressState = {
  chores: [],
  xp: 0,
  streak: 0,
  source: null,
  dailyTotals: null,
  today: '',
};

/** Local-clock fallback for the streak path when the Trail omits `today`. */
function localToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function progressFromTrail(trail: TrailResponse): ProgressState {
  return {
    chores: choresFromTrail(trail),
    xp: trail.xp ?? 0,
    streak: trail.streak ?? 0,
    source: 'trail',
    dailyTotals: trail.daily_totals ?? null,
    today: trail.today || localToday(),
  };
}

function progressFromQuests(quests: QuestResponse): ProgressState {
  // The Quests endpoint has no per-day history, so the streak path is simply
  // absent on that fallback rather than being reconstructed from a guess.
  return {
    chores: choresFromQuests(quests),
    xp: quests.xp ?? 0,
    streak: quests.streak ?? 0,
    source: 'quest',
    dailyTotals: null,
    today: localToday(),
  };
}

/**
 * Load the Trail tasks, falling back to the simpler Quests endpoint when the
 * Trail surface is not deployed. Both feed the same XP/streak HUD, so a
 * deployment with either one still gets a working progression loop.
 */
async function loadProgress(): Promise<ProgressState> {
  try {
    return progressFromTrail(await getTrailTasks());
  } catch {
    // Trail is optional (config tab defaults off); quests are the fallback.
  }

  try {
    return progressFromQuests(await getQuests());
  } catch {
    return EMPTY_PROGRESS;
  }
}

interface PlotDataProviderProps {
  /** Owner to show; when omitted the first owner from /owners is used. */
  requestedOwner?: string | null;
  children: ReactNode;
}

export function PlotDataProvider({
  requestedOwner,
  children,
}: PlotDataProviderProps) {
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  // Discovery status is tracked apart from the list: an empty list and a
  // failed request both leave `owners` empty, and only one of them should
  // stop the spinner with "no growers found".
  const [ownersStatus, setOwnersStatus] = useState<
    'pending' | 'ready' | 'error'
  >('pending');
  const [owner, setOwner] = useState(requestedOwner ?? '');
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [allowances, setAllowances] = useState<AllowanceMap | null>(null);
  const [allowancesUnavailable, setAllowancesUnavailable] = useState(false);
  const [season, setSeason] = useState<Season | null>(null);
  const [progress, setProgress] = useState<ProgressState>(EMPTY_PROGRESS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  // A `?owner=` change (deep link, or the classic UI's owner selector) wins
  // over whatever the provider previously settled on.
  useEffect(() => {
    if (requestedOwner) setOwner(requestedOwner);
  }, [requestedOwner]);

  useEffect(() => {
    let cancelled = false;
    setOwnersStatus('pending');
    getOwners()
      .then((list) => {
        if (cancelled) return;
        setOwners(list);
        setOwnersStatus('ready');
        setOwner((current) => current || list[0]?.owner || '');
      })
      .catch(() => {
        // Owner discovery failing is not fatal on its own: an explicit
        // `?owner=` deep link can still load a portfolio below.
        if (cancelled) return;
        setOwners([]);
        setOwnersStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  // Everything below is scoped to one grower. Dropping it whenever the
  // grower changes (and whenever a load fails) stops the HUD from showing the
  // previous grower's money under the new grower's name.
  const clearOwnerScopedState = useCallback(() => {
    setPortfolio(null);
    setAllowances(null);
    setAllowancesUnavailable(false);
    setSeason(null);
    setProgress(EMPTY_PROGRESS);
  }, []);

  const loadedOwnerRef = useRef<string | null>(null);

  // Only the no-owner branch below cares about discovery status. Collapsing it
  // to a constant once an owner is known keeps a refresh (which cycles
  // ownersStatus pending -> ready) from re-running the load twice.
  const discoveryOutcome = owner ? 'has-owner' : ownersStatus;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    if (loadedOwnerRef.current !== owner) {
      clearOwnerScopedState();
      loadedOwnerRef.current = owner;
    }

    if (!owner) {
      // Only stop the spinner once /owners has actually resolved; while it is
      // still in flight there is nothing to report yet.
      if (discoveryOutcome === 'pending') return () => {};
      setLoading(false);
      setError(
        discoveryOutcome === 'error'
          ? 'Could not load the list of growers.'
          : 'No growers found for this account.'
      );
      return () => {};
    }

    Promise.all([
      getPortfolio(owner),
      // A rejected allowances fetch (e.g. the backend's 402 billing gate) is
      // distinct from a genuine 200-with-empty-payload response: the former
      // must surface a "temporarily unavailable" notice, the latter keeps
      // today's "no allowances set up" copy. Tagging the outcome here — rather
      // than collapsing both to `null` via `.catch(() => null)` — is what lets
      // the rest of the HUD tell the two apart (#7005).
      getAllowances(owner).then(
        (value) => ({ ok: true as const, value }),
        () => ({ ok: false as const })
      ),
      loadProgress(),
    ])
      .then(([portfolioResult, allowanceOutcome, progressResult]) => {
        if (cancelled) return;
        setPortfolio(portfolioResult as Portfolio);
        setAllowances(
          allowanceOutcome.ok
            ? ((allowanceOutcome.value.allowances as
                | AllowanceMap
                | undefined) ?? null)
            : null
        );
        setSeason(
          allowanceOutcome.ok ? parseTaxYear(allowanceOutcome.value.tax_year) : null
        );
        setAllowancesUnavailable(!allowanceOutcome.ok);
        setProgress(progressResult);
        setLoading(false);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        clearOwnerScopedState();
        setError(cause instanceof Error ? cause.message : String(cause));
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [owner, discoveryOutcome, reloadToken, clearOwnerScopedState]);

  // Each response is a whole server-side snapshot, so two in flight at once
  // resolve last-write-wins and an out-of-order pair can un-tick a chore that
  // did complete. Chaining keeps at most one request in flight, which makes
  // the last response we apply the freshest one.
  const completionChain = useRef<Promise<unknown>>(Promise.resolve());

  const completeChore = useCallback(
    (id: string): Promise<void> => {
      const chore = progress.chores.find((item) => item.id === id);
      if (!chore || chore.completed) return Promise.resolve();
      // This attempt's promise is handed back to the caller (below) so it can
      // reject and drive a per-row pending/error state (#7188). The chain
      // itself must never reject, though — it always resolves via the
      // trailing `.catch(() => {})` so a failure here doesn't wedge whatever
      // completion is clicked next; not optimistically updating `progress`
      // on failure is what keeps the row from showing a false "done" state.
      const attempt = completionChain.current.then(
        (): Promise<void> =>
          (chore.source === 'trail'
            ? completeTrailTask(id)
            : completeQuest(id)
          ).then((payload) => {
            setProgress(
              chore.source === 'trail'
                ? progressFromTrail(payload as TrailResponse)
                : progressFromQuests(payload as QuestResponse)
            );
          })
      );
      completionChain.current = attempt.catch(() => {});
      return attempt;
    },
    [progress.chores]
  );

  const refresh = useCallback(() => setReloadToken((token) => token + 1), []);

  const snapshot = useMemo(
    () =>
      buildPlotSnapshot({
        portfolio,
        xp: progress.xp,
        streak: progress.streak,
        allowances,
        allowancesUnavailable,
      }),
    [portfolio, progress.xp, progress.streak, allowances, allowancesUnavailable]
  );

  const value = useMemo<PlotDataValue>(
    () => ({
      loading,
      error,
      owner,
      owners,
      setOwner,
      snapshot,
      chores: progress.chores,
      choresAvailable: progress.source !== null,
      completeChore,
      refresh,
      allowances,
      allowancesUnavailable,
      season,
      dailyTotals: progress.dailyTotals,
      today: progress.today,
    }),
    [
      loading,
      error,
      owner,
      owners,
      snapshot,
      progress.chores,
      progress.source,
      progress.dailyTotals,
      progress.today,
      allowances,
      allowancesUnavailable,
      season,
      completeChore,
      refresh,
    ]
  );

  return (
    <plotDataContext.Provider value={value}>
      {children}
    </plotDataContext.Provider>
  );
}

export { plotDataContext };
