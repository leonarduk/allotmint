import { useCallback, useEffect, useRef, useState } from 'react';

import {
  getGroupAlphaVsBenchmark,
  getGroupMaxDrawdown,
  getGroupTrackingError,
} from '../api';
import { isFresh, readFetchCache, runDeduped } from '../utils/fetchCache';

// The group dashboard's three 365-day benchmark tiles. Each metric is fetched,
// cached and retried on its own, so one cold-cache timeout never blanks the
// other two tiles (#10793, mirroring PerformanceDashboard since #10755).
export type GroupBenchmarkMetricKey = 'alpha' | 'trackingError' | 'maxDrawdown';
export type GroupBenchmarkMetrics = Record<
  GroupBenchmarkMetricKey,
  number | null
>;

const METRIC_KEYS: GroupBenchmarkMetricKey[] = [
  'alpha',
  'trackingError',
  'maxDrawdown',
];
const BENCHMARK_TICKER = 'VWRL.L';

// The data can only change once a day (a 365-day benchmark window), so a
// five-minute window is generous rather than risky -- and an expired value is
// still refreshed behind whatever is already rendered.
const BENCHMARK_METRICS_TTL_MS = 5 * 60_000;

export const GROUP_BENCHMARK_METRIC_LABEL_KEYS: Record<
  GroupBenchmarkMetricKey,
  string
> = {
  alpha: 'dashboard.alphaVsBenchmark',
  trackingError: 'dashboard.trackingError',
  maxDrawdown: 'dashboard.maxDrawdown',
};

// All three are valid for group scope: the backend computes alpha and
// tracking error from the combined group portfolio series (see
// getGroupAlphaVsBenchmark / getGroupTrackingError in api.ts), not by
// averaging per-owner values, so they are meaningful aggregates.
const FETCHERS: Record<
  GroupBenchmarkMetricKey,
  (slug: string) => Promise<number | null>
> = {
  // Async, so a fetcher that throws or misbehaves rejects instead of
  // throwing synchronously out of the effect.
  alpha: async (slug) =>
    (await getGroupAlphaVsBenchmark(slug, BENCHMARK_TICKER)).alpha_vs_benchmark,
  trackingError: async (slug) =>
    (await getGroupTrackingError(slug, BENCHMARK_TICKER)).tracking_error,
  maxDrawdown: async (slug) => (await getGroupMaxDrawdown(slug)).max_drawdown,
};

const cacheKeyFor = (slug: string, key: GroupBenchmarkMetricKey) =>
  `group-benchmark-metrics:${slug}:${key}`;

const cachedMetrics = (slug: string): GroupBenchmarkMetrics => ({
  alpha:
    readFetchCache<number | null>(cacheKeyFor(slug, 'alpha'))?.value ?? null,
  trackingError:
    readFetchCache<number | null>(cacheKeyFor(slug, 'trackingError'))?.value ??
    null,
  maxDrawdown:
    readFetchCache<number | null>(cacheKeyFor(slug, 'maxDrawdown'))?.value ??
    null,
});

/**
 * Load one metric; resolves to its key when it failed with nothing on screen.
 *
 * A cached value is applied first. A failed refresh of a cached value stays
 * quiet and keeps it, for the same reason `useFetch` does, so only a cold
 * failure counts as failed and offers Retry.
 */
function loadMetric(
  slug: string,
  key: GroupBenchmarkMetricKey,
  isCurrent: () => boolean,
  apply: (key: GroupBenchmarkMetricKey, value: number | null) => void
): Promise<GroupBenchmarkMetricKey | null> {
  const cacheKey = cacheKeyFor(slug, key);
  const cached = readFetchCache<number | null>(cacheKey);
  if (cached) {
    apply(key, cached.value);
    if (isFresh(cached, BENCHMARK_METRICS_TTL_MS)) return Promise.resolve(null);
  }
  return runDeduped(cacheKey, () => FETCHERS[key](slug)).then(
    (value) => {
      if (isCurrent()) apply(key, value);
      return null;
    },
    (err: unknown) => {
      if (!cached) return key;
      console.warn('Background refresh of benchmark metrics failed', err);
      return null;
    }
  );
}

export type GroupBenchmarkMetricsState = {
  metrics: GroupBenchmarkMetrics;
  failedMetrics: GroupBenchmarkMetricKey[];
  retrying: boolean;
  retryFailedMetrics: () => void;
};

export function useGroupBenchmarkMetrics(
  slug: string,
  enabled: boolean
): GroupBenchmarkMetricsState {
  const [metrics, setMetrics] = useState<GroupBenchmarkMetrics>(() =>
    cachedMetrics(slug)
  );
  const [failedMetrics, setFailedMetrics] = useState<GroupBenchmarkMetricKey[]>(
    []
  );
  const [retrying, setRetrying] = useState(false);
  // Bumped whenever the group changes or the view unmounts, so a load or
  // retry started for an earlier group never writes into this one.
  const loadGeneration = useRef(0);

  // Effects run after the commit, so switching group would otherwise leave the
  // previous group's values rendered under the new group's heading until its
  // requests settle. Swap them during render instead, the same way `useFetch`
  // swaps on a cache-key change.
  const [trackedSlug, setTrackedSlug] = useState(slug);
  if (trackedSlug !== slug) {
    setTrackedSlug(slug);
    setMetrics(cachedMetrics(slug));
    setFailedMetrics([]);
    setRetrying(false);
  }

  const loadMetrics = useCallback(
    (keys: GroupBenchmarkMetricKey[], isCurrent: () => boolean) => {
      const apply = (key: GroupBenchmarkMetricKey, value: number | null) =>
        setMetrics((previous) =>
          previous[key] === value ? previous : { ...previous, [key]: value }
        );
      return Promise.all(
        keys.map((key) => loadMetric(slug, key, isCurrent, apply))
      ).then((results) => {
        if (!isCurrent()) return;
        const failed = results.filter(
          (key): key is GroupBenchmarkMetricKey => key !== null
        );
        // Metrics not requested this time keep their previous state, so a
        // retry never forgets a failure it did not retry.
        setFailedMetrics((previous) =>
          METRIC_KEYS.filter((key) =>
            keys.includes(key) ? failed.includes(key) : previous.includes(key)
          )
        );
      });
    },
    [slug]
  );

  useEffect(() => {
    if (!slug || !enabled) return;
    loadGeneration.current += 1;
    const generation = loadGeneration.current;
    void loadMetrics(METRIC_KEYS, () => loadGeneration.current === generation);
    return () => {
      loadGeneration.current += 1;
    };
  }, [slug, enabled, loadMetrics]);

  // Refetch only the metrics that failed, keeping the ones already shown.
  const retryFailedMetrics = useCallback(() => {
    const generation = loadGeneration.current;
    const isCurrent = () => loadGeneration.current === generation;
    setRetrying(true);
    void loadMetrics(failedMetrics, isCurrent).finally(() => {
      if (isCurrent()) setRetrying(false);
    });
  }, [failedMetrics, loadMetrics]);

  return { metrics, failedMetrics, retrying, retryFailedMetrics };
}
