import { useTranslation } from 'react-i18next';

/**
 * Persistent banner shown for the whole session while `demoReadOnly` is
 * true (issue #7410). This is a courtesy signal only — it is not the
 * enforcement boundary. The server-side gates (#7407, #7408) are what
 * actually make a demo-scoped token read-only; hiding/disabling individual
 * mutating controls is #7411, deliberately not this component's job.
 */
export default function DemoReadOnlyBanner() {
  const { t } = useTranslation();

  return (
    <div
      role="status"
      data-testid="demo-readonly-banner"
      className="demo-readonly-banner"
    >
      {t('demo.readOnlyBanner', 'Read-only demo — sign in to use AllotMint')}
    </div>
  );
}
