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
  getGroupPortfolio,
  getOwners,
  getPortfolio,
  getQuests,
  getTrailTasks,
} from '../api';
import type {
  GroupSummary,
  OwnerSummary,
  Portfolio,
  QuestResponse,
  TrailResponse,
} from '../types';
import i18n from '../i18n';
import { useGroupedOwners } from '../hooks/useGroupedOwners';
import { useAuth } from '../AuthContext';
import { pickDefaultOwner } from '../utils/owners';
import {
  buildPlotSnapshot,
  plotPortfolioFromGroup,
  type AllowanceMap,
  type PlotSnapshot,
} from './plotModel';
import {
  parseTaxYear,
  seasonFromCalendar,
  type DailyTotals,
  type Season,
} from './seasonModel';

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
  /**
   * The full, unfiltered `/owners` response. Default-owner selection and
   * portfolio loading key off this. It is also what lets the picker look up
   * a display name for a deep-linked owner who isn't in `pickerOwners`
   * (e.g. `?owner=demo`) instead of silently mismatching `<select>`'s value
   * against its options — see the note on `pickerOwners` (#7189, #7192).
   */
  owners: OwnerSummary[];
  /**
   * `owners` filtered to whoever actually belongs to a configured group
   * (the real household), for the grower *picker* to render. Empty while
   * `/groups` is still in flight, so the picker can wait for it rather than
   * flashing the unfiltered list (including the demo seed) and then
   * narrowing a moment later. `owners` itself stays untouched — only the
   * picker's option list should hide accounts that sit outside every group
   * (#7189).
   *
   * A caller must still fall back to `owners` for whichever owner is
   * *currently active*, even if that owner has since dropped out of this
   * list (e.g. an explicit `?owner=demo` deep link): filtering the picker
   * must never leave `<select value={owner}>` pointing at an owner that
   * isn't one of its own `<option>`s, or the browser silently reselects
   * whatever option happens to be first — showing one grower's name while
   * another grower's data is on screen (#7192).
   */
  pickerOwners: OwnerSummary[];
  /**
   * Groups the picker offers as one shared plot ("At a glance", "Adults"…),
   * from `/groups` (#7190). Empty while `/groups` is in flight or failed.
   */
  groups: GroupSummary[];
  /**
   * The group whose combined plot is on screen, or null in per-grower mode.
   * While set, the snapshot comes from `/portfolio-group/{slug}` and `owner`
   * is not what is shown (#7190).
   */
  group: string | null;
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
   * FEED meter and the "Feed the beds" milestone group are omitted in that
   * case rather than rendered as empty, unearnable progress (#7195).
   */
  allowancesUnavailable: boolean;
  /**
   * The UK tax year this plot is in: the backend's value when it reports
   * one, otherwise derived from the calendar (#7195). Null until loaded.
   */
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
  pickerOwners: [],
  groups: [],
  group: null,
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

type AllowanceOutcome =
  | { ok: true; value: Awaited<ReturnType<typeof getAllowances>> }
  | { ok: false };

interface ScopeData {
  portfolio: Portfolio;
  allowanceOutcome: AllowanceOutcome;
  progress: ProgressState;
}

/**
 * Load everything one plot needs: a grower's portfolio and allowances, or a
 * group's combined portfolio (#7190).
 *
 * Tax allowances are per person and there is no group endpoint for them, so
 * group mode reports them as unavailable: the FEED meter and the "Feed the
 * beds" goals are left out rather than showing one member's headroom as the
 * household's. `/trail` is the signed-in user's own progress in both modes
 * (#7191), which the HUD already labels "Your progress".
 */
async function loadScope(
  owner: string,
  group: string | null
): Promise<ScopeData> {
  if (group) {
    const [groupPortfolio, progress] = await Promise.all([
      getGroupPortfolio(group),
      loadProgress(),
    ]);
    return {
      portfolio: plotPortfolioFromGroup(groupPortfolio),
      allowanceOutcome: { ok: false },
      progress,
    };
  }
  const [portfolio, allowanceOutcome, progress] = await Promise.all([
    getPortfolio(owner),
    // A rejected allowances fetch (e.g. the backend's 402 billing gate) is
    // distinct from a genuine 200-with-empty-payload response: the former
    // must surface a "temporarily unavailable" notice, the latter keeps
    // today's "no allowances set up" copy. Tagging the outcome here — rather
    // than collapsing both to `null` via `.catch(() => null)` — is what lets
    // the rest of the HUD tell the two apart (#7005).
    getAllowances(owner).then(
      (value): AllowanceOutcome => ({ ok: true, value }),
      (): AllowanceOutcome => ({ ok: false })
    ),
    loadProgress(),
  ]);
  return { portfolio: portfolio as Portfolio, allowanceOutcome, progress };
}

interface PlotDataProviderProps {
  /**
   * Owner to show; when omitted the signed-in user's owner is used, falling
   * back to the first owner from /owners (#10753).
   */
  requestedOwner?: string | null;
  /**
   * Group to show as one combined plot (`?group=`, #7190). When set it wins
   * over the owner; when absent the plot is per grower, exactly as before.
   */
  requestedGroup?: string | null;
  children: ReactNode;
}

export function PlotDataProvider({
  requestedOwner,
  requestedGroup,
  children,
}: PlotDataProviderProps) {
  // Held in state, like `owner`, so moving between Plot screens (whose rail
  // links carry no query string) keeps the group on screen (#7190).
  const [group, setGroup] = useState<string | null>(requestedGroup || null);
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  // Discovery status is tracked apart from the list: an empty list and a
  // failed request both leave `owners` empty, and only one of them should
  // stop the spinner with "no growers found".
  const [ownersStatus, setOwnersStatus] = useState<
    'pending' | 'ready' | 'error'
  >('pending');
  const [owner, setOwner] = useState(requestedOwner ?? '');
  // Read through a ref so a user change doesn't refetch /owners.
  const { user } = useAuth();
  const userRef = useRef(user);
  userRef.current = user;
  // The owner this provider last picked by default (not via ?owner= or the
  // picker), so a late-arriving signed-in user can still replace it (#10753).
  const autoOwnerRef = useRef<string | null>(null);
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
  // `?group=` wins over `?owner=`; an explicit `?owner=` on its own leaves
  // group mode (#7190).
  useEffect(() => {
    if (requestedGroup) {
      setGroup(requestedGroup);
      return;
    }
    if (requestedOwner) {
      setOwner(requestedOwner);
      setGroup(null);
    }
  }, [requestedOwner, requestedGroup]);

  useEffect(() => {
    let cancelled = false;
    setOwnersStatus('pending');
    getOwners()
      .then((list) => {
        if (cancelled) return;
        setOwners(list);
        setOwnersStatus('ready');
        const initial = pickDefaultOwner(list, userRef.current);
        autoOwnerRef.current = initial;
        setOwner((current) => current || initial);
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

  // Re-resolve a default-picked owner when the signed-in user changes (e.g.
  // auth settling after /owners resolved). An explicit ?owner= or a picker
  // choice differs from autoOwnerRef and is left alone.
  useEffect(() => {
    if (requestedOwner || ownersStatus !== 'ready') return;
    if (owner && owner !== autoOwnerRef.current) return;
    const next = pickDefaultOwner(owners, user);
    autoOwnerRef.current = next;
    if (next !== owner) setOwner(next);
  }, [owners, ownersStatus, user, requestedOwner, owner]);

  // `/groups` defines the real household membership (e.g. "adults",
  // "children"); it is what keeps accounts with no household membership —
  // notably the demo/seed account — out of the grower picker below. The
  // fetch, slug computation, and fallback logic all live in
  // `useGroupedOwners` so this provider only has to consume the resulting
  // option list (#7189).
  const { pickerOwners, pickerGroups: groups } = useGroupedOwners(
    owners,
    reloadToken
  );

  // Everything below is scoped to one grower. Dropping it whenever the
  // grower changes (and whenever a load fails) stops the HUD from showing the
  // previous grower's money under the new grower's name. `progress` is reset
  // here too (see `setProgress(EMPTY_PROGRESS)` below), but only as a loading
  // placeholder: `/trail` is the signed-in user's progress, not the grower's
  // (#7191), so the refetch restores the same session-wide values for every
  // grower. The HUD labels them "Your progress", not as the grower's.
  const clearOwnerScopedState = useCallback(() => {
    setPortfolio(null);
    setAllowances(null);
    setAllowancesUnavailable(false);
    setSeason(null);
    setProgress(EMPTY_PROGRESS);
  }, []);

  const loadedOwnerRef = useRef<string | null>(null);

  // Only the no-owner branch below cares about discovery status. Collapsing it
  // to a constant once an owner (or a group, which needs no owner) is known
  // keeps a refresh (which cycles ownersStatus pending -> ready) from
  // re-running the load twice.
  const discoveryOutcome = owner || group ? 'has-owner' : ownersStatus;
  // The owner only matters to the load outside group mode, so a default owner
  // settling while a group is on screen doesn't refetch the group (#7190).
  const loadOwner = group ? '' : owner;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    // A group and a grower are different plots: switching between them
    // clears the old figures just like switching growers does.
    const scopeKey = group ? `group:${group}` : loadOwner;
    if (loadedOwnerRef.current !== scopeKey) {
      clearOwnerScopedState();
      loadedOwnerRef.current = scopeKey;
    }

    if (!loadOwner && !group) {
      // Only stop the spinner once /owners has actually resolved; while it is
      // still in flight there is nothing to report yet.
      if (discoveryOutcome === 'pending') return () => {};
      setLoading(false);
      setError(
        discoveryOutcome === 'error'
          ? i18n.t('plot.data.ownersError')
          : i18n.t('plot.data.noOwners')
      );
      return () => {};
    }

    loadScope(loadOwner, group)
      .then((loaded) => {
        if (cancelled) return;
        const { allowanceOutcome, progress: progressResult } = loaded;
        setPortfolio(loaded.portfolio);
        setAllowances(
          allowanceOutcome.ok
            ? ((allowanceOutcome.value.allowances as
                | AllowanceMap
                | undefined) ?? null)
            : null
        );
        // The API's tax year is an override; the window itself is public,
        // so the countdown still works when the allowances fetch fails or
        // omits it (#7195).
        setSeason(
          (allowanceOutcome.ok
            ? parseTaxYear(allowanceOutcome.value.tax_year)
            : null) ?? seasonFromCalendar(new Date())
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
  }, [loadOwner, group, discoveryOutcome, reloadToken, clearOwnerScopedState]);

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
      pickerOwners,
      groups,
      group,
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
      pickerOwners,
      groups,
      group,
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
