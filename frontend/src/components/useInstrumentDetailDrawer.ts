import { useCallback, useEffect, useRef, useState } from "react";

import {
  clampDrawerWidth,
  DEFAULT_DRAWER_WIDTH,
  DRAWER_WIDTH_KEY,
  expandedDrawerWidth,
} from "./instrumentDetailDrawer";
import { useViewportWidth } from "@/hooks/useViewportWidth";

const reportStorageError = (action: "read" | "write", error: unknown) => {
  console.warn(`Unable to ${action} the instrument detail drawer width`, error);
};

export const readDrawerWidth = (): number => {
  if (typeof window === "undefined") return DEFAULT_DRAWER_WIDTH;

  try {
    const storedWidth = Number(window.localStorage.getItem(DRAWER_WIDTH_KEY));
    const width = Number.isFinite(storedWidth) && storedWidth > 0
      ? storedWidth
      : DEFAULT_DRAWER_WIDTH;
    return clampDrawerWidth(width, window.innerWidth);
  } catch (error) {
    reportStorageError("read", error);
    return clampDrawerWidth(DEFAULT_DRAWER_WIDTH, window.innerWidth);
  }
};

const persistDrawerWidth = (width: number) => {
  try {
    window.localStorage.setItem(DRAWER_WIDTH_KEY, String(Math.round(width)));
  } catch (error) {
    reportStorageError("write", error);
  }
};

export const useInstrumentDetailDrawer = (enabled: boolean) => {
  const [width, setWidth] = useState(readDrawerWidth);
  const viewportWidth = useViewportWidth(enabled);
  const dragStart = useRef<{ pointerX: number; width: number } | null>(null);

  useEffect(() => {
    if (!enabled) return;
    setWidth((currentWidth) => clampDrawerWidth(currentWidth, viewportWidth));
  }, [enabled, viewportWidth]);

  const resizeToPointer = useCallback((clientX: number) => {
    if (!dragStart.current) return null;
    return clampDrawerWidth(
      dragStart.current.width + dragStart.current.pointerX - clientX,
      window.innerWidth,
    );
  }, []);

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    dragStart.current = { pointerX: event.clientX, width };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const nextWidth = resizeToPointer(event.clientX);
    if (nextWidth != null) setWidth(nextWidth);
  };
  const handlePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    const nextWidth = resizeToPointer(event.clientX);
    dragStart.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    if (nextWidth != null) {
      setWidth(nextWidth);
      persistDrawerWidth(nextWidth);
    }
  };
  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const direction = event.key === "ArrowLeft" ? 1 : -1;
    const nextWidth = clampDrawerWidth(width + direction * 20, window.innerWidth);
    setWidth(nextWidth);
    persistDrawerWidth(nextWidth);
  };
  const toggleExpanded = () => {
    const expandedWidth = expandedDrawerWidth(viewportWidth);
    const nextWidth = width >= expandedWidth - 1
      ? clampDrawerWidth(DEFAULT_DRAWER_WIDTH, viewportWidth)
      : expandedWidth;
    setWidth(nextWidth);
    persistDrawerWidth(nextWidth);
  };

  return {
    width,
    viewportWidth,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handleKeyDown,
    toggleExpanded,
  };
};
