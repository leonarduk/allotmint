import styles from '../plot.module.css';
import { usePlotData, type Chore } from '../PlotDataContext';
import RadialProgress from '../components/RadialProgress';
import Meter from '../components/Meter';

function ChoreRow({
  chore,
  onComplete,
}: {
  chore: Chore;
  onComplete: (id: string) => void;
}) {
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
        className={styles.goButton}
        disabled={chore.completed}
        onClick={() => onComplete(chore.id)}
      >
        {chore.completed ? 'Done' : 'Do it'}
      </button>
    </li>
  );
}

/**
 * The chores screen — the quest board, wired to the same Trail/Quests
 * endpoints the classic Trail page uses, so progress is shared between skins.
 */
export default function ChoresScreen() {
  const { chores, choresAvailable, completeChore, snapshot } = usePlotData();

  const daily = chores.filter((chore) => chore.kind === 'daily');
  const once = chores.filter((chore) => chore.kind === 'once');
  const doneToday = daily.filter((chore) => chore.completed).length;
  const pct = daily.length > 0 ? (doneToday / daily.length) * 100 : 0;
  const { grower } = snapshot;

  if (!choresAvailable) {
    return (
      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>Chores</h2>
        <p className={styles.sectionNote}>
          Neither the Trail nor the Quests endpoint is available on this
          deployment, so there is nothing to tick off here yet.
        </p>
      </section>
    );
  }

  return (
    <div className={styles.stack}>
      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>
          Daily chores {doneToday}/{daily.length}
        </h2>
        <div className={styles.pills}>
          <div className={styles.pill}>
            <RadialProgress
              pct={pct}
              value={`${doneToday}/${daily.length}`}
              label="Chores done"
              caption={
                daily.length > 0 && doneToday === daily.length
                  ? 'Plot is tidy'
                  : 'Complete all chores'
              }
            />
          </div>
          <div className={styles.pill}>
            <div className={styles.pillHead}>
              <span>Season XP</span>
              <span className={styles.pillValue}>{grower.xpTotal}</span>
            </div>
            <Meter
              pct={grower.pct}
              label={`Level ${grower.level}, ${grower.xpIntoLevel} of ${grower.xpForLevel} XP to level ${grower.level + 1}`}
            />
            <p className={styles.pillHint}>
              {`Level ${grower.level} · ${grower.xpIntoLevel}/${grower.xpForLevel} XP to level ${grower.level + 1}`}
            </p>
          </div>
          <div className={styles.pill}>
            <div className={styles.pillHead}>
              <span>Streak</span>
              <span className={styles.pillValue}>{snapshot.streak}</span>
            </div>
            <p className={styles.pillHint}>
              Consecutive days with every daily chore finished.
            </p>
          </div>
        </div>
      </section>

      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>Today</h2>
        {daily.length === 0 ? (
          <p className={styles.sectionNote}>No daily chores right now.</p>
        ) : (
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {daily.map((chore) => (
              <ChoreRow
                key={chore.id}
                chore={chore}
                onComplete={completeChore}
              />
            ))}
          </ul>
        )}
      </section>

      {once.length > 0 && (
        <section className={`${styles.panel} ${styles.panelGlow}`}>
          <h2 className={styles.panelTitle}>Groundwork</h2>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {once.map((chore) => (
              <ChoreRow
                key={chore.id}
                chore={chore}
                onComplete={completeChore}
              />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
