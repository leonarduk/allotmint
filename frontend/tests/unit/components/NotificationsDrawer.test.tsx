import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi, Mock } from "vitest";
import { NotificationsDrawer } from "@/components/NotificationsDrawer";
import { useFetch } from "@/hooks/useFetch";

vi.mock("@/hooks/useFetch");

describe("NotificationsDrawer", () => {
  it("shows empty message when there are no alerts", () => {
    (useFetch as Mock)
      .mockReturnValueOnce({ data: [], loading: false, error: undefined })
      .mockReturnValueOnce({ data: [], loading: false, error: undefined });

    render(<NotificationsDrawer open onClose={() => {}} />);

    expect(screen.getByText(/No alerts/i)).toBeInTheDocument();
    expect(screen.getByText(/No nudges/i)).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("shows accessible loading skeletons for alerts and nudges while fetching", () => {
    (useFetch as Mock)
      .mockReturnValueOnce({ data: undefined, loading: true, error: undefined })
      .mockReturnValueOnce({ data: undefined, loading: true, error: undefined });

    render(<NotificationsDrawer open onClose={() => {}} />);

    expect(screen.getAllByRole("status", { name: /loading/i })).toHaveLength(2);
    expect(screen.queryByText(/No alerts/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/No nudges/i)).not.toBeInTheDocument();
  });
});
