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
  getGroups,
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
  setOwner: (owner: string) => void;
  snapshot: PlotSnapshot;
  chores: Chore[];
  choresAvailable: boolean;
  completeChore: (id: string) => void;
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
  pickerOwners: [],
  setOwner: () => {},
  snapshot: EMPTY_SNAPSHOT,
  chores: [],
  choresAvailable: false,
  completeChore: () => {},
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

  // `/groups` defines the real household membership (e.g. "adults",
  // "children"); it is what keeps accounts with no household membership —
  // notably the demo/seed account — out of the grower picker below. This is
  // deliberately a separate, non-fatal effect from owner discovery above: a
  // failed or empty `/groups` response must not touch `ownersStatus` or the
  // "no growers found" error path, it should just leave `groups` empty and
  // let `pickerOwners` fall back to showing every owner (#7189).
  //
  // `groupsStatus` mirrors `ownersStatus` above for the same reason: an
  // empty `groups` array is ambiguous between "not loaded yet" and "loaded,
  // no groups configured" and only one of those should make `pickerOwners`
  // fall back to the unfiltered list. Without this, `pickerOwners` briefly
  // equals the full `owners` list (demo account included) the instant
  // `/owners` resolves, then narrows a moment later once `/groups` catches
  // up — the exact "wrong grower's data flashes on screen" class of bug
  // `clearOwnerScopedState` exists to prevent elsewhere in this file.
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [groupsStatus, setGroupsStatus] = useState<
    'pending' | 'ready' | 'error'
  >('pending');

  useEffect(() => {
    let cancelled = false;
    setGroupsStatus('pending');
    getGroups()
      .then((list) => {
        if (cancelled) return;
        setGroups(list);
        setGroupsStatus('ready');
      })
      .catch(() => {
        // Swallowed deliberately: `groups` just stays empty and `ready`'s
        // "no grouping configured" fallback below applies equally to a
        // genuinely-empty response and a failed one.
        if (cancelled) return;
        setGroups([]);
        setGroupsStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  // The set of owner slugs that belong to at least one group. Membership,
  // not an exclusion list, is the rule — this is why the demo account (which
  // simply isn't in any group) drops out without `"demo"` ever being named
  // in this file (#7189).
  const groupedOwnerSlugs = useMemo(() => {
    const slugs = new Set<string>();
    for (const group of groups) {
      for (const member of group.members) slugs.add(member);
    }
    return slugs;
  }, [groups]);

  // The picker's option list: real owners only, with a fall back to the full
  // `owners` list whenever grouping data can't narrow it down (`/groups`
  // failed, or none of the current owners matched any group). While
  // `/groups` is still in flight this deliberately returns an empty list
  // rather than the unfiltered `owners` — see the comment above `groups` —
  // so the picker (which also hides itself below two options) simply stays
  // hidden for that brief window instead of showing every account and then
  // narrowing. `owners` itself is left untouched for the data layer — deep
  // links like `?owner=demo` bypass this list entirely and keep working via
  // the `requestedOwner` effect above (#7189).
  const pickerOwners = useMemo(() => {
    if (groupsStatus === 'pending') return [];
    if (groupedOwnerSlugs.size === 0) return owners;
    const filtered = owners.filter((entry) => groupedOwnerSlugs.has(entry.owner));
    return filtered.length > 0 ? filtered : owners;
  }, [owners, groupedOwnerSlugs, groupsStatus]);

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
    (id: string) => {
      const chore = progress.chores.find((item) => item.id === id);
      if (!chore || chore.completed) return;
      completionChain.current = completionChain.current
        .then((): Promise<unknown> =>
          chore.source === 'trail' ? completeTrailTask(id) : completeQuest(id)
        )
        .then((payload) => {
          setProgress(
            chore.source === 'trail'
              ? progressFromTrail(payload as TrailResponse)
              : progressFromQuests(payload as QuestResponse)
          );
        })
        .catch(() => {
          // Completion is best-effort; the row stays actionable so the user
          // can retry rather than seeing a false "done" state. Swallowing here
          // also keeps one failure from breaking the chain for later clicks.
        });
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
