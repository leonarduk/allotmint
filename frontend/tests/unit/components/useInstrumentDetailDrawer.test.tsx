import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_DRAWER_WIDTH,
  expandedDrawerWidth,
} from "@/components/instrumentDetailDrawer";
import { useInstrumentDetailDrawer } from "@/components/useInstrumentDetailDrawer";

const DrawerHarness = () => {
  const drawer = useInstrumentDetailDrawer(true);
  return (
    <>
      <output aria-label="Drawer width">{Math.round(drawer.width)}</output>
      <div
        aria-label="Resize drawer"
        role="separator"
        tabIndex={0}
        onPointerDown={drawer.handlePointerDown}
        onPointerMove={drawer.handlePointerMove}
        onPointerUp={drawer.handlePointerUp}
        onKeyDown={drawer.handleKeyDown}
      />
      <button type="button" onClick={drawer.toggleExpanded}>Toggle</button>
    </>
  );
};

const setViewportWidth = (width: number) => {
  vi.spyOn(window, "innerWidth", "get").mockReturnValue(width);
};

const renderDrawer = (storedWidth = DEFAULT_DRAWER_WIDTH) => {
  window.localStorage.setItem("allotmint.instrumentDetail.drawerWidth", String(storedWidth));
  render(<DrawerHarness />);
  const separator = screen.getByRole("separator");
  Object.assign(separator, {
    setPointerCapture: vi.fn(),
    hasPointerCapture: vi.fn(() => true),
    releasePointerCapture: vi.fn(),
  });
  return separator;
};

describe("useInstrumentDetailDrawer", () => {
  beforeEach(() => {
    window.localStorage.clear();
    setViewportWidth(1_000);
  });

  afterEach(() => vi.restoreAllMocks());

  it("resizes and persists the width after a pointer drag", () => {
    const separator = renderDrawer();

    fireEvent.pointerDown(separator, { clientX: 600, pointerId: 1 });
    fireEvent.pointerMove(separator, { clientX: 500, pointerId: 1 });
    expect(screen.getByLabelText("Drawer width")).toHaveTextContent("520");
    fireEvent.pointerUp(separator, { clientX: 480, pointerId: 1 });

    expect(screen.getByLabelText("Drawer width")).toHaveTextContent("540");
    expect(window.localStorage.getItem("allotmint.instrumentDetail.drawerWidth")).toBe("540");
  });

  it("resizes by keyboard arrow increments", () => {
    const separator = renderDrawer();
    fireEvent.keyDown(separator, { key: "ArrowLeft" });
    expect(screen.getByLabelText("Drawer width")).toHaveTextContent("440");
    fireEvent.keyDown(separator, { key: "ArrowRight" });
    expect(screen.getByLabelText("Drawer width")).toHaveTextContent("420");
  });

  it("toggles between restored and expanded widths", () => {
    renderDrawer();
    fireEvent.click(screen.getByRole("button", { name: "Toggle" }));
    expect(screen.getByLabelText("Drawer width")).toHaveTextContent("600");
    fireEvent.click(screen.getByRole("button", { name: "Toggle" }));
    expect(screen.getByLabelText("Drawer width")).toHaveTextContent("420");
  });

  it("clamps the drawer when the viewport shrinks", () => {
    renderDrawer(700);
    setViewportWidth(500);
    fireEvent(window, new Event("resize"));
    expect(screen.getByLabelText("Drawer width")).toHaveTextContent("484");
  });

  it("collapses at the exact expanded width and expands below the comparison boundary", () => {
    const threshold = expandedDrawerWidth(window.innerWidth);
    window.localStorage.setItem("allotmint.instrumentDetail.drawerWidth", String(threshold));
    const { unmount } = render(<DrawerHarness />);
    fireEvent.click(screen.getByRole("button", { name: "Toggle" }));
    expect(screen.getByLabelText("Drawer width")).toHaveTextContent("420");
    unmount();

    window.localStorage.setItem("allotmint.instrumentDetail.drawerWidth", String(threshold - 2));
    render(<DrawerHarness />);
    fireEvent.click(screen.getByRole("button", { name: "Toggle" }));
    expect(screen.getByLabelText("Drawer width")).toHaveTextContent("600");
  });
});
