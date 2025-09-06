import { toast, type ToastId } from "react-toastify";

const activeToasts = new Map<string, ToastId>();

/**
 * Show an error toast, deduping by message so the same error isn't shown
 * multiple times concurrently.
 */
export function errorToast(error: unknown, fallback = "An unexpected error occurred") {
  const message =
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : fallback;

  if (activeToasts.has(message)) {
    return;
  }

  const id = toast.error(message, {
    onClose: () => {
      activeToasts.delete(message);
    },
  });

  activeToasts.set(message, id);
}

export default errorToast;
