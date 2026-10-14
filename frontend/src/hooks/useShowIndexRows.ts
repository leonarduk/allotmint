import { useCallback, useState } from 'react';

const SHOW_INDEX_ROWS_KEY = 'showIndexBenchmarkRows';

const readShowIndexRows = (): boolean => {
  try {
    return window.localStorage.getItem(SHOW_INDEX_ROWS_KEY) === 'true';
  } catch {
    // Storage blocked (private mode, sandbox): fall back to the default, off.
    return false;
  }
};

/** Whether the owner table shows index rows; remembered per browser, off by default. */
export function useShowIndexRows(): [boolean, (show: boolean) => void] {
  const [show, setShowState] = useState(readShowIndexRows);
  const setShow = useCallback((next: boolean) => {
    setShowState(next);
    try {
      window.localStorage.setItem(SHOW_INDEX_ROWS_KEY, String(next));
    } catch {
      // Storage blocked: the choice still applies for this page view.
    }
  }, []);
  return [show, setShow];
}
