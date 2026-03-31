import type { InstrumentSummary } from "../types";

const CSV_HEADERS = [
  "ticker",
  "name",
  "grouping",
  "exchange",
  "currency",
  "instrument_type",
  "units",
  "market_value_gbp",
  "gain_gbp",
  "gain_pct",
];

const sanitizeFilenamePart = (value: string): string =>
  value.replaceAll(/[^a-zA-Z0-9_-]/g, "_");

const escapeCsvCell = (value: string | number | null | undefined): string => {
  const cell = value == null ? "" : String(value);
  const escaped = cell.replaceAll('"', '""');
  return `"${escaped}"`;
};

const escapeHtml = (value: string | number | null | undefined): string => {
  const text = value == null ? "" : String(value);
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
};

const formatNumber = (value: number | null | undefined): string => {
  if (value == null || Number.isNaN(value)) return "";
  return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
};

const buildInstrumentCsv = (instruments: InstrumentSummary[]): string => {
  const rows = instruments.map((instrument) => [
    instrument.ticker,
    instrument.name,
    instrument.grouping ?? "",
    instrument.exchange ?? "",
    instrument.currency ?? "",
    instrument.instrument_type ?? "",
    instrument.units,
    instrument.market_value_gbp,
    instrument.gain_gbp,
    instrument.gain_pct ?? "",
  ]);

  const csvRows = [
    CSV_HEADERS.map(escapeCsvCell).join(","),
    ...rows.map((row) => row.map(escapeCsvCell).join(",")),
  ];

  return `${csvRows.join("\r\n")}\r\n`;
};

const buildInstrumentPrintHtml = (
  instruments: InstrumentSummary[],
  groupLabel: string,
): string => {
  const instrumentRows = instruments.map((instrument) => {
    const cells = [
      instrument.ticker,
      instrument.name,
      instrument.grouping ?? "",
      instrument.exchange ?? "",
      instrument.currency ?? "",
      instrument.instrument_type ?? "",
      formatNumber(instrument.units),
      formatNumber(instrument.market_value_gbp),
      formatNumber(instrument.gain_gbp),
      formatNumber(instrument.gain_pct),
    ];
    const rowHtml = cells.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("");
    return `<tr>${rowHtml}</tr>`;
  });

  const tableBody = instrumentRows.length
    ? instrumentRows.join("")
    : '<tr><td colspan="10">No instruments available.</td></tr>';

  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Instrument export ${escapeHtml(groupLabel)}</title>
    <style>
      @page { size: A4; margin: 12mm; }
      body { font-family: Inter, Arial, sans-serif; margin: 0; color: #111827; }
      h1 { margin: 0 0 8px; font-size: 20px; }
      p { margin: 0 0 14px; color: #374151; }
      table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 10px; }
      th, td { border: 1px solid #d1d5db; padding: 4px; text-align: left; vertical-align: top; word-break: break-word; }
      th { background: #f3f4f6; font-weight: 700; }
    </style>
  </head>
  <body>
    <h1>Instrument export: ${escapeHtml(groupLabel)}</h1>
    <p>Generated ${escapeHtml(new Date().toLocaleString())}</p>
    <table>
      <thead>
        <tr>
          <th>Ticker</th>
          <th>Name</th>
          <th>Group</th>
          <th>Exchange</th>
          <th>Currency</th>
          <th>Type</th>
          <th>Units</th>
          <th>Market Value (GBP)</th>
          <th>Gain (GBP)</th>
          <th>Gain %</th>
        </tr>
      </thead>
      <tbody>${tableBody}</tbody>
    </table>
  </body>
</html>`;
};

export const downloadInstrumentsCsv = (
  instruments: InstrumentSummary[],
  groupLabel: string,
): void => {
  const csv = buildInstrumentCsv(instruments);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const safeGroup = sanitizeFilenamePart(groupLabel || "all");
  const safeDate = sanitizeFilenamePart(new Date().toISOString().slice(0, 10));
  link.href = url;
  link.download = `${safeGroup}-instruments-${safeDate}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => URL.revokeObjectURL(url), 250);
};

export const printInstrumentsPdf = (
  instruments: InstrumentSummary[],
  groupLabel: string,
): void => {
  const iframe = document.createElement("iframe");
  iframe.style.position = "fixed";
  iframe.style.right = "0";
  iframe.style.bottom = "0";
  iframe.style.width = "0";
  iframe.style.height = "0";
  iframe.style.border = "0";
  iframe.setAttribute("aria-hidden", "true");
  document.body.appendChild(iframe);

  const cleanup = () => {
    iframe.onload = null;
    if (document.body.contains(iframe)) {
      document.body.removeChild(iframe);
    }
  };

  iframe.onload = () => {
    const printContext = iframe.contentWindow;
    if (!printContext) {
      cleanup();
      return;
    }
    printContext.focus();
    printContext.print();
    window.setTimeout(cleanup, 1200);
  };

  const frameDocument = iframe.contentDocument ?? iframe.contentWindow?.document;
  if (!frameDocument) {
    cleanup();
    return;
  }
  frameDocument.open();
  frameDocument.write(buildInstrumentPrintHtml(instruments, groupLabel));
  frameDocument.close();
};
