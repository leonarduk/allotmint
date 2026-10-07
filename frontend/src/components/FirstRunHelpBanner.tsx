import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useConfig } from '../ConfigContext';
import { isModeEnabled } from '../pageManifest';
import { visibleHelpPages } from '../lib/helpPages';
import { loadJSON, saveJSON } from '../utils/storage';

// Persisted once the user dismisses the banner so it never reappears (#7827).
export const FIRST_RUN_HELP_DISMISSED_KEY = 'allotmint.firstRunHelpDismissed';

// The handful of pages a first-time user most needs pointing at. Their copy
// comes from HELP_PAGES so the banner and the Help page cannot drift.
const KEY_PAGE_PATHS = ['/', '/allocation', '/performance'];

/**
 * Inline, non-blocking orientation banner for the dashboard. Points new users
 * at the Help page and glossary, which otherwise live behind the Settings menu.
 */
export function FirstRunHelpBanner() {
  const { t } = useTranslation();
  const { tabs, disabledTabs } = useConfig();
  const [dismissed, setDismissed] = useState(() =>
    loadJSON<boolean>(FIRST_RUN_HELP_DISMISSED_KEY, false)
  );

  if (dismissed || !isModeEnabled('help', tabs, disabledTabs)) return null;

  const keyPages = visibleHelpPages(tabs, disabledTabs).filter((entry) =>
    KEY_PAGE_PATHS.includes(entry.path)
  );

  const dismiss = () => {
    setDismissed(true);
    try {
      saveJSON(FIRST_RUN_HELP_DISMISSED_KEY, true);
    } catch (err) {
      // Storage can be blocked (private mode, quota); the banner still hides
      // for this session, it just may show again on the next visit.
      console.warn('Could not persist first-run help dismissal', err);
    }
  };

  return (
    <section
      aria-label={t('firstRunHelp.title', 'New to AllotMint?')}
      className="mb-4 rounded p-4 text-sm"
      style={{
        // Theme variables (not Tailwind dark:) so it follows the in-app
        // light/dark toggle, matching the summary cards around it.
        background: 'var(--summary-card-bg)',
        border: '1px solid var(--summary-card-border)',
        color: 'var(--summary-card-value)',
      }}
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        {/* Grows to fill the row but wraps the dismiss button below it on
            narrow screens instead of squeezing the copy into a sliver. */}
        <div className="space-y-2" style={{ flex: '1 1 16rem', minWidth: 0 }}>
          <h2 className="text-base font-semibold">
            {t('firstRunHelp.title', 'New to AllotMint?')}
          </h2>
          <p>
            {t(
              'help.intro',
              'A quick guide to what each page in AllotMint is for, plus how to look up unfamiliar terms and how to report a problem.'
            )}
          </p>
          {keyPages.length > 0 && (
            <ul className="list-disc space-y-1 pl-5">
              {keyPages.map((entry) => (
                <li key={entry.path}>
                  <Link to={entry.path} className="font-medium">
                    {t(entry.titleKey, entry.titleDefault)}
                  </Link>
                  {': '}
                  <span>
                    {t(entry.descriptionKey, entry.descriptionDefault)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <div className="flex flex-wrap gap-3">
            <Link to="/help" className="px-1 py-1 font-semibold">
              {t('firstRunHelp.openHelp', 'Open Help & Getting Started')}
            </Link>
            <Link to="/metrics-explained" className="px-1 py-1">
              {t('help.glossaryLink', 'Open the metrics glossary')}
            </Link>
          </div>
        </div>
        <button type="button" onClick={dismiss} className="shrink-0">
          {t('firstRunHelp.dismiss', "Got it, don't show again")}
        </button>
      </div>
    </section>
  );
}
