export const FTSE100 = [
  "AAL.L",
  "ABF.L",
  "ADM.L",
  "AHT.L",
  "ANTO.L",
];

export const FTSE250 = [
  "ASC.L",
  "BME.L",
  "CINE.L",
  "DOM.L",
  "EZJ.L",
];

export const FTSE350 = [...FTSE100, ...FTSE250];

export const FTSEAllShare = [...FTSE350];

export const WATCHLISTS = {
  "FTSE 100": FTSE100,
  "FTSE 250": FTSE250,
  "FTSE 350": FTSE350,
  "FTSE All-Share": FTSEAllShare,
} as const;

export type WatchlistName = keyof typeof WATCHLISTS;
