import { renderHook, act, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useTransactionsController } from "@/components/transactions/useTransactionsController";

const mockUseFetch = vi.fn();
const mockUpdateTransaction = vi.fn();
const mockGetTransactions = vi.fn();

vi.mock("@/hooks/useFetch", () => ({
  useFetch: (...args: unknown[]) => mockUseFetch(...args),
}));

vi.mock("@/api", () => ({
  createTransaction: vi.fn(),
  deleteTransaction: vi.fn(),
  getTransactions: (...args: unknown[]) => mockGetTransactions(...args),
  updateTransaction: (...args: unknown[]) => mockUpdateTransaction(...args),
}));

describe("useTransactionsController", () => {
  beforeEach(() => {
    mockUseFetch.mockReset();
    mockUpdateTransaction.mockReset();
    mockGetTransactions.mockReset();
    mockUseFetch.mockReturnValue({
      data: [
        {
          id: "alex:isa:0",
          owner: "alex",
          account: "isa",
          ticker: "PFE",
          date: "2024-01-01",
        },
      ],
      loading: false,
      error: null,
    });
  });

  it("exposes paginated rows and selection helpers", async () => {
    const { result } = renderHook(() =>
      useTransactionsController([
        { owner: "alex", full_name: "Alex Example", accounts: ["isa"] },
      ]),
    );

    expect(result.current.paginatedTransactions).toHaveLength(1);

    act(() => {
      result.current.handleToggleSelect("alex:isa:0", true);
    });

    expect(result.current.selectedIds).toEqual(["alex:isa:0"]);
    expect(result.current.hasSelection).toBe(true);
  });

  it("validates and applies bulk updates", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    mockUpdateTransaction.mockResolvedValue({});

    const { result } = renderHook(() =>
      useTransactionsController([
        { owner: "alex", full_name: "Alex Example", accounts: ["isa"] },
      ]),
    );

    act(() => {
      result.current.handleToggleSelect("alex:isa:0", true);
      result.current.setFormField("owner", "alex");
      result.current.setFormField("account", "isa");
      result.current.setFormField("date", "2024-01-01");
      result.current.setFormField("ticker", "PFE");
      result.current.setFormField("price", "20");
      result.current.setFormField("units", "2");
      result.current.setFormField("reason", "Rebalance");
    });

    await act(async () => {
      await result.current.applyToSelected();
    });

    await waitFor(() => {
      expect(mockUpdateTransaction).toHaveBeenCalledWith(
        "alex:isa:0",
        expect.objectContaining({ ticker: "PFE", units: 2 }),
      );
    });
    confirmSpy.mockRestore();
  });
});
