/**
 * External research links for the instrument research page (#10424).
 *
 * Each provider is keyed on data the page already holds (ticker, exchange,
 * ISIN, name, instrument type) and declares which instruments it applies
 * to, so UK-only sites don't appear on US listings and equity-only sites
 * don't appear on funds. A link whose required field is missing is
 * skipped rather than rendered with an empty placeholder.
 */

export type ExternalResearchLinkId =
  | "yahoo"
  | "ft"
  | "lseShareChat"
  | "investegate"
  | "marketBeat"
  | "companiesHouse"
  | "finviz"
  | "edgar";

export interface ExternalResearchLink {
  id: ExternalResearchLinkId;
  url: string;
}

export interface ExternalResearchLinkInput {
  ticker: string;
  exchange?: string | null;
  isin?: string | null;
  name?: string | null;
  instrumentType?: string | null;
}

const ISIN_PATTERN = /^[A-Z]{2}[A-Z0-9]{9}[0-9]$/;

// Yahoo symbol suffix per AllotMint exchange code; US listings take none.
const YAHOO_SUFFIXES: Record<string, string> = {
  L: ".L",
  DE: ".DE",
  TO: ".TO",
  F: ".F",
  N: "",
};

const UK_EXCHANGES = new Set(["L"]);
const US_EXCHANGES = new Set(["N", "NASDAQ", "NYSE", "US"]);

// Listed companies (and investment trusts, which are LSE-listed companies
// with RNS feeds). A missing type is treated as an equity, the common case.
const COMPANY_TYPES = new Set(["", "EQUITY", "INVESTMENT TRUST"]);

/** Strip only the final ".EXCHANGE" segment so BRK.B.N -> BRK.B. */
function baseTickerOf(ticker: string): string {
  const trimmed = ticker.trim().toUpperCase();
  const lastDot = trimmed.lastIndexOf(".");
  return lastDot > 0 ? trimmed.slice(0, lastDot) : trimmed;
}

interface NormalisedInput {
  ticker: string;
  exchange: string;
  isin: string | null;
  name: string;
  type: string;
}

function normalise(input: ExternalResearchLinkInput): NormalisedInput {
  const isin = input.isin?.trim().toUpperCase() ?? "";
  return {
    ticker: baseTickerOf(input.ticker),
    exchange: input.exchange?.trim().toUpperCase() ?? "",
    isin: ISIN_PATTERN.test(isin) ? isin : null,
    name: input.name?.trim() ?? "",
    type: input.instrumentType?.trim().toUpperCase() ?? "",
  };
}

type Builder = (i: NormalisedInput) => string | null;

const q = encodeURIComponent;

const isUkCompany = (i: NormalisedInput) =>
  UK_EXCHANGES.has(i.exchange) && COMPANY_TYPES.has(i.type) && !!i.ticker;
const isUsEquity = (i: NormalisedInput) =>
  US_EXCHANGES.has(i.exchange) && (i.type === "" || i.type === "EQUITY") && !!i.ticker;

const BUILDERS: Record<ExternalResearchLinkId, Builder> = {
  yahoo: (i) => {
    const suffix = YAHOO_SUFFIXES[i.exchange];
    if (suffix === undefined || !i.ticker) return null;
    return `https://uk.finance.yahoo.com/quote/${q(i.ticker + suffix)}`;
  },
  ft: (i) => (i.isin ? `https://markets.ft.com/data/search?query=${q(i.isin)}` : null),
  lseShareChat: (i) =>
    isUkCompany(i) ? `https://www.lse.co.uk/ShareChat.html?ShareTicker=${q(i.ticker)}` : null,
  investegate: (i) =>
    isUkCompany(i) ? `https://www.investegate.co.uk/company/${q(i.ticker)}` : null,
  marketBeat: (i) =>
    isUkCompany(i) ? `https://www.marketbeat.com/stocks/LON/${q(i.ticker)}/` : null,
  companiesHouse: (i) =>
    isUkCompany(i) && i.name
      ? `https://find-and-update.company-information.service.gov.uk/search/companies?q=${q(i.name)}`
      : null,
  finviz: (i) => (isUsEquity(i) ? `https://finviz.com/quote.ashx?t=${q(i.ticker)}` : null),
  edgar: (i) =>
    isUsEquity(i)
      ? `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${q(i.ticker)}`
      : null,
};

/** Build the external research links that apply to an instrument, in display order. */
export function buildExternalResearchLinks(
  input: ExternalResearchLinkInput,
): ExternalResearchLink[] {
  const normalised = normalise(input);
  return (Object.keys(BUILDERS) as ExternalResearchLinkId[]).flatMap((id) => {
    const url = BUILDERS[id](normalised);
    return url ? [{ id, url }] : [];
  });
}
