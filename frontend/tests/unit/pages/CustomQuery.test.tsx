import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { createInstance } from "i18next";
import type { ReactElement } from "react";
import en from "@/locales/en/translation.json";
import fr from "@/locales/fr/translation.json";

const mockQueryData = [
  { owner: "alice", ticker: "AAA", market_value_gbp: 100 },
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
}));

import {
  getOwners,
  getPortfolio,
  listSavedQueries,
  runCustomQuery,
} from "@/api";
import { CustomQuery } from "@/pages/CustomQuery";

function renderWithI18n(ui: ReactElement) {
  const i18n = createInstance();
  i18n.use(initReactI18next).init({
    lng: "en",
    resources: { en: { translation: en }, fr: { translation: fr } },
  });
  const result = render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
  return { i18n, ...result };
}

describe("Custom Query page", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/");
    vi.resetAllMocks();
    // default API mocks to resolve to empty arrays
    runCustomQuery.mockResolvedValue([]);
    getOwners.mockResolvedValue([
      { owner: "alice", full_name: "Alice Example", accounts: [] },
      { owner: "bob", full_name: "Bob Example", accounts: [] },
    ]);
    // Deliberately NOT "AAA"/"BBB"/"CCC" — those are exactly the strings the
    // hardcoded fallback that issue #7202 removed used to render, so a test
    // fixture reusing them couldn't tell a working derivation from a gutted
    // one. See "PR #7323 review" comment above the fallback's old location
    // in the old ScreenerQuery.tsx.
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
  it("submits query form and renders results with export links", async () => {
    runCustomQuery.mockResolvedValue(mockQueryData);
    const { i18n } = renderWithI18n(<CustomQuery />);

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

    fireEvent.click(screen.getByRole("button", { name: i18n.t("query.run") }));

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
    const { i18n } = renderWithI18n(<CustomQuery />);

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
      screen.getByRole("button", { name: i18n.t("query.run") }),
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
    const { i18n } = renderWithI18n(<CustomQuery />);
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
    renderWithI18n(<CustomQuery />);
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
    renderWithI18n(<CustomQuery />);
    await screen.findByLabelText("VOD");
    await screen.findByLabelText("PFE");

    fireEvent.click(screen.getByLabelText("Alice Example"));

    // Bob's ticker must disappear once only Alice is in scope; re-fetching
    // is scoped by the getPortfolio call arguments, not just by what's shown.
    await screen.findByLabelText("VOD");
    expect(screen.queryByLabelText("PFE")).not.toBeInTheDocument();
  });

  it("updates the ticker list when the selected owner changes", async () => {
    // Distinct, non-overlapping ticker sets per owner so a stale list (or a
    // list that ignores the current selection) is detectable: if the ticker
    // options don't react to the owner change, MSFT will never appear and/or
    // AAPL will linger.
    getPortfolio.mockImplementation((owner: string) =>
      Promise.resolve(
        makePortfolio(owner, owner === "alice" ? ["AAPL"] : ["MSFT"]),
      ),
    );

    renderWithI18n(<CustomQuery />);
    await screen.findByLabelText("Alice Example");

    // No owner selected == all owners in scope, so both owners' tickers show.
    expect(await screen.findByLabelText("AAPL")).toBeInTheDocument();
    expect(await screen.findByLabelText("MSFT")).toBeInTheDocument();

    // Select Alice: only her holding should remain.
    fireEvent.click(screen.getByLabelText("Alice Example"));
    await screen.findByLabelText("AAPL");
    expect(screen.queryByLabelText("MSFT")).not.toBeInTheDocument();

    // Switch to Bob: the list must re-scope to Bob's holdings, dropping
    // Alice's ticker and surfacing Bob's.
    fireEvent.click(screen.getByLabelText("Alice Example"));
    fireEvent.click(screen.getByLabelText("Bob Example"));
    expect(await screen.findByLabelText("MSFT")).toBeInTheDocument();
    expect(screen.queryByLabelText("AAPL")).not.toBeInTheDocument();
  });

  it("shows an empty state when the in-scope owner has no holdings", async () => {
    getPortfolio.mockResolvedValue(makePortfolio("alice", []));
    const { i18n } = renderWithI18n(<CustomQuery />);
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
    const { i18n } = renderWithI18n(<CustomQuery />);
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

    renderWithI18n(<CustomQuery />);

    expect(screen.getByTestId("custom-query-wrapper")).toBeInTheDocument();
    expect(
      screen.getByTestId("custom-query-boundary"),
    ).toBeInTheDocument();
  });

  it("initializes form from query string", async () => {
    window.history.pushState(
      {},
      "",
      "/?start=2024-01-01&owners=alice&tickers=VOD&metrics=market_value_gbp",
    );
    const { i18n } = renderWithI18n(<CustomQuery />);
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

  // Expected default range (trailing 12 months, local dates).
  const expectedDefaultRange = () => {
    const pad = (n: number) => String(n).padStart(2, "0");
    const iso = (d: Date) =>
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    const today = new Date();
    const yearAgo = new Date(today);
    yearAgo.setFullYear(today.getFullYear() - 1);
    if (yearAgo.getMonth() !== today.getMonth()) yearAgo.setDate(0);
    return { start: iso(yearAgo), end: iso(today) };
  };

  it("clamps the default start to 28 Feb when today is 29 Feb", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2028, 1, 29, 12));
    try {
      window.history.pushState({}, "", "/");
      const { i18n } = renderWithI18n(<CustomQuery />);
      await screen.findByLabelText(i18n.t("query.start"));
      expect(screen.getByLabelText(i18n.t("query.end"))).toHaveValue(
        "2028-02-29",
      );
      expect(screen.getByLabelText(i18n.t("query.start"))).toHaveValue(
        "2027-02-28",
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("defaults the date range to the trailing 12 months", async () => {
    window.history.pushState({}, "", "/");
    const { i18n } = renderWithI18n(<CustomQuery />);
    await screen.findByLabelText(i18n.t("query.start"));
    const { start, end } = expectedDefaultRange();
    expect(screen.getByLabelText(i18n.t("query.end"))).toHaveValue(end);
    expect(screen.getByLabelText(i18n.t("query.start"))).toHaveValue(start);
  });

  it("keeps the default end date when a link only carries a start date", async () => {
    window.history.pushState({}, "", "/?start=2024-01-01");
    const { i18n } = renderWithI18n(<CustomQuery />);
    await screen.findByLabelText(i18n.t("query.start"));
    expect(screen.getByLabelText(i18n.t("query.start"))).toHaveValue(
      "2024-01-01",
    );
    expect(screen.getByLabelText(i18n.t("query.end"))).toHaveValue(
      expectedDefaultRange().end,
    );
  });

  it("keeps the default start date when a link only carries an end date", async () => {
    window.history.pushState({}, "", "/?end=2024-02-01");
    const { i18n } = renderWithI18n(<CustomQuery />);
    await screen.findByLabelText(i18n.t("query.start"));
    expect(screen.getByLabelText(i18n.t("query.end"))).toHaveValue(
      "2024-02-01",
    );
    expect(screen.getByLabelText(i18n.t("query.start"))).toHaveValue(
      expectedDefaultRange().start,
    );
  });

  it("overrides both defaults when a link carries start and end", async () => {
    window.history.pushState({}, "", "/?start=2024-01-01&end=2024-02-01");
    const { i18n } = renderWithI18n(<CustomQuery />);
    await screen.findByLabelText(i18n.t("query.start"));
    expect(screen.getByLabelText(i18n.t("query.start"))).toHaveValue(
      "2024-01-01",
    );
    expect(screen.getByLabelText(i18n.t("query.end"))).toHaveValue(
      "2024-02-01",
    );
  });

  it("loading a saved query with blank dates clears the defaults", async () => {
    window.history.pushState({}, "", "/");
    listSavedQueries.mockResolvedValueOnce([
      {
        id: "2",
        name: "NoDates",
        params: { start: "", end: "", owners: [], tickers: [], metrics: [] },
      },
    ]);
    const { i18n } = renderWithI18n(<CustomQuery />);
    fireEvent.click(await screen.findByText("NoDates"));
    expect(screen.getByLabelText(i18n.t("query.start"))).toHaveValue("");
    expect(screen.getByLabelText(i18n.t("query.end"))).toHaveValue("");
  });

  it("ignores an invalid end date in the link and keeps the default", async () => {
    window.history.pushState({}, "", "/?end=not-a-date");
    const { i18n } = renderWithI18n(<CustomQuery />);
    await screen.findByLabelText(i18n.t("query.end"));
    expect(screen.getByLabelText(i18n.t("query.end"))).toHaveValue(
      expectedDefaultRange().end,
    );
  });

  it("sanitizes malicious query parameters", async () => {
    window.history.pushState(
      {},
      "",
      "/?owners=<script>alert(1)</script>&start=not-a-date",
    );
    const { i18n } = renderWithI18n(<CustomQuery />);
    await screen.findByLabelText(i18n.t("query.start"));
    // The invalid date is rejected and the default stays.
    expect(screen.getByLabelText(i18n.t("query.start"))).toHaveValue(
      expectedDefaultRange().start,
    );
    expect(screen.getByLabelText("Alice Example")).not.toBeChecked();
    expect(screen.getByLabelText("Bob Example")).not.toBeChecked();
  });

  it("copies an encoded link to the clipboard", async () => {
    const writeText = vi.fn();
    Object.assign(navigator, { clipboard: { writeText } });
    const { i18n } = renderWithI18n(<CustomQuery />);
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
    const { i18n, rerender } = renderWithI18n(<CustomQuery />);
    await screen.findByLabelText(i18n.t("query.start"));
    await act(async () => {
      await i18n.changeLanguage("fr");
    });
    rerender(
      <I18nextProvider i18n={i18n}>
        <CustomQuery />
      </I18nextProvider>,
    );
    expect(
      await screen.findByLabelText(i18n.t("query.start")),
    ).toBeInTheDocument();
  });
});

// Integration coverage for the full Run-button flow (issue #7133 follow-up).
//
// The unit tests above mock `runCustomQuery` itself, so they would stay green
// even if `runCustomQuery` reverted to a GET (or dropped `format: "json"` from
// the request body) — the exact regression PR #7133 fixed. These tests instead
// stub the global `fetch` and drive the *real* `runCustomQuery` through the
// component, asserting on the wire-level request (method, URL, JSON body) and
// on the user-visible result/error states.
describe("Custom Query page — Run button integration (real runCustomQuery)", () => {
  // `runCustomQuery` is mocked at module scope above; these tests need the
  // real implementation, so we import it fresh from the module registry and
  // restore the mocked binding afterwards.
  let realRunCustomQuery: typeof import("@/api").runCustomQuery;
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(async () => {
    const actual = await vi.importActual<typeof import("@/api")>("@/api");
    realRunCustomQuery = actual.runCustomQuery;
    // Re-point the mocked export at the real implementation for this block.
    (runCustomQuery as unknown as { mockImplementation: (fn: unknown) => void })
      .mockImplementation(realRunCustomQuery);

    // Default the other API calls the page makes on mount so the form renders
    // deterministically without hitting the network.
    getOwners.mockResolvedValue([
      { owner: "alice", full_name: "Alice Example", accounts: [] },
    ]);
    getPortfolio.mockImplementation((owner: string) =>
      Promise.resolve(makePortfolio(owner, ["VOD"])),
    );
    listSavedQueries.mockResolvedValue([]);

    fetchSpy = vi.spyOn(globalThis, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  function stubFetchOnce(payload: unknown, init: { ok?: boolean; status?: number } = {}) {
    const ok = init.ok ?? true;
    const status = init.status ?? (ok ? 200 : 500);
    fetchSpy.mockResolvedValueOnce({
      ok,
      status,
      statusText: ok ? "OK" : "Internal Server Error",
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => payload,
      text: async () => JSON.stringify(payload),
    } as unknown as Response);
  }

  it("POSTs the query as JSON with format=json and renders the unwrapped results", async () => {
    stubFetchOnce({ results: mockQueryData });

    const { i18n } = renderWithI18n(<CustomQuery />);
    await screen.findByLabelText("Alice Example");
    await screen.findByLabelText("VOD");

    fireEvent.change(screen.getByLabelText(i18n.t("query.start")), {
      target: { value: "2024-01-01" },
    });
    fireEvent.change(screen.getByLabelText(i18n.t("query.end")), {
      target: { value: "2024-02-01" },
    });
    fireEvent.click(screen.getByLabelText("Alice Example"));
    await screen.findByLabelText("VOD");
    fireEvent.click(screen.getByLabelText("VOD"));
    fireEvent.click(screen.getByLabelText(i18n.t("query.metricMarketValueGbp")));

    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("query.run") }),
    );

    // The unwrapped `results` array must be rendered — proving the response
    // shape `{ results: [...] }` is parsed correctly end-to-end.
    expect(await screen.findByText("AAA")).toBeInTheDocument();

    // Wire-level assertions: a POST to /custom-query/run with a JSON body
    // that includes `format: "json"`. Reverting to GET (or dropping the
    // format field) would fail these.
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toContain("/custom-query/run");
    expect(init.method).toBe("POST");
    expect(
      new Headers(init.headers as HeadersInit).get("Content-Type"),
    ).toBe("application/json");
    const body = JSON.parse(String(init.body));
    expect(body).toMatchObject({
      start: "2024-01-01",
      end: "2024-02-01",
      owners: ["alice"],
      tickers: ["VOD"],
      metrics: ["market_value_gbp"],
      format: "json",
    });
  });

  it("shows an error state when the backend rejects the query", async () => {
    stubFetchOnce(
      { detail: "query blew up" },
      { ok: false, status: 500 },
    );

    const { i18n } = renderWithI18n(<CustomQuery />);
    await screen.findByLabelText("Alice Example");
    await screen.findByLabelText("VOD");

    fireEvent.click(screen.getByLabelText("Alice Example"));
    await screen.findByLabelText("VOD");
    fireEvent.click(screen.getByLabelText("VOD"));
    fireEvent.click(screen.getByLabelText(i18n.t("query.metricMarketValueGbp")));

    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("query.run") }),
    );

    // The backend's `detail` message is surfaced to the user (prefixed with
    // "Failed to run query" for 5xx, #7178), and no results table is rendered.
    expect(
      await screen.findByText("Failed to run query: query blew up"),
    ).toBeInTheDocument();
    expect(screen.queryByText("AAA")).not.toBeInTheDocument();
  });
});
