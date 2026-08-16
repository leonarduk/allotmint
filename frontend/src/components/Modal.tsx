import { useEffect, useRef, type ReactNode } from "react";

interface ModalProps {
  onClose: () => void;
  children: ReactNode;
  className?: string;
  overlayClassName?: string;
  labelledBy?: string;
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Dialog wrapper with a focus trap (Tab/Shift+Tab stay within the dialog),
 * Escape-to-close, and focus restoration to the element that opened it.
 */
export function Modal({ onClose, children, className, overlayClassName, labelledBy }: ModalProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Keep a stable ref to onClose so the keydown listener is registered only
  // once (on mount) and never needs to be removed/re-added when the parent
  // re-renders with a new inline callback reference.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const container = containerRef.current;
    const focusables = container?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
    (focusables?.[0] ?? container)?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !container) return;
      const focusable = Array.from(
        container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey) {
        if (active === first || !container.contains(active)) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last || !container.contains(active)) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previouslyFocused?.focus?.();
    };
  }, []);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelledBy}
      className={overlayClassName ?? "fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"}
      onClick={onClose}
    >
      <div ref={containerRef} className={className} onClick={(e) => e.stopPropagation()} tabIndex={-1}>
        {children}
      </div>
    </div>
  );
}

export default Modal;
