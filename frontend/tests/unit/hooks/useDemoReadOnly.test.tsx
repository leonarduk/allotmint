import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { useDemoReadOnly, DEMO_READONLY_MESSAGE } from "@/hooks/useDemoReadOnly";
import { AuthContext } from "@/AuthContext";

function Probe({ reasonArg }: { reasonArg?: string }) {
  const { demoReadOnly, reason } = useDemoReadOnly();
  return (
    <div>
      <span data-testid="flag">{String(demoReadOnly)}</span>
      <span data-testid="reason">{reason(reasonArg) ?? "none"}</span>
    </div>
  );
}

describe("useDemoReadOnly (issue #7411)", () => {
  it("defaults to false (invisible to ordinary signed-in users)", () => {
    render(<Probe />);

    expect(screen.getByTestId("flag")).toHaveTextContent("false");
    expect(screen.getByTestId("reason")).toHaveTextContent("none");
  });

  it("reflects demoReadOnly=true from AuthContext and returns a reason", () => {
    render(
      <AuthContext.Provider
        value={{
          user: null,
          setUser: vi.fn(),
          logout: null,
          setLogout: vi.fn(),
          demoReadOnly: true,
          setDemoReadOnly: vi.fn(),
        }}
      >
        <Probe />
      </AuthContext.Provider>,
    );

    expect(screen.getByTestId("flag")).toHaveTextContent("true");
    expect(screen.getByTestId("reason")).toHaveTextContent(DEMO_READONLY_MESSAGE);
  });

  it("prefers a caller-supplied reason over the default message", () => {
    render(
      <AuthContext.Provider
        value={{
          user: null,
          setUser: vi.fn(),
          logout: null,
          setLogout: vi.fn(),
          demoReadOnly: true,
          setDemoReadOnly: vi.fn(),
        }}
      >
        <Probe reasonArg="Adding holdings is disabled in the demo." />
      </AuthContext.Provider>,
    );

    expect(screen.getByTestId("reason")).toHaveTextContent(
      "Adding holdings is disabled in the demo.",
    );
  });
});
