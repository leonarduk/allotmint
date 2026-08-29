import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PerformanceScopeSelector } from "@/components/PerformanceScopeSelector";

describe("PerformanceScopeSelector (#7228)", () => {
  const owners = [
    { owner: "alice", full_name: "Alice Example", accounts: ["ISA"] },
    { owner: "bob", full_name: "Bob Example", accounts: ["ISA"] },
  ];
  const groups = [
    { slug: "all", name: "At a glance", members: ["alice", "bob"] },
    { slug: "adults", name: "Adults", members: ["alice"] },
  ];

  it("lists group entries alongside every owner", () => {
    render(
      <PerformanceScopeSelector
        owners={owners}
        groups={groups}
        value={{ kind: "owner", owner: "alice" }}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByRole("option", { name: "At a glance" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Adults" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Alice Example" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Bob Example" })).toBeInTheDocument();
  });

  it("reports a group selection distinctly from an owner selection", () => {
    const onSelect = vi.fn();
    render(
      <PerformanceScopeSelector
        owners={owners}
        groups={groups}
        value={null}
        onSelect={onSelect}
      />,
    );

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "group:all" },
    });
    expect(onSelect).toHaveBeenCalledWith({ kind: "group", slug: "all" });

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "owner:bob" },
    });
    expect(onSelect).toHaveBeenCalledWith({ kind: "owner", owner: "bob" });
  });

  it("reflects the active group scope as the selected value", () => {
    render(
      <PerformanceScopeSelector
        owners={owners}
        groups={groups}
        value={{ kind: "group", slug: "adults" }}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByRole("combobox")).toHaveValue("group:adults");
  });
});
