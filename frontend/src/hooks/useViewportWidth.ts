import { useEffect, useState } from "react";

import { DEFAULT_DRAWER_WIDTH } from "@/components/instrumentDetailDrawer";

export const useViewportWidth = (enabled = true): number => {
  const [viewportWidth, setViewportWidth] = useState(() =>
    typeof window === "undefined" ? DEFAULT_DRAWER_WIDTH : window.innerWidth,
  );

  useEffect(() => {
    if (!enabled) return;

    const handleResize = () => setViewportWidth(window.innerWidth);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [enabled]);

  return viewportWidth;
};
