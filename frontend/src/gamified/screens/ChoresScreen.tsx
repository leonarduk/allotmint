import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import styles from '../plot.module.css';
import { usePlotData, type Chore } from '../PlotDataContext';
import RadialProgress from '../components/RadialProgress';
import Meter from '../components/Meter';
import { markChorePending, type TrackedChoreId } from '../../choreCompletion';
import { useAsyncItemState } from '../../hooks/useAsyncItemState';

/**
 * Chores that used to self-complete on click (#7003) now deep-link to the
 * real classic-app flow instead. The ones marked `visitTracked` also set a
 * pending marker (see ../../choreCompletion) so the destination page can
 * mark the chore done once the user actually does the thing — the other two
 * ("Adjust your alert threshold", "Create your first savings goal") already
 * get marked done server-side once real data exists (a custom threshold / a
 * saved goal), so they only need the real link.
 */
const CHORE_LINKS: Record<
  string,
  { path: (owner: string) => string; visitTracked?: TrackedChoreId }
> = {
  check_overview: {
    path: (owner) => (owner ? `/?owner=${encodeURIComponent(owner)}` : '/'),
    visitTracked: 'check_overview',
  },
  research_new_stock: {
    path: () => '/research',
    visitTracked: 'research_new_stock',
  },
  run_a_report: {
    path: () => '/reports',
    visitTracked: 'run_a_report',
  },
  set_alert_threshold: {
    path: () => '/alert-settings',
  },
  create_goal: {
    path: () => '/goals',
  },
};

function ChoreRow({
  chore,
  owner,
  pending,
  error,
  onComplete,
  onNavigate,
}: {
  chore: Chore;
  owner: string;
  /** True while this chore's completion POST is in flight (#7188). */
  pending: boolean;
  /** Message from the most recent failed completion attempt, if any (#7188). */
  error: string | null;
  onComplete: (id: string) => void;
  onNavigate: (path: string) => void;
}) {
  const { t } = useTranslation();
  const link = CHORE_LINKS[chore.id];

  const handleClick = () => {
    if (link) {
      if (link.visitTracked) markChorePending(link.visitTracked);
      onNavigate(link.path(owner));
      return;
    }
    onComplete(chore.id);
  };

  const buttonLabel = chore.completed
    ? t('plot.chores.done')
    : pending
      ? t('plot.chores.completing')
      : link
        ? t('plot.chores.go')
        : error
          ? t('plot.chores.tryAgain')
          : t('plot.chores.doIt');
  const errorId = `chore-error-${chore.id}`;
  const showError = Boolean(error) && !chore.completed;

  return (
    <li
      className={`${styles.choreRow} ${chore.completed ? styles.choreRowDone : ''}`}
    >
      <div className={styles.choreBody}>
        <div
          className={`${styles.choreTitle} ${
            chore.completed ? styles.choreTitleDone : ''
          }`}
        >
          {chore.title}
        </div>
        {chore.note && <p className={styles.choreNote}>{chore.note}</p>}
      </div>
      {chore.xp !== null && (
        <span className={styles.choreReward}>
          <span aria-hidden="true">✦</span> {chore.xp} XP
        </span>
      )}
      <button
        type="button"
        className={
          pending ? `${styles.goButton} ${styles.goButtonPending}` : styles.goButton
        }
        // #7188 finding 1: only `chore.completed` disables the button.
        // Disabling on `pending` too used to blur focus the instant the
        // user activated it (browsers blur an element that becomes
        // disabled), dumping keyboard/screen-reader focus on <body> right
        // as a failure needed to be seen. Re-entry while pending is guarded
        // in `handleComplete` instead, so the click is a no-op rather than
        // a second request, without moving focus anywhere.
        disabled={chore.completed}
        aria-busy={pending}
        aria-describedby={showError ? errorId : undefined}
        onClick={handleClick}
      >
        {buttonLabel}
      </button>
      {/* #7188 finding 2: `aria-busy` is an element state, not an
          announcement, and it would only be spoken if focus were still on
          the button — which the fix above preserves, but relying on that
          alone is fragile (e.g. focus already moved for another reason).
          An always-mounted sr-only status region makes the pending/settled
          transition audible regardless, matching the .srOnly + role="status"
          pattern already used elsewhere (see PlotApp.tsx, SeedCatalogue.tsx). */}
      <span className={styles.srOnly} role="status">
        {pending ? t('plot.chores.completingTitle', { title: chore.title }) : ''}
      </span>
      {/* #7188 finding 4: the error used to be an unassociated sibling —
          announced once via role="alert" but with nothing tying it to the
          "Try again" button for a user who tabs back to it later.
          aria-describedby above links the two. */}
      {showError && (
        <p id={errorId} className={styles.choreError} role="alert">
          {error}
        </p>
      )}
    </li>
  );
}

/**
 * The chores screen — the quest board, wired to the same Trail/Quests
 * endpoints the classic Trail page uses, so progress is shared between skins.
 */
export default function ChoresScreen() {
  const { t } = useTranslation();
  const { chores, choresAvailable, completeChore, snapshot, owner } =
    usePlotData();
  const navigate = useNavigate();

  // Per-chore pending/error UI state for #7188. The pending/error *id sets* live
  // in the reusable `useAsyncItemState` hook (see ../../hooks/useAsyncItemState)
  // rather than in PlotDataContext, because this is purely presentational —
  // PlotDataContext's `completeChore` already tracks the single in-flight
  // completion chain for correctness; this just reflects that back per row.
  // The human-readable error copy stays local to this screen: the hook only
  // tracks *which* id errored, not the message to show for it.
  const { pendingIds, errorIds, start, succeed, fail } = useAsyncItemState();
  const [errorMessages, setErrorMessages] = useState<Record<string, string>>({});

  const handleComplete = useCallback(
    (id: string) => {
      // #7188 finding 1: the button is no longer natively `disabled` while
      // pending (that used to blur focus on click), so a second Enter/click
      // on the same row while its request is still in flight has to be
      // guarded here instead — a no-op, not a second POST.
      if (pendingIds.has(id)) return;
      setErrorMessages((prev) => {
        if (!(id in prev)) return prev;
        const next = { ...prev };
        delete next[id];
        return next;
      });
      start(id);
      completeChore(id)
        .then(() => {
          succeed(id);
        })
        .catch((cause: unknown) => {
          // #7188 finding 5: log the actual cause instead of discarding it —
          // otherwise an expired session (401), a stale chore id (404) and a
          // dropped connection are all indistinguishable, and the row's
          // generic copy is all anyone has to go on when reporting a bug.
          console.error(`Failed to complete chore "${id}"`, cause);
          const status = (cause as { status?: number } | null | undefined)
            ?.status;
          const message =
            status === 401
              ? t('plot.chores.sessionExpired')
              : cause instanceof Error && cause.message
                ? cause.message
                : t('plot.chores.completeFailed');
          setErrorMessages((prev) => ({ ...prev, [id]: message }));
          fail(id);
        });
    },
    [completeChore, pendingIds, start, succeed, fail, t]
  );

  const daily = chores.filter((chore) => chore.kind === 'daily');
  const once = chores.filter((chore) => chore.kind === 'once');
  const doneToday = daily.filter((chore) => chore.completed).length;
  const pct = daily.length > 0 ? (doneToday / daily.length) * 100 : 0;
  const { grower } = snapshot;

  if (!choresAvailable) {
    return (
      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>{t('plot.chores.title')}</h2>
        <p className={styles.sectionNote}>
          {t('plot.chores.unavailable')}
        </p>
      </section>
    );
  }

  return (
    <div className={styles.stack}>
      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>
          {t('plot.chores.dailyChores')} {doneToday}/{daily.length}
        </h2>
        <div className={styles.pills}>
          <div className={styles.pill}>
            <RadialProgress
              pct={pct}
              value={`${doneToday}/${daily.length}`}
              label={t('plot.chores.choresDone')}
              caption={
                daily.length > 0 && doneToday === daily.length
                  ? t('plot.chores.plotTidy')
                  : t('plot.chores.completeAll')
              }
            />
          </div>
          <div className={styles.pill}>
            <div className={styles.pillHead}>
              <span>{t('plot.chores.seasonXp')}</span>
              <span className={styles.pillValue}>{grower.xpTotal}</span>
            </div>
            <Meter
              pct={grower.pct}
              label={t('plot.chores.meterLabel', {
                level: grower.level,
                xp: grower.xpIntoLevel,
                xpForLevel: grower.xpForLevel,
                nextLevel: grower.level + 1,
              })}
            />
            <p className={styles.pillHint}>
              {t('plot.chores.levelHint', {
                level: grower.level,
                xp: grower.xpIntoLevel,
                xpForLevel: grower.xpForLevel,
                nextLevel: grower.level + 1,
              })}
            </p>
          </div>
          <div className={styles.pill}>
            <div className={styles.pillHead}>
              <span>{t('plot.chores.streak')}</span>
              <span className={styles.pillValue}>{snapshot.streak}</span>
            </div>
            <p className={styles.pillHint}>
              {t('plot.chores.streakHint')}
            </p>
          </div>
        </div>
      </section>

      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>{t('plot.chores.today')}</h2>
        {daily.length === 0 ? (
          <p className={styles.sectionNote}>{t('plot.chores.noDaily')}</p>
        ) : (
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {daily.map((chore) => (
              <ChoreRow
                key={chore.id}
                chore={chore}
                owner={owner}
                pending={pendingIds.has(chore.id)}
                error={
                  errorIds.has(chore.id)
                    ? (errorMessages[chore.id] ?? null)
                    : null
                }
                onComplete={handleComplete}
                onNavigate={navigate}
              />
            ))}
          </ul>
        )}
      </section>

      {once.length > 0 && (
        <section className={`${styles.panel} ${styles.panelGlow}`}>
          <h2 className={styles.panelTitle}>{t('plot.chores.groundwork')}</h2>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {once.map((chore) => (
              <ChoreRow
                key={chore.id}
                chore={chore}
                owner={owner}
                pending={pendingIds.has(chore.id)}
                error={
                  errorIds.has(chore.id)
                    ? (errorMessages[chore.id] ?? null)
                    : null
                }
                onComplete={handleComplete}
                onNavigate={navigate}
              />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
