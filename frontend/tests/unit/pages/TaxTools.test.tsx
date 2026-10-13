import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TaxTools from "@/pages/TaxTools";
import { getAllowances, getOwners, getPortfolio, harvestTax } from "@/api";
import { useRoute } from "@/RouteContext";
import { AuthContext } from "@/AuthContext";

vi.mock("@/api", () => ({
  harvestTax: vi.fn(),
  getAllowances: vi.fn(),
  getOwners: vi.fn(),
  getPortfolio: vi.fn(),
}));

vi.mock("@/RouteContext", () => ({
  useRoute: vi.fn(),
}));

describe("TaxTools", () => {
  const allowancesMock = getAllowances as unknown as vi.Mock;
  const harvestMock = harvestTax as unknown as vi.Mock;
  const ownersMock = getOwners as unknown as vi.Mock;
  const portfolioMock = getPortfolio as unknown as vi.Mock;
  const useRouteMock = useRoute as unknown as vi.Mock;

  beforeEach(() => {
    vi.clearAllMocks();
    useRouteMock.mockReturnValue({
      mode: "taxtools",
      setMode: vi.fn(),
      selectedOwner: "alice",
      setSelectedOwner: vi.fn(),
      selectedGroup: "",
      setSelectedGroup: vi.fn(),
    });
    ownersMock.mockResolvedValue([
      { owner: "alice", accounts: ["isa"] },
      { owner: "bob", accounts: ["gpp"] },
    ]);
    allowancesMock.mockResolvedValue({
      owner: "alice",
      tax_year: "2024",
      allowances: {
        isa: { used: 1000, limit: 20000, remaining: 19000 },
      },
    });
    portfolioMock.mockResolvedValue({
      owner: "alice",
      as_of: "2024-01-01",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 0,
      accounts: [
        {
          account_type: "gia",
          currency: "GBP",
          value_estimate_gbp: 0,
          holdings: [
            {
              ticker: "ABC",
              name: "ABC Corp",
              units: 10,
              cost_basis_gbp: 1000,
              market_value_gbp: 800,
              gain_gbp: -200,
              current_price_gbp: 80,
              acquired_date: "2023-01-01",
            },
            {
              ticker: "XYZ",
              name: "XYZ Plc",
              units: 5,
              cost_basis_gbp: 500,
              market_value_gbp: 400,
              gain_gbp: -100,
              current_price_gbp: 80,
              acquired_date: "2023-02-01",
            },
          ],
        },
      ],
    });
    harvestMock.mockResolvedValue({ trades: [] });
  });

  it("loads the owner portfolio when an owner is selected", async () => {
    render(<TaxTools />);

    await screen.findByLabelText(/portfolio owner/i);
    await screen.findByRole("checkbox", { name: /abc/i });

    expect(portfolioMock).toHaveBeenCalledWith("alice");
  });

  it("calls harvest API with selected holdings and shows results", async () => {
    harvestMock.mockResolvedValue({ trades: [{ ticker: "ABC", loss: 123 }] });

    render(<TaxTools />);

    const checkbox = await screen.findByRole("checkbox", { name: /abc/i });
    fireEvent.click(checkbox);

    fireEvent.click(screen.getByRole("button", { name: /run harvest/i }));

    await screen.findByTestId("harvest-results");

    expect(harvestMock).toHaveBeenCalledWith(
      [{ ticker: "ABC", basis: 100, price: 80 }],
      0,
    );
  });

  it("disables button and shows spinner while loading", async () => {
    let resolvePromise: (value: { trades: any[] }) => void;
    harvestMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePromise = resolve;
        }),
    );

    render(<TaxTools />);

    const checkbox = await screen.findByRole("checkbox", { name: /abc/i });
    fireEvent.click(checkbox);

    const button = screen.getByRole("button", { name: /run harvest/i });
    fireEvent.click(button);

    await screen.findByTestId("spinner");
    expect(button).toBeDisabled();

    resolvePromise!({ trades: [{ ticker: "XYZ", loss: 50 }] });
    await screen.findByTestId("harvest-results");
  });

  it("shows an accessible table skeleton while allowances are loading", async () => {
    let resolveAllowances: (value: Awaited<ReturnType<typeof getAllowances>>) => void;
    allowancesMock.mockReturnValue(
      new Promise((resolve) => {
        resolveAllowances = resolve;
      }),
    );

    render(<TaxTools />);

    expect(await screen.findByRole("status", { name: /loading/i })).toBeInTheDocument();
    expect(screen.queryByText(/tax year 2024/i)).not.toBeInTheDocument();

    resolveAllowances!({
      owner: "alice",
      tax_year: "2024",
      allowances: { isa: { used: 1000, limit: 20000, remaining: 19000 } },
    });

    await screen.findByText(/tax year 2024/i);
    expect(screen.queryByRole("status", { name: /loading/i })).not.toBeInTheDocument();
  });

  it("renders allowance data", async () => {
    render(<TaxTools />);

    await screen.findByText(/tax year 2024/i);
    expect(screen.getByText(/used £1,000.00 of £20,000.00 total/i)).toBeInTheDocument();

    const tables = await screen.findAllByRole("table");
    const allowancesTable = tables.find((table) =>
      within(table).queryByText(/usage/i),
    );
    expect(allowancesTable).toBeDefined();
    const isaCell = within(allowancesTable!)
      .getAllByRole("cell")
      .find((cell) => cell.textContent?.trim().toLowerCase() === "isa");
    expect(isaCell).toBeDefined();
    const isaRow = isaCell!.closest("tr");
    expect(isaRow).not.toBeNull();
    expect(isaRow).toHaveTextContent("£20,000.00");
    expect(isaRow).toHaveTextContent("£19,000.00");
    expect(allowancesMock).toHaveBeenCalledWith("alice");
  });

  it("highlights usage when over the allowance", async () => {
    allowancesMock.mockResolvedValue({
      owner: "alice",
      tax_year: "2024",
      allowances: {
        isa: { used: 21000, limit: 20000, remaining: -1000 },
      },
    });

    render(<TaxTools />);

    const tables = await screen.findAllByRole("table");
    const allowancesTable = tables.find((table) =>
      within(table).queryByText(/usage/i),
    );
    expect(allowancesTable).toBeDefined();
    const isaCell = within(allowancesTable!)
      .getAllByRole("cell")
      .find((cell) => cell.textContent?.trim().toLowerCase() === "isa");
    expect(isaCell).toBeDefined();
    const isaRow = isaCell!.closest("tr");
    expect(isaRow).not.toBeNull();

    const usageElements = within(isaRow!).getAllByText(/105%/);
    const visibleUsage = usageElements.find((node) => !node.classList.contains("sr-only"));
    expect(visibleUsage).toHaveClass("text-red-600");
  });

  it("prompts for owner selection when none is set", async () => {
    useRouteMock.mockReturnValue({
      mode: "taxtools",
      setMode: vi.fn(),
      selectedOwner: "",
      setSelectedOwner: vi.fn(),
      selectedGroup: "",
      setSelectedGroup: vi.fn(),
    });
    ownersMock.mockResolvedValue([
      { owner: "alice", accounts: ["isa"] },
      { owner: "bob", accounts: ["gpp"] },
    ]);

    render(<TaxTools />);

    expect(
      await screen.findByText(/choose a portfolio owner to see their allowance usage/i),
    ).toBeInTheDocument();
    expect(allowancesMock).not.toHaveBeenCalled();
  });

  it("defaults to the signed-in user's owner and shows display names (#10753)", async () => {
    const setSelectedOwner = vi.fn();
    useRouteMock.mockReturnValue({
      mode: "taxtools",
      setMode: vi.fn(),
      selectedOwner: "",
      setSelectedOwner,
      selectedGroup: "",
      setSelectedGroup: vi.fn(),
    });
    ownersMock.mockResolvedValue([
      { owner: "alex", full_name: "Alex Leonard", email: "alex@example.com", accounts: [] },
      { owner: "steve", full_name: "Steve Leonard", email: "steve@example.com", accounts: [] },
    ]);

    render(
      <AuthContext.Provider
        value={{
          user: { email: "steve@example.com" },
          setUser: () => {},
          logout: null,
          setLogout: () => {},
          demoReadOnly: false,
          setDemoReadOnly: () => {},
        }}
      >
        <TaxTools />
      </AuthContext.Provider>,
    );

    await waitFor(() => expect(setSelectedOwner).toHaveBeenCalledWith("steve"));
    expect(setSelectedOwner).not.toHaveBeenCalledWith("alex");
    const select = screen.getByLabelText(/portfolio owner/i);
    expect(
      within(select)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["Select an owner", "Alex Leonard", "Steve Leonard"]);
  });

  it("drops the empty placeholder once an owner is selected", async () => {
    render(<TaxTools />);

    const select = await screen.findByLabelText(/portfolio owner/i);
    await screen.findByRole("option", { name: "bob" });
    expect(
      within(select)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["alice", "bob"]);
  });

  it("replaces an unknown route owner with the default owner", async () => {
    const setSelectedOwner = vi.fn();
    useRouteMock.mockReturnValue({
      mode: "taxtools",
      setMode: vi.fn(),
      selectedOwner: "nobody",
      setSelectedOwner,
      selectedGroup: "",
      setSelectedGroup: vi.fn(),
    });
    ownersMock.mockResolvedValue([
      { owner: "alice", accounts: ["isa"] },
      { owner: "bob", accounts: ["gpp"] },
    ]);

    render(<TaxTools />);

    await waitFor(() => expect(setSelectedOwner).toHaveBeenCalledWith("alice"));
  });

  it("allows manual entry through the advanced toggle", async () => {
    render(<TaxTools />);

    const advancedToggle = await screen.findByLabelText(/advanced/i);
    fireEvent.click(advancedToggle);

    fireEvent.change(screen.getByPlaceholderText(/ticker/i), {
      target: { value: "MAN" },
    });
    fireEvent.change(screen.getByPlaceholderText(/basis/i), {
      target: { value: "50" },
    });
    fireEvent.change(screen.getByPlaceholderText(/price/i), {
      target: { value: "40" },
    });

    const slider = screen.getByRole("slider");
    fireEvent.change(slider, { target: { value: "10" } });

    fireEvent.click(screen.getByRole("button", { name: /run harvest/i }));

    expect(harvestMock).toHaveBeenCalledWith(
      [{ ticker: "MAN", basis: 50, price: 40 }],
      10,
    );
  });

  it("shows validation error when no positions are selected", async () => {
    render(<TaxTools />);

    await screen.findByRole("checkbox", { name: /abc/i });

    fireEvent.click(screen.getByRole("button", { name: /run harvest/i }));

    expect(
      await screen.findByText(/select a position or enter one manually/i),
    ).toBeInTheDocument();
    expect(harvestMock).not.toHaveBeenCalled();
  });

  describe("tax wrappers and cost basis (#10760)", () => {
    const losingHolding = (ticker: string) => ({
      ticker,
      name: `${ticker} Fund`,
      units: 10,
      cost_basis_gbp: 1000,
      market_value_gbp: 800,
      gain_gbp: -200,
      current_price_gbp: 80,
      acquired_date: "2023-01-01",
    });

    const portfolioWith = (
      accounts: { account_type: string; holdings: Record<string, unknown>[] }[],
    ) => ({
      owner: "alice",
      as_of: "2024-01-01",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 0,
      accounts: accounts.map((account) => ({
        currency: "GBP",
        value_estimate_gbp: 0,
        ...account,
      })),
    });

    it("excludes ISA/SIPP holdings but keeps GIA losses", async () => {
      portfolioMock.mockResolvedValue(
        portfolioWith([
          { account_type: "isa", holdings: [losingHolding("ISAX")] },
          { account_type: "sipp", holdings: [losingHolding("SIPX")] },
          { account_type: "gia", holdings: [losingHolding("GIAX")] },
        ]),
      );

      render(<TaxTools />);

      await screen.findByRole("checkbox", { name: /giax/i });
      expect(screen.queryByRole("checkbox", { name: /isax/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("checkbox", { name: /sipx/i })).not.toBeInTheDocument();
    });

    it("shows the all-sheltered empty state when every account is an ISA/SIPP", async () => {
      portfolioMock.mockResolvedValue(
        portfolioWith([
          { account_type: "isa", holdings: [losingHolding("ISAX")] },
          { account_type: "sipp", holdings: [losingHolding("SIPX")] },
        ]),
      );

      render(<TaxTools />);

      expect(
        await screen.findByText(/outside capital gains tax/i),
      ).toBeInTheDocument();
      expect(screen.queryByRole("checkbox", { name: /isax|sipx/i })).not.toBeInTheDocument();
      expect(screen.queryByText(/no clear loss candidates/i)).not.toBeInTheDocument();
    });

    it("uses the effective cost basis when the raw cost basis is zero", async () => {
      portfolioMock.mockResolvedValue(
        portfolioWith([
          {
            account_type: "gia",
            holdings: [
              {
                ticker: "ISXF.L",
                name: "iShares Fund",
                units: 100,
                cost_basis_gbp: 0,
                effective_cost_basis_gbp: 3681.18,
                market_value_gbp: 2690.14,
                gain_gbp: -991.04,
                current_price_gbp: 26.9014,
                acquired_date: "2023-01-01",
              },
            ],
          },
        ]),
      );

      render(<TaxTools />);

      const checkbox = await screen.findByRole("checkbox", { name: /isxf\.l/i });
      const row = checkbox.closest("tr")!;
      expect(row).toHaveTextContent("£3,681.18");
      expect(row).toHaveTextContent("-£991.04");
      expect(row).toHaveTextContent("-26.92%");

      fireEvent.click(checkbox);
      fireEvent.click(screen.getByRole("button", { name: /run harvest/i }));
      await screen.findByText(/no trades qualify/i);
      expect(harvestMock).toHaveBeenCalledWith(
        [{ ticker: "ISXF.L", basis: 36.8118, price: 26.9014 }],
        0,
      );
    });
  });
});
