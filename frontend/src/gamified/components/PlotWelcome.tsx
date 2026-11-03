import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import styles from '../plot.module.css';
import { PLOT_GUIDE_ANCHOR, plotGlossaryPath } from '../../lib/plotGlossary';

/** Remembers, per browser, that this viewer has dismissed the welcome. */
export const PLOT_WELCOME_STORAGE_KEY = 'allotmint:plotWelcomeDismissed';

function readDismissed(): boolean {
  try {
    return window.localStorage.getItem(PLOT_WELCOME_STORAGE_KEY) === '1';
  } catch {
    // Storage blocked (private mode): show the welcome; it stays dismissible
    // for this page view.
    return false;
  }
}

function writeDismissed(): void {
  try {
    window.localStorage.setItem(PLOT_WELCOME_STORAGE_KEY, '1');
  } catch {
    // Nothing to do: the welcome still hides for this page view.
  }
}

const STEP_KEYS = [
  'plot.welcome.stepCrops',
  'plot.welcome.stepGrowth',
  'plot.welcome.stepMeters',
  'plot.welcome.stepChores',
] as const;

/**
 * First-visit walkthrough for the hub (#7210): what the garden words stand
 * for, shown before the scoreboard. Inline rather than a modal, so it never
 * blocks the hub, and dismissed for good with one button.
 */
export default function PlotWelcome() {
  const { t } = useTranslation();
  const [dismissed, setDismissed] = useState(readDismissed);
  if (dismissed) return null;

  const dismiss = () => {
    writeDismissed();
    setDismissed(true);
  };

  return (
    <section
      className={`${styles.panel} ${styles.panelGlow}`}
      aria-labelledby="plot-welcome-title"
    >
      <h2 id="plot-welcome-title" className={styles.panelTitle}>
        {t('plot.welcome.title')}
      </h2>
      <p className={styles.sectionNote}>{t('plot.welcome.intro')}</p>
      <ol className={styles.welcomeSteps}>
        {STEP_KEYS.map((key) => (
          <li key={key}>{t(key)}</li>
        ))}
      </ol>
      <div className={styles.welcomeActions}>
        <Link className={styles.chipButton} to={plotGlossaryPath(PLOT_GUIDE_ANCHOR)}>
          {t('plot.welcome.readGuide')}
        </Link>
        <button type="button" className={styles.goButton} onClick={dismiss}>
          {t('plot.welcome.dismiss')}
        </button>
      </div>
    </section>
  );
}
