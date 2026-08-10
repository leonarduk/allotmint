export const DRAWER_WIDTH_KEY = "allotmint.instrumentDetail.drawerWidth";
export const DEFAULT_DRAWER_WIDTH = 420;
export const MIN_DRAWER_WIDTH = 320;

const DRAWER_VIEWPORT_MARGIN = 16;

export const clampDrawerWidth = (width: number, viewportWidth: number): number =>
  Math.max(
    Math.min(MIN_DRAWER_WIDTH, viewportWidth),
    Math.min(width, viewportWidth - DRAWER_VIEWPORT_MARGIN),
  );
