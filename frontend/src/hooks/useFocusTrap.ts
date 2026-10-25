import { useEffect, type RefObject } from 'react';

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusables(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
  );
}

// Wraps Tab/Shift+Tab at the ends of `container`, and pulls focus back in if
// it has escaped (e.g. after a click on the page behind a backdrop).
function trapTab(event: KeyboardEvent, container: HTMLElement): void {
  if (event.key !== 'Tab') return;
  const items = focusables(container);
  if (items.length === 0) return;
  const first = items[0];
  const last = items[items.length - 1];
  const active = document.activeElement;
  const outside = !container.contains(active);
  if (event.shiftKey && (active === first || outside)) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (active === last || outside)) {
    event.preventDefault();
    first.focus();
  }
}

/**
 * Modal-dialog focus handling for `containerRef` while `active` (#7962):
 * moves focus inside (to `initialFocusRef`, else the first focusable element,
 * else the container), keeps Tab/Shift+Tab within it, and when it deactivates
 * or unmounts returns focus to the element that had it before.
 */
export function useFocusTrap(
  containerRef: RefObject<HTMLElement | null>,
  active: boolean,
  initialFocusRef?: RefObject<HTMLElement | null>
): void {
  useEffect(() => {
    const container = containerRef.current;
    if (!active || !container) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    (initialFocusRef?.current ?? focusables(container)[0] ?? container).focus();

    const handleKeyDown = (event: KeyboardEvent) => trapTab(event, container);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [active, containerRef, initialFocusRef]);
}
