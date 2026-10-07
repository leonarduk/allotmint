/** Render a backend signal action ("BUY"/"sell") as "Buy"/"Sell". */
export function formatSignalAction(action: string): string {
  if (!action) {
    return action;
  }
  const lower = action.toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}
