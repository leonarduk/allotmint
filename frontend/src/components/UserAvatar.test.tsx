import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { MemoryRouter } from "react-router-dom";
import UserAvatar from "./UserAvatar";
import { AuthContext } from "../AuthContext";

const noop = () => {};

describe("UserAvatar", () => {
  it("links to the profile page", () => {
    render(
      <AuthContext.Provider value={{ user: { picture: "p.jpg", name: "Test" }, setUser: noop }}>
        <MemoryRouter>
          <UserAvatar />
        </MemoryRouter>
      </AuthContext.Provider>,
    );
    expect(screen.getByRole("link")).toHaveAttribute("href", "/profile");
  });
});
