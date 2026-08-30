import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { createInstance } from "i18next";
import type { ReactElement } from "react";
import en from "@/locales/en/translation.json";
import fr from "@/locales/fr/translation.json";

const mockQueryData = [
  { owner: "alice", ticker: "AAA", market_value_gbp: 100 },
];
const mockScreenerData = [
  {
    ticker: "AAA",
    name: "Alpha",
    peg_ratio: 1,
    pe_ratio: 10,
    de_ratio: 0.5,
    fcf: 1000,
    eps: 2,
    gross_margin: 0.4,
    operating_margin: 0.2,
    net_margin: 0.1,
    ebitda_margin: 0.3,
    roa: 0.1,
    roe: 0.2,
    roi: 0.15,
    dividend_yield: 2,
    dividend_payout_ratio: 40,
    beta: 1.2,
    shares_outstanding: 1000,
    float_shares: 800,
    market_cap: 5000,
    high_52w: 150,
    low_52w: 90,
    avg_volume: 2000,
  },
];

vi.mock("@/utils/errorToast", () => ({
  __esModule: true,
  default: vi.fn(),
}));

// Portfolios backing the Custom Query "Tickers" control (issue #7202): the
// UI now derives its ticker checkboxes from each in-scope owner's real
// holdings rather than a hardcoded AAA/BBB/CCC list, so tests need a
// getPortfolio mock that returns holdings per owner.
function makePortfolio(owner: string, tickers: string[]) {
  return {
    owner,
    as_of: "2024-01-01",
    trades_this_month: 0,
    trades_remaining: 0,
    total_value_estimate_gbp: 0,
    accounts: [
      {
        account_type: "ISA",
        currency: "GBP",
        value_estimate_gbp: 0,
        holdings: tickers.map((ticker) => ({
          ticker,
          name: ticker,
          units: 1,
        })),
      },
    ],
  };
}

vi.mock("@/api", () => ({
  API_BASE: "http://api",
  getOwners: vi.fn().mockResolvedValue([
    { owner: "alice", full_name: "Alice Example", accounts: [] },
    { owner: "bob", full_name: "Bob Example", accounts: [] },
  ]),
  getPortfolio: vi.fn(),
  runCustomQuery: vi.fn(),
  saveCustomQuery: vi.fn().mockResolvedValue({}),
  listSavedQueries: vi.fn().mockResolvedValue([
    {
      id: "1",
      name: "Saved1",
      params: {
        start: "2024-01-01",
        end: "2024-01-31",
        owners: ["bob"],
        tickers: ["ZZZ"],
        metrics: ["market_value_gbp"],
      },
    },
  ]),
  getScreener: vi.fn(),
  checkScreenerAvailable: vi.fn().mockResolvedValue(true),
}));

import {
  getOwners,
  getPortfolio,
  getScreener,
  listSavedQueries,
  runCustomQuery,
  checkScreenerAvailable,
} from "@/api";
import { ScreenerQuery } from "@/pages/ScreenerQuery";

function renderWithI18n(ui: ReactElement) {
  const i18n = createInstance();
  i18n.use(initReactI18next).init({
    lng: "en",
    resources: { en: { translation: en }, fr: { translation: fr } },
  });
  const result = render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
  return { i18n, ...result };
}

describe("Screener & Query page", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/");
    vi.resetAllMocks();
    // default API mocks to resolve to empty arrays
    runCustomQuery.mockResolvedValue([]);
    getScreener.mockResolvedValue([]);
    checkScreenerAvailable.mockResolvedValue(true);
    getOwners.mockResolvedValue([
      { owner: "alice", full_name: "Alice Example", accounts: [] },
      { owner: "bob", full_name: "Bob Example", accounts: [] },
    ]);
    // Deliberately NOT "AAA"/"BBB"/"CCC" — those are exactly the strings the
    // hardcoded fallback that issue #7202 removed used to render, so a test
    // fixture reusing them couldn't tell a working derivation from a gutted
    // one. See "PR #7323 review" comment above the fallback's old location
    // in ScreenerQuery.tsx.
    getPortfolio.mockImplementation((owner: string) =>
      Promise.resolve(
        makePortfolio(owner, owner === "alice" ? ["VOD"] : ["PFE"]),
      ),
    );
    listSavedQueries.mockResolvedValue([
      {
        id: "1",
        name: "Saved1",
        params: {
          start: "2024-01-01",
          end: "2024-01-31",
          owners: ["bob"],
          // Deliberately a ticker neither mocked owner holds, to exercise
          // the "selected but not in scope" rendering path (issue #7202
          // follow-up #4): it must still render — greyed/labeled — and stay
          // selected, not silently vanish.
          tickers: ["ZZZ"],
          metrics: ["market_value_gbp"],
        },
      },
    ]);
  });
  it("runs screener and displays results", async () => {
    getScreener.mockResolvedValue(mockScreenerData);
    renderWithI18n(<ScreenerQuery />);

    fireEvent.change(await screen.findByLabelText(en.screener.tickers), {
      target: { value: "AAA" },
    });
    fireEvent.change(screen.getByLabelText(en.screener.maxPeg), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText(en.screener.minRoe), {
      target: { value: "5" },
    });

    fireEvent.click(screen.getAllByRole("button", { name: en.screener.run })[0]);

    const values = await screen.findAllByText("1,000");
    expect(values.length).toBeGreaterThan(0);
    expect(getScreener).toHaveBeenCalledWith(
      ["AAA"],
      expect.objectContaining({ peg_max: 2, roe_min: 5 }),
    );

    fireEvent.change(screen.getByLabelText(en.screener.minDividendYield), {
      target: { value: "1" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: en.screener.run })[0]);

    const values2 = await screen.findAllByText("1,000");
    expect(values2.length).toBeGreaterThan(0);
    expect(getScreener).toHaveBeenCalledWith(["AAA"], { peg_max: 2, roe_min: 5 });
    expect(await screen.findByText("1.2")).toBeInTheDocument();
    expect(getScreener).toHaveBeenCalledWith(
      ["AAA"],
      expect.objectContaining({ peg_max: 2, dividend_yield_min: 1 }),
    );
  });

  it("submits query form and renders results with export links", async () => {
    runCustomQuery.mockResolvedValue(mockQueryData);
    const { i18n } = renderWithI18n(<ScreenerQuery />);

    await screen.findByLabelText("Alice Example");
    await screen.findByLabelText("VOD");

    fireEvent.change(screen.getByLabelText(i18n.t("query.start")), {
      target: { value: "2024-01-01" },
    });
    fireEvent.change(screen.getByLabelText(i18n.t("query.end")), {
      target: { value: "2024-02-01" },
    });

    fireEvent.click(screen.getByLabelText("Alice Example"));
    // Narrowing owners re-scopes and re-fetches the ticker list (it briefly
    // shows the loading state — see the "shows a loading state" behaviour
    // covered elsewhere), so wait for VOD to be present again before
    // clicking it.
    await screen.findByLabelText("VOD");
    fireEvent.click(screen.getByLabelText("VOD"));
    fireEvent.click(screen.getByLabelText(i18n.t("query.metricMarketValueGbp")));

    fireEvent.click(screen.getAllByRole("button", { name: i18n.t("query.run") })[1]);

    expect(runCustomQuery).toHaveBeenCalledWith({
      start: "2024-01-01",
      end: "2024-02-01",
      owners: ["alice"],
      tickers: ["VOD"],
      metrics: ["market_value_gbp"],
    });

    expect(await screen.findByText("AAA")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /csv/i })).toHaveAttribute(
      "href",
      expect.stringContaining("format=csv"),
    );
    expect(screen.getByRole("link", { name: /xlsx/i })).toHaveAttribute(
      "href",
      expect.stringContaining("format=xlsx"),
    );
  });

  it("persists selected parameters in export URLs", async () => {
    runCustomQuery.mockResolvedValue(mockQueryData);
    const { i18n } = renderWithI18n(<ScreenerQuery />);

    await screen.findByLabelText("Alice Example");
    await screen.findByLabelText("VOD");

    fireEvent.change(screen.getByLabelText(i18n.t("query.start")), {
      target: { value: "2024-01-01" },
    });
    fireEvent.change(screen.getByLabelText(i18n.t("query.end")), {
      target: { value: "2024-02-01" },
    });

    fireEvent.click(screen.getByLabelText("Alice Example"));
    // Narrowing owners re-scopes and re-fetches the ticker list (it briefly
    // shows the loading state — see the "shows a loading state" behaviour
    // covered elsewhere), so wait for VOD to be present again before
    // clicking it.
    await screen.findByLabelText("VOD");
    fireEvent.click(screen.getByLabelText("VOD"));
    fireEvent.click(screen.getByLabelText(i18n.t("query.metricMarketValueGbp")));

    fireEvent.click(
      screen.getAllByRole("button", { name: i18n.t("query.run") })[1],
    );

    const csv = await screen.findByRole("link", { name: /csv/i });
    const href = csv.getAttribute("href") ?? "";
    expect(href).toContain("start=2024-01-01");
    expect(href).toContain("end=2024-02-01");
    expect(href).toContain("owners=alice");
    expect(href).toContain("tickers=VOD");
    expect(href).toContain("metrics=market_value_gbp");
  });

  it("loads saved queries into the form", async () => {
    const { i18n } = renderWithI18n(<ScreenerQuery />);
    const btn = await screen.findByText("Saved1");
    fireEvent.click(btn);
    expect(screen.getByLabelText(i18n.t("query.start"))).toHaveValue("2024-01-01");

    // Issue #7202 follow-up #4: Saved1's ticker ("ZZZ") isn't held by either
    // mocked owner, so it must still render — checked, and marked as not
    // currently held — rather than becoming an invisible-but-active value
    // that's still submitted/exported/copied into the share link.
    const zzz = await screen.findByLabelText("ZZZ");
    expect(zzz).toBeChecked();
    expect(screen.getByText(new RegExp(i18n.t("query.tickerNotHeld")))).toBeInTheDocument();
  });

  it("derives the ticker list from real per-owner holdings, not a hardcoded list", async () => {
    renderWithI18n(<ScreenerQuery />);
    await screen.findByLabelText("Alice Example");

    // Both mocked owners' tickers show up (no owner selected == all owners
    // in scope, same semantics as the Owners checkboxes elsewhere).
    expect(await screen.findByLabelText("VOD")).toBeInTheDocument();
    expect(await screen.findByLabelText("PFE")).toBeInTheDocument();
    expect(getPortfolio).toHaveBeenCalledWith("alice");
    expect(getPortfolio).toHaveBeenCalledWith("bob");

    // The old hardcoded placeholder list must never render, regardless of
    // what holdings come back.
    expect(screen.queryByLabelText("AAA")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("BBB")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("CCC")).not.toBeInTheDocument();
  });

  it("narrows the ticker list to the selected owner's holdings", async () => {
    renderWithI18n(<ScreenerQuery />);
    await screen.findByLabelText("VOD");
    await screen.findByLabelText("PFE");

    fireEvent.click(screen.getByLabelText("Alice Example"));

    // Bob's ticker must disappear once only Alice is in scope; re-fetching
    // is scoped by the getPortfolio call arguments, not just by what's shown.
    await screen.findByLabelText("VOD");
    expect(screen.queryByLabelText("PFE")).not.toBeInTheDocument();
  });

  it("shows an empty state when the in-scope owner has no holdings", async () => {
    getPortfolio.mockResolvedValue(makePortfolio("alice", []));
    const { i18n } = renderWithI18n(<ScreenerQuery />);
    await screen.findByLabelText("Alice Example");

    expect(
      await screen.findByText(i18n.t("query.tickersEmpty")),
    ).toBeInTheDocument();
  });

  it("surfaces which owners' holdings failed to load without hiding the rest", async () => {
    getPortfolio.mockImplementation((owner: string) =>
      owner === "bob"
        ? Promise.reject(new Error("portfolio down"))
        : Promise.resolve(makePortfolio(owner, ["VOD"])),
    );
    const { i18n } = renderWithI18n(<ScreenerQuery />);
    await screen.findByLabelText("Alice Example");

    // Alice's ticker still renders...
    expect(await screen.findByLabelText("VOD")).toBeInTheDocument();
    // ...but the failure for bob is surfaced, not swallowed.
    expect(
      await screen.findByText(
        new RegExp(i18n.t("query.tickersPartialError", { owners: "bob" })),
      ),
    ).toBeInTheDocument();
  });

  it("renders wrapper and marker even when owner and saved query fetches fail", async () => {
    getOwners.mockRejectedValueOnce(new Error("owners down"));
    listSavedQueries.mockRejectedValueOnce(new Error("queries down"));

    renderWithI18n(<ScreenerQuery />);

    expect(screen.getByTestId("screener-query-wrapper")).toBeInTheDocument();
    expect(
      screen.getByTestId("screener-query-boundary"),
    ).toBeInTheDocument();
  });

  it("initializes form from query string", async () => {
    window.history.pushState(
      {},
      "",
      "/?start=2024-01-01&owners=alice&tickers=VOD&metrics=market_value_gbp",
    );
    const { i18n } = renderWithI18n(<ScreenerQuery />);
    await screen.findByLabelText("Alice Example");
    await screen.findByLabelText("VOD");
    expect(screen.getByLabelText(i18n.t("query.start"))).toHaveValue(
      "2024-01-01",
    );
    expect(screen.getByLabelText("Alice Example")).toBeChecked();
    expect(screen.getByLabelText("VOD")).toBeChecked();
    expect(
      screen.getByLabelText(i18n.t("query.metricMarketValueGbp")),
    ).toBeChecked();
  });

  it("sanitizes malicious query parameters", async () => {
    window.history.pushState(
      {},
      "",
      "/?owners=<script>alert(1)</script>&start=not-a-date",
    );
    const { i18n } = renderWithI18n(<ScreenerQuery />);
    await screen.findByLabelText(i18n.t("query.start"));
    expect(screen.getByLabelText(i18n.t("query.start"))).toHaveValue("");
    expect(screen.getByLabelText("Alice Example")).not.toBeChecked();
    expect(screen.getByLabelText("Bob Example")).not.toBeChecked();
  });

  it("copies an encoded link to the clipboard", async () => {
    const writeText = vi.fn();
    Object.assign(navigator, { clipboard: { writeText } });
    const { i18n } = renderWithI18n(<ScreenerQuery />);
    await screen.findByLabelText("Alice Example");
    await screen.findByLabelText("VOD");
    fireEvent.click(screen.getByLabelText("Alice Example"));
    // Narrowing owners re-scopes and re-fetches the ticker list (it briefly
    // shows the loading state — see the "shows a loading state" behaviour
    // covered elsewhere), so wait for VOD to be present again before
    // clicking it.
    await screen.findByLabelText("VOD");
    fireEvent.click(screen.getByLabelText("VOD"));
    fireEvent.click(screen.getByLabelText(i18n.t("query.metricMarketValueGbp")));
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("query.copyLink") }),
    );
    expect(writeText).toHaveBeenCalled();
    expect(writeText.mock.calls[0][0]).toContain("owners=alice");
  });

  it("switches labels when language changes", async () => {
    const { i18n, rerender } = renderWithI18n(<ScreenerQuery />);
    await screen.findByLabelText(i18n.t("query.start"));
    await act(async () => {
      await i18n.changeLanguage("fr");
    });
    rerender(
      <I18nextProvider i18n={i18n}>
        <ScreenerQuery />
      </I18nextProvider>,
    );
    expect(
      await screen.findByLabelText(i18n.t("query.start")),
    ).toBeInTheDocument();
  });
});
