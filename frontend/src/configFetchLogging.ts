// A single transient "Failed to fetch" that self-heals on the next attempt
// isn't an app-breaking failure — log it at warn so it doesn't read as an
// unhandled error in the console (#5109). Only the final, non-retryable
// failure (retries exhausted) escalates to console.error, since that is a
// genuine, user-visible failure ("Unable to load configuration" screen).
export const logConfigFetchFailure = (err: unknown, willRetry: boolean) => {
  if (willRetry) {
    console.warn('Failed to load configuration, retrying', err);
  } else {
    console.error('Failed to load configuration', err);
  }
};
