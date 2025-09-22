import { render, screen, within, act, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import i18n from "../i18n";
import { formatDateISO } from "../lib/date";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
vi.mock("../api", () => ({
    getInstrumentDetail: vi.fn(() => Promise.resolve({ mini: { 7: [], 30: [], 180: [] } })),
    getGroupPortfolio: vi.fn(),
    getGroupAlphaVsBenchmark: vi.fn(() => Promise.resolve({ alpha_vs_benchmark: 0 })),
    getGroupTrackingError: vi.fn(() => Promise.resolve({ tracking_error: 0 })),
    getGroupMaxDrawdown: vi.fn(() => Promise.resolve({ max_drawdown: 0 })),
    getGroupSectorContributions: vi.fn(() => Promise.resolve([])),
    getGroupRegionContributions: vi.fn(() => Promise.resolve([])),
}));
vi.mock("./TopMoversSummary", () => ({
    TopMoversSummary: () => <div data-testid="top-movers-summary" />,
}));
import { HoldingsTable } from "./HoldingsTable";
import { GroupPortfolioView } from "./GroupPortfolioView";
import { configContext, type AppConfig } from "../ConfigContext";
import { getGroupPortfolio } from "../api";

const defaultConfig: AppConfig = {
    relativeViewEnabled: false,
    theme: "system",
    baseCurrency: "GBP",
    tabs: {
        group: true,
        market: true,
        owner: true,
        instrument: true,
        performance: true,
        transactions: true,
        trading: true,
        screener: true,
        timeseries: true,
        watchlist: true,
        allocation: true,
        rebalance: true,
        movers: true,
        instrumentadmin: true,
        dataadmin: true,
        virtual: true,
        support: true,
        settings: true,
        pension: true,
        reports: true,
        scenario: true,
      },
};
import type { Holding } from "../types";

beforeEach(() => {
    // Ensure React act environment is enabled for explicit act() calls
    (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
});

describe("HoldingsTable", () => {
    beforeEach(() => {
        localStorage.clear();
    });
    const holdings: Holding[] = [
        {
            ticker: "AAA",
            name: "Alpha",
            currency: "GBP",
            instrument_type: "Equity",
            units: 5,
            price: 0,
            cost_basis_gbp: 100,
            market_value_gbp: 150,
            gain_gbp: 50,
            current_price_gbp: 30,
            latest_source: "Feed",
            acquired_date: "2024-01-01",
            last_price_date: "2024-01-01",
            days_held: 100,
            sell_eligible: true,
            days_until_eligible: 0,
        },
        {
            ticker: "XYZ",
            name: "Test Holding",
            currency: "USD",
            instrument_type: "Equity",
            units: 5,
            price: 0,
            cost_basis_gbp: 500,
            market_value_gbp: 0,
            gain_gbp: -25,
            acquired_date: "",
            days_held: 0,
            sell_eligible: false,
            days_until_eligible: 10,
            next_eligible_sell_date: "2024-07-20",
        },
        {
            ticker: "GBXH",
            name: "GBX Holding",
            currency: "GBX",
            instrument_type: "Equity",
            units: 1,
            price: 0,
            cost_basis_gbp: 10,
            market_value_gbp: 10,
            gain_gbp: 0,
            acquired_date: "2024-01-05",
            days_held: 50,
            sell_eligible: false,
            days_until_eligible: 5,
        },
        {
            ticker: "CADH",
            name: "CAD Holding",
            currency: "CAD",
            instrument_type: "Equity",
            units: 1,
            price: 0,
            cost_basis_gbp: 20,
            market_value_gbp: 20,
            gain_gbp: 0,
            acquired_date: "2024-02-01",
            days_held: 30,
            sell_eligible: false,
            days_until_eligible: 0,
        },
    ];

    const TestProvider = ({ children }: { children: React.ReactNode }) => {
        const [relativeViewEnabled, setRelativeViewEnabled] = useState(false);
        return (
            <configContext.Provider
              value={{
                ...defaultConfig,
                relativeViewEnabled,
                setRelativeViewEnabled,
                refreshConfig: async () => {},
                setBaseCurrency: () => {},
              }}
            >
                {children}
            </configContext.Provider>
        );
    };

    const renderWithConfig = (ui: React.ReactElement) => render(<TestProvider>{ui}</TestProvider>);

    it("toggles relative view", async () => {
        renderWithConfig(<HoldingsTable holdings={holdings} />);
        await screen.findByText("AAA");
        expect(screen.getByRole('columnheader', { name: 'Units' })).toBeInTheDocument();
        const toggle = screen.getByLabelText('Relative view');
        await userEvent.click(toggle);
        expect(screen.queryByRole('columnheader', { name: 'Units' })).toBeNull();
        expect(screen.getByRole('columnheader', { name: /Gain %/ })).toBeInTheDocument();
    });

    it("shows days to go if not eligible", async () => {
        render(<HoldingsTable holdings={holdings}/>);
        const row = (await screen.findByText("Test Holding")).closest("tr");
        const cell = within(row!).getByText("✗ 10");
        expect(cell).toBeInTheDocument();
        const expected = formatDateISO(new Date('2024-07-20'));
        expect(cell).toHaveAttribute('title', expected);
    });

    it("marks stale prices with an asterisk", async () => {
        const stale: Holding = {
            ticker: "STALE",
            name: "Stale Co",
            currency: "GBP",
            instrument_type: "Equity",
            units: 1,
            price: 0,
            cost_basis_gbp: 100,
            market_value_gbp: 100,
            gain_gbp: 0,
            current_price_gbp: 100,
            acquired_date: "2024-01-01",
            days_held: 10,
            sell_eligible: true,
            days_until_eligible: 0,
            last_price_date: "2024-01-01",
            last_price_time: "2024-01-01T09:00:00Z",
            is_stale: true,
        };
        render(<HoldingsTable holdings={[stale]} />);
        const star = await screen.findByTitle("2024-01-01T09:00:00Z");
        expect(star).toHaveTextContent("*");
        const price = screen.getByText("£100.00");
        expect(price).toHaveClass("text-gray");
    });

    it("creates FX pair buttons for currency and skips GBX", async () => {
        const onSelect = vi.fn();
        render(<HoldingsTable holdings={holdings} onSelectInstrument={onSelect}/>);
        await screen.findByRole('button', { name: 'USD' });
        await act(async () => {
            await userEvent.click(screen.getByRole('button', { name: 'USD' }));
        });
        expect(onSelect).toHaveBeenCalledWith('USDGBP.FX', 'USD');
        expect(screen.queryByRole('button', { name: 'GBX' })).toBeNull();
        expect(screen.getByRole('button', { name: 'CAD' })).toBeInTheDocument();
    });

    it("sorts by ticker when header clicked", async () => {
        render(<HoldingsTable holdings={holdings}/>);
        await screen.findByText("AAA");
        // initially sorted ascending by ticker => AAA first
        let rows = screen.getAllByRole("row");
        expect(within(rows[2]).getByText("AAA")).toBeInTheDocument();

        await act(async () => {
            await userEvent.click(screen.getByText(/^Ticker/));
        });
        rows = screen.getAllByRole("row");
        expect(within(rows[2]).getByText("XYZ")).toBeInTheDocument();
    });

    it("filters by ticker", async () => {
        render(<HoldingsTable holdings={holdings}/>);
        const input = await screen.findByPlaceholderText("Ticker");
        await act(async () => {
            await userEvent.type(input, "AA");
        });
        expect(screen.getByText("AAA")).toBeInTheDocument();
        expect(screen.queryByText("XYZ")).toBeNull();
    });

    it("filters by eligibility", async () => {
        render(<HoldingsTable holdings={holdings}/>);
        const select = await screen.findByLabelText("Sell eligible");
        await act(async () => {
            await userEvent.selectOptions(select, "true");
        });
        expect(screen.getByText("AAA")).toBeInTheDocument();
        expect(screen.queryByText("Test Holding")).toBeNull();
    });

    it("shows last price date badge when available", async () => {
        render(<HoldingsTable holdings={holdings} />);
        const row = (await screen.findByText("AAA")).closest("tr");
        const badge = within(row!).getByTitle("2024-01-01");
        expect(badge).toBeInTheDocument();
    });

    it("allows toggling columns", async () => {
        render(<HoldingsTable holdings={holdings}/>);
        await screen.findByText("AAA");
        expect(screen.getByRole('columnheader', {name: 'Units'})).toBeInTheDocument();
        const checkbox = screen.getByLabelText("Units");
        await act(async () => {
            await userEvent.click(checkbox);
        });
        await waitFor(() =>
            expect(screen.queryByRole('columnheader', {name: 'Units'})).toBeNull(),
        );
    });

      it("shows price source when available", async () => {
          render(<HoldingsTable holdings={holdings}/>);
          expect(await screen.findByText(/Source: Feed/)).toBeInTheDocument();
      });

      it("applies sell-eligible quick filter", async () => {
        render(<HoldingsTable holdings={holdings} />);
        await screen.findByText('AAA');
        await act(async () => {
            await userEvent.click(screen.getByRole('button', { name: 'Sell-eligible' }));
        });
        expect(screen.getByLabelText('Sell eligible')).toHaveValue('true');
        expect(screen.getByText('AAA')).toBeInTheDocument();
        expect(screen.queryByText('Test Holding')).toBeNull();
    });

    it("applies gain percentage quick filter", async () => {
        render(<HoldingsTable holdings={holdings} />);
        const input = await screen.findByPlaceholderText('Min Gain %');
        await act(async () => {
            await userEvent.type(input, '10');
        });
        expect(screen.getByPlaceholderText('Gain %')).toHaveValue('10');
        expect(screen.getByText('AAA')).toBeInTheDocument();
        expect(screen.queryByText('XYZ')).toBeNull();
    });

      it("persists view preset selection", async () => {
          const mixedHoldings: Holding[] = [
              ...holdings,
            {
                ticker: 'BND1',
                name: 'Bond Holding',
                currency: 'GBP',
                instrument_type: 'Bond',
                units: 1,
                price: 0,
                cost_basis_gbp: 100,
                market_value_gbp: 100,
                gain_gbp: 0,
                acquired_date: '',
                days_held: 0,
                sell_eligible: false,
                days_until_eligible: 0,
            },
        ];
        const { unmount } = render(<HoldingsTable holdings={mixedHoldings} />);
        await screen.findByText('AAA');
        await act(async () => {
            await userEvent.click(screen.getByRole('button', { name: 'Bond' }));
        });
        expect(screen.getByText('BND1')).toBeInTheDocument();
        expect(screen.queryByText('AAA')).toBeNull();
        unmount();
        render(<HoldingsTable holdings={mixedHoldings} />);
        await screen.findByText('BND1');
        expect(screen.getByPlaceholderText('Type')).toHaveValue('Bond');
        expect(screen.getByText('BND1')).toBeInTheDocument();
          expect(screen.queryByText('AAA')).toBeNull();
      });

      it("shows controls and fallback when no rows match", async () => {
          localStorage.setItem("holdingsTableViewPreset", "Bond");
          render(<HoldingsTable holdings={holdings} />);
          expect(await screen.findByText('View:')).toBeInTheDocument();
          expect(screen.getByText('No holdings match the current filters.')).toBeInTheDocument();
          expect(screen.getByRole('button', { name: 'Clear filters' })).toBeInTheDocument();
          expect(screen.getByRole('button', { name: 'Open Screener' })).toBeInTheDocument();
          await act(async () => {
              await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
          });
          expect(screen.getByText('AAA')).toBeInTheDocument();
      });

      it("opens InstrumentDetail without altering search params", async () => {
        const portfolio = {
          name: "All owners combined",
          accounts: [
            {
              owner: "alice",
              account_type: "isa",
              holdings: [
                {
                  ticker: "AAA",
                  name: "Alpha",
                  currency: "GBP",
                  instrument_type: "Equity",
                  units: 1,
                  cost_basis_gbp: 100,
                  market_value_gbp: 150,
                  gain_gbp: 50,
                },
              ],
            },
          ],
        };
        vi.mocked(getGroupPortfolio).mockResolvedValue(portfolio as any);
        vi.stubGlobal(
          "ResponsiveContainer",
          ({ children }: any) => <div>{children}</div>,
        );
        vi.stubGlobal("LineChart", ({ children }: any) => <div>{children}</div>);
        vi.stubGlobal("Line", () => <div />);
        vi.stubGlobal("XAxis", () => <div />);
        vi.stubGlobal("YAxis", () => <div />);
        vi.stubGlobal("Tooltip", () => <div />);
        renderWithConfig(
          <MemoryRouter>
            <GroupPortfolioView slug="all" />
          </MemoryRouter>,
        );
        await screen.findByRole("button", { name: "AAA" });
        const initial = window.location.search;
        await act(async () => {
          await userEvent.click(screen.getByRole("button", { name: "AAA" }));
        });
        await screen.findByRole("heading", { name: "Alpha" });
        expect(window.location.search).toBe(initial);
        vi.unstubAllGlobals();
      });

      it("renders translated text in Spanish", async () => {
          await act(async () => {
              await i18n.changeLanguage('es');
          });
          render(<HoldingsTable holdings={holdings} />);
          expect(await screen.findByText('Vista:')).toBeInTheDocument();
          expect(screen.getByRole('button', { name: 'Todos' })).toBeInTheDocument();
          await act(async () => {
              await i18n.changeLanguage('en');
          });
      });

      it("renders rows and keeps header on scroll", async () => {
          const manyHoldings = Array.from({ length: 50 }, (_, i) => ({
              ...holdings[0],
              ticker: `T${i}`,
              name: `Name${i}`,
          }));
          render(<HoldingsTable holdings={manyHoldings} />);
          await screen.findByText('T0');
          const container = screen.getByRole('table').parentElement as HTMLElement;
          act(() => {
              container.scrollTop = 500;
              container.dispatchEvent(new Event('scroll'));
          });
          expect(screen.getByRole('columnheader', { name: 'Ticker' })).toBeInTheDocument();
          expect(screen.getByText('T49')).toBeInTheDocument();
      });
  });
