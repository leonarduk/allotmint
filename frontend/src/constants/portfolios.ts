// Shared portfolio-slug constants.
//
// `ALL_PORTFOLIOS_SLUG` is the sentinel slug meaning "aggregate across every
// portfolio" (as opposed to a single owner's slug). It is part of the API
// contract between the frontend and backend, so it lives here rather than
// being spelled out as a bare `"all"` literal at each call site — a typo in
// one usage would otherwise silently break aggregation with no compile-time
// error.
export const ALL_PORTFOLIOS_SLUG = "all";
