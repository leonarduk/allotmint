/**
 * Plot mode's glossary (#7210): every garden word the skin uses, next to the
 * real term it stands for. Rendered on /metrics-explained under the
 * `PLOT_GUIDE_ANCHOR` section (each entry at its own `id`), and reused as the
 * text of the in-app InfoTips, so a term is defined once and reachable in one
 * click from wherever it appears.
 *
 * Entries already written out by hand on that page (beds, growth stages,
 * condition, holding period, water, feed, sunlight, grower level) are not
 * repeated here.
 */
export interface PlotGlossaryEntry {
  /** Anchor on /metrics-explained. */
  id: string;
  /** i18n key suffix under metricsExplanation.sections.plot. */
  key: string;
  title: string;
  detail: string;
}

export const PLOT_GUIDE_ANCHOR = 'plot-guide';

/** Path to one Plot glossary entry, for InfoTip "Learn more" links. */
export function plotGlossaryPath(id: string): string {
  return `/metrics-explained#${id}`;
}

export const PLOT_GLOSSARY: readonly PlotGlossaryEntry[] = [
  {
    id: 'plot-crop',
    key: 'crop',
    title: 'Crop (a holding)',
    detail:
      'One holding of one investment in one account. The same investment held in two accounts is two crops, shown together where that helps.',
  },
  {
    id: 'plot-plot',
    key: 'plot',
    title: 'Plot (your portfolio)',
    detail:
      "Everything one grower holds, across all of their accounts. The plot's value is the portfolio's total value, cash included.",
  },
  {
    id: 'share-of-plot',
    key: 'shareOfPlot',
    title: 'Share of plot (position size)',
    detail:
      "How much of the plot's total value one crop makes up. It is a size, not a score: a big share is neither good nor bad on its own.",
  },
  {
    id: 'time-held',
    key: 'timeHeld',
    title: 'Time held',
    detail:
      "How long the holding has been held. It sets the crop's growth stage, so its level climbs from 0 to 5 as the crop grows from Sown to Established, and it never goes down while you keep the holding.",
  },
  {
    id: 'todays-move',
    key: 'todaysMove',
    title: "Today's move",
    detail:
      "How much the price has moved today, scored from 0 to 100 where 50 means flat and a 5% move either way reaches the end of the bar. A price confirmed as stale lowers the score. It describes today only and predicts nothing.",
  },
  {
    id: 'chores',
    key: 'chores',
    title: 'Chores (daily tasks)',
    detail:
      'Short tasks such as checking your overview or running a report. Each one opens the page it is about and only counts once you have actually done it there. One-off tasks are set-up jobs you only need to do once. Chores earn XP.',
  },
  {
    id: 'streak',
    key: 'streak',
    title: 'Streak',
    detail:
      'The number of days in a row on which every daily chore was finished.',
  },
  {
    id: 'crate',
    key: 'crate',
    title: 'Crate',
    detail:
      "The week's reward at the end of the streak path. It fills when you finish every chore on every day of the week.",
  },
  {
    id: 'season',
    key: 'season',
    title: 'Season (the UK tax year)',
    detail:
      'Runs from 6 April to 5 April, the same year that ISA and pension allowances reset on. Season goals are tiered milestones for plot size, plot value, allowance use, streak and rank.',
  },
  {
    id: 'grower-rank',
    key: 'growerRank',
    title: 'Grower rank',
    detail:
      'A title for your grower level: Seedling Sower, then Weekend Grower from level 4, Seasoned Digger from 8, Plotholder from 15, Master Grower from 25 and Head Gardener from 40. It reflects chores done, not how your investments have performed.',
  },
  {
    id: 'star-grower',
    key: 'starGrower',
    title: 'Star grower and Needs attention',
    detail:
      "Star grower is the crop with the highest total gain. Needs attention only appears when something is actually wrong: the holding can't be sold yet, its price is stale, or it is down by 5% or more.",
  },
  {
    id: 'next-job',
    key: 'nextJob',
    title: 'Next job on the plot',
    detail:
      'One fact from your own data worth looking at, such as stale prices or unused ISA allowance, with a link to the page that deals with it. It is never a suggestion to buy or sell.',
  },
  {
    id: 'seed-shed',
    key: 'seedShed',
    title: 'Seed shed (your watchlist)',
    detail:
      'The same watchlist as the classic Watchlist page, priced from live quotes. Nothing there places a trade.',
  },
];

const BY_KEY = new Map(PLOT_GLOSSARY.map((entry) => [entry.key, entry]));

/** The glossary entry for `key`; throws on a typo so a tip can't go blank. */
export function plotGlossaryEntry(key: string): PlotGlossaryEntry {
  const entry = BY_KEY.get(key);
  if (!entry) throw new Error(`Unknown Plot glossary key: ${key}`);
  return entry;
}
