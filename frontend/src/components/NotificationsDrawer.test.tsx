import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi, Mock } from "vitest";
import { NotificationsDrawer } from "./NotificationsDrawer";
import { useFetch } from "../hooks/useFetch";

vi.mock("../hooks/useFetch");

describe("NotificationsDrawer", () => {
  it("shows empty message when there are no alerts", () => {
    (useFetch as Mock).mockReturnValue({
      data: [],
      loading: false,
      error: undefined,
    });

    render(<NotificationsDrawer open onClose={() => {}} />);

    expect(screen.getByText(/No alerts/i)).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });
});
