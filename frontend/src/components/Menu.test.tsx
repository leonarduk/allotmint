import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import Menu from "./Menu";

describe("Menu", () => {
  it("renders Logs tab", () => {
    render(
      <MemoryRouter>
        <Menu />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Logs" })).toBeInTheDocument();
  });

  it("renders logout button when callback provided", () => {
    const onLogout = vi.fn();
    render(
      <MemoryRouter>
        <Menu onLogout={onLogout} />
      </MemoryRouter>,
    );
    const btn = screen.getByRole("button", { name: /logout/i });
    fireEvent.click(btn);
    expect(onLogout).toHaveBeenCalled();
  });
});
