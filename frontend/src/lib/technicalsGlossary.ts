/**
 * Plain-English explanations of the technical-analysis terms on the research
 * page's Technicals tab. `short` is the one-liner in each row's InfoTip;
 * `detail` is the fuller entry on /metrics-explained, under the anchor `id`.
 * One list feeds both so the two never drift apart.
 */
export interface GlossaryEntry {
  /** Anchor on /metrics-explained and i18n key suffix. */
  id: string;
  key: string;
  title: string;
  short: string;
  detail: string;
}

export const TECHNICALS_GLOSSARY_ANCHOR = 'technical-analysis';

const entries = [
  {
    id: 'technical-trend',
    key: 'trend',
    title: 'Trend',
    short:
      'Uptrend: the price is above its 50-day average and the 50-day is above the 200-day. Downtrend: both are the other way round. Anything else is mixed.',
    detail:
      'A quick read of direction from the moving averages. Uptrend means the price is above its 50-day average and the 50-day is above the 200-day; downtrend means the price is below the 50-day and the 50-day is below the 200-day. Anything in between is mixed. Moving averages lag the price, so a trend label describes the last few months, not what comes next.',
  },
  {
    id: 'simple-moving-average',
    key: 'movingAverage',
    title: 'Moving average (20, 50, 200-day)',
    short:
      'The average closing price over the last 20, 50 or 200 trading days. The percentage shows how far today’s price is above or below it.',
    detail:
      'The average of the last 20, 50 or 200 daily closes (roughly one month, one quarter and ten months of trading). The 20-day follows the price closely; the 200-day is a slow, long-term reference. “Price −8% vs average” means today’s close is 8% below that average.',
  },
  {
    id: 'golden-death-cross',
    key: 'cross',
    title: 'Golden cross and death cross',
    short:
      'A golden cross is when the 50-day average rises above the 200-day; a death cross is when it falls below. “Death” means the 50 is currently under the 200 — a weakening trend, not a forecast.',
    detail:
      'Named moments when the 50-day moving average crosses the 200-day. Golden cross: the 50-day moves above the 200-day, so recent prices are running higher than the longer-term average. Death cross: the 50-day moves below it. The names sound dramatic, but a death cross only says the medium-term average has dropped under the long-term one. Because both averages lag, a cross often comes after much of the move has happened, and crosses in a sideways market are frequently reversed soon after. The tab shows which side the 50-day is on now and, when it happened within the loaded history, the date of the last cross.',
  },
  {
    id: 'rsi-zones',
    key: 'rsi',
    title: 'RSI (14-day) and its zones',
    short:
      'RSI (0–100) compares recent gains with recent losses over 14 days. 70+ is called overbought and 30 or below oversold: the move has been strong, not that it must reverse.',
    detail:
      'The Relative Strength Index compares the average size of up days with the average size of down days over the last 14 days (Wilder’s method), on a 0–100 scale. Around 50 means gains and losses have been balanced. 70 or above is conventionally called overbought and 30 or below oversold. Those labels describe how one-sided recent moves have been; a strongly trending share can stay overbought or oversold for a long time.',
  },
  {
    id: 'macd',
    key: 'macd',
    title: 'MACD (12/26/9)',
    short:
      'MACD is the gap between 12-day and 26-day exponential averages; the signal line is a 9-day average of MACD. Bullish crossover: MACD rises above the signal line (momentum improving). Bearish: it falls below.',
    detail:
      'Moving Average Convergence Divergence. The MACD line is the 12-day exponential moving average minus the 26-day one; positive means short-term prices are above the longer-term trend. The signal line is a 9-day average of the MACD line, and the histogram is MACD minus signal. A bullish crossover is the MACD line moving above the signal line (momentum picking up); a bearish crossover is it moving below. The values are in the share’s price units, so compare them over time for one share rather than between shares.',
  },
  {
    id: 'bollinger-bands',
    key: 'bollinger',
    title: 'Bollinger bands and %B',
    short:
      'Bands sit two standard deviations above and below the 20-day average. %B shows where the price is between them: 0% at the lower band, 100% at the upper; outside that range it has closed beyond a band.',
    detail:
      'Bollinger bands are drawn two standard deviations above and below the 20-day moving average, so they widen when the price is volatile and narrow when it is calm. %B places today’s close within them: 0% is on the lower band, 50% on the average, 100% on the upper band. Below 0% or above 100% means the close was outside the bands — an unusually large move relative to the last month.',
  },
  {
    id: 'range-52-week',
    key: 'range',
    title: '52-week range',
    short:
      'The highest and lowest closes over the past year. Position in range: 0% means at the low, 100% at the high.',
    detail:
      'The highest and lowest daily closes over the last 365 days, with the dates they happened. “From 52-week high” is how far the current price is below that high. “Position in range” places the price between the low (0%) and the high (100%).',
  },
  {
    id: 'period-returns',
    key: 'returns',
    title: 'Returns',
    short:
      'The change in closing price over 1, 3, 6 and 12 months. Price only: dividends are not included.',
    detail:
      'The change in closing price from the last close on or before the start of the period to the latest close. These are price returns — dividends are not added back — so for a high-yielding share the total return will be higher.',
  },
  {
    id: 'relative-strength',
    key: 'relativeStrength',
    title: 'Relative strength vs benchmark',
    short:
      'The instrument’s return minus its benchmark’s over the same period. Positive means it did better than the benchmark.',
    detail:
      'The instrument’s price return minus its benchmark’s over the same 3 or 12 months, both measured to the same end date. The benchmark is the one used on the Fundamentals tab: the instrument’s own, if set, otherwise a default for its listing exchange. +5% means it beat the benchmark by five percentage points.',
  },
] as const satisfies readonly GlossaryEntry[];

export type TechnicalsTerm = (typeof entries)[number]['key'];

export const TECHNICALS_GLOSSARY: readonly GlossaryEntry[] = entries;

export const technicalsTerm = (key: TechnicalsTerm): GlossaryEntry =>
  entries.find((entry) => entry.key === key)!;
