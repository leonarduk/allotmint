import type { Portfolio } from "../types";

export type PortfolioExportData = Pick<Portfolio, "owner" | "as_of" | "accounts">;

export const CSV_HEADERS = [
  "owner", "as_of", "account_type", "ticker", "name", "units", "currency",
  "market_value_gbp", "gain_gbp", "gain_pct",
];

const sanitizeFilenamePart = (value: string): string =>
  value.replaceAll(/[^a-zA-Z0-9_-]/g, "_");

const escapeCsvCell = (value: string | number | null | undefined): string => {
  const cell = value == null ? "" : String(value);
  return `"${cell.replaceAll('"', '""')}"`;
};

export const buildPortfolioCsv = (portfolio: PortfolioExportData): string => {
  const rows = portfolio.accounts.flatMap((account) =>
    account.holdings.map((holding) => [
      portfolio.owner, portfolio.as_of, account.account_type, holding.ticker,
      holding.name, holding.units, holding.currency ?? account.currency ?? "",
      holding.market_value_gbp ?? "", holding.gain_gbp ?? "", holding.gain_pct ?? "",
    ]),
  );
  return `${[
    CSV_HEADERS.map(escapeCsvCell).join(","),
    ...rows.map((row) => row.map(escapeCsvCell).join(",")),
  ].join("\r\n")}\r\n`;
};

export const downloadPortfolioCsv = (portfolio: PortfolioExportData): void => {
  const blob = new Blob([buildPortfolioCsv(portfolio)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${sanitizeFilenamePart(portfolio.owner)}-portfolio-${sanitizeFilenamePart(portfolio.as_of)}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => URL.revokeObjectURL(url), 250);
};

const escapeHtml = (value: string | number | null | undefined): string => {
  const text = value == null ? "" : String(value);
  return text.replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
};

const formatNumber = (value: number | null | undefined): string =>
  value == null || Number.isNaN(value)
    ? ""
    : value.toLocaleString(undefined, { maximumFractionDigits: 2 });

export const buildPortfolioPrintHtml = (portfolio: PortfolioExportData): string => {
  const holdingsRows = portfolio.accounts.flatMap((account) =>
    account.holdings.map((holding) => `<tr>${[
      account.account_type, holding.ticker, holding.name, formatNumber(holding.units),
      holding.currency ?? account.currency ?? "", formatNumber(holding.market_value_gbp),
      formatNumber(holding.gain_gbp), formatNumber(holding.gain_pct),
    ].map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`),
  );
  const tableBody = holdingsRows.length
    ? holdingsRows.join("")
    : '<tr><td colspan="8">No holdings available.</td></tr>';
  return `<!doctype html><html><head><meta charset="utf-8" /><title>${escapeHtml(portfolio.owner)} portfolio ${escapeHtml(portfolio.as_of)}</title><style>@page { size: A4; margin: 12mm; } body { font-family: Inter, Arial, sans-serif; margin: 0; color: #111827; } h1 { margin: 0 0 8px; font-size: 20px; } p { margin: 0 0 14px; color: #374151; } table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 11px; } th, td { border: 1px solid #d1d5db; padding: 6px; text-align: left; vertical-align: top; word-break: break-word; } th { background: #f3f4f6; font-weight: 700; }</style></head><body><h1>Portfolio export: ${escapeHtml(portfolio.owner)}</h1><p>As of ${escapeHtml(portfolio.as_of)} • Generated ${escapeHtml(new Date().toLocaleString())}</p><table><thead><tr><th>Account</th><th>Ticker</th><th>Name</th><th>Units</th><th>Currency</th><th>Market Value (GBP)</th><th>Gain (GBP)</th><th>Gain %</th></tr></thead><tbody>${tableBody}</tbody></table></body></html>`;
};

export const printPortfolioPdf = (portfolio: PortfolioExportData): void => {
  const iframe = document.createElement("iframe");
  Object.assign(iframe.style, { position: "fixed", right: "0", bottom: "0", width: "0", height: "0", border: "0" });
  iframe.setAttribute("aria-hidden", "true");
  document.body.appendChild(iframe);
  const cleanup = () => {
    iframe.onload = null;
    if (document.body.contains(iframe)) document.body.removeChild(iframe);
  };
  iframe.onload = () => {
    const printContext = iframe.contentWindow;
    if (!printContext) return cleanup();
    printContext.focus();
    printContext.print();
    window.setTimeout(cleanup, 1200);
  };
  const frameDocument = iframe.contentDocument ?? iframe.contentWindow?.document;
  if (!frameDocument) return cleanup();
  frameDocument.open();
  frameDocument.write(buildPortfolioPrintHtml(portfolio));
  frameDocument.close();
};
