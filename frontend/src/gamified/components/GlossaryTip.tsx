import { useTranslation } from 'react-i18next';
import InfoTip from '../../components/InfoTip';
import { plotGlossaryEntry, plotGlossaryPath } from '../../lib/plotGlossary';

/**
 * An InfoTip whose text is the term's Plot glossary entry (#7210), with a
 * "Learn more" link to that entry on /metrics-explained — so every coined
 * word is defined one click from where it appears, in the same words as the
 * glossary.
 */
export default function GlossaryTip({
  glossaryKey,
  term,
}: {
  glossaryKey: string;
  /** The term as shown on screen, for the button's accessible name. */
  term: string;
}) {
  const { t } = useTranslation();
  const entry = plotGlossaryEntry(glossaryKey);
  return (
    <InfoTip
      label={t('plot.hub.whatDoesMean', { term })}
      to={plotGlossaryPath(entry.id)}
    >
      {t(`metricsExplanation.sections.plot.${entry.key}.detail`, entry.detail)}
    </InfoTip>
  );
}
