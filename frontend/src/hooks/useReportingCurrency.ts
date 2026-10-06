import { useCallback, useEffect, useMemo, useState } from 'react';

import { getGbpRate, type GbpRate } from '../api';
import { useConfig } from '../ConfigContext';
import { currencySymbol, money, normalizeDisplayCurrency } from '../lib/money';

/** Formats an amount held in `sourceCurrency` (GBP when omitted). */
export type MoneyFormatter = (
  value: number | null | undefined,
  sourceCurrency?: string | null
) => string;

/**
 * - `gbp`: the configured base currency is GBP, so nothing to convert.
 * - `loading`: the GBP rate for the base currency is being fetched.
 * - `converted`: GBP amounts are shown in the base currency.
 * - `unavailable`: there is no rate, so GBP amounts stay in GBP.
 */
export type ReportingStatus = 'gbp' | 'loading' | 'converted' | 'unavailable';

export interface ReportingCurrency {
  /** The currency GBP amounts are actually shown in right now. */
  currency: string;
  /** `currency`'s symbol, for column headers such as "Mkt £" (#9805). */
  symbol: string;
  /** The configured base currency, which `currency` matches once converted. */
  configuredCurrency: string;
  status: ReportingStatus;
  /** GBP per one unit of `configuredCurrency`, when known. */
  gbpPerUnit: number | null;
  /** A GBP amount in `currency`. */
  convertGbp: (value: number) => number;
  format: MoneyFormatter;
}

// One request per currency for the page's lifetime: every view shares it.
const rateRequests = new Map<string, Promise<GbpRate>>();

/** Forget fetched rates (tests, or after the base currency's rate changes). */
export function clearReportingRateCache(): void {
  rateRequests.clear();
}

function loadRate(currency: string): Promise<GbpRate> {
  let request = rateRequests.get(currency);
  if (!request) {
    request = getGbpRate(currency);
    rateRequests.set(currency, request);
    // A failed request is retried by the next view that asks.
    request.catch(() => rateRequests.delete(currency));
  }
  return request;
}

function usableRate(rate: number | null | undefined): number | null {
  return typeof rate === 'number' && Number.isFinite(rate) && rate > 0
    ? rate
    : null;
}

function useGbpRate(
  currency: string
): { currency: string; gbpPerUnit: number | null } | null {
  const [loaded, setLoaded] = useState<{
    currency: string;
    gbpPerUnit: number | null;
  } | null>(null);
  useEffect(() => {
    if (currency === 'GBP') return undefined;
    let active = true;
    loadRate(currency)
      .then((rate) => {
        if (active)
          setLoaded({ currency, gbpPerUnit: usableRate(rate.gbp_per_unit) });
      })
      .catch((error: unknown) => {
        // Shown as "unavailable": amounts stay in GBP rather than being relabelled.
        console.warn(`No GBP rate for ${currency}; showing GBP`, error);
        if (active) setLoaded({ currency, gbpPerUnit: null });
      });
    return () => {
      active = false;
    };
  }, [currency]);
  return loaded?.currency === currency ? loaded : null;
}

function reportingStatus(
  configured: string,
  rate: { gbpPerUnit: number | null } | null
): ReportingStatus {
  if (configured === 'GBP') return 'gbp';
  if (rate === null) return 'loading';
  return rate.gbpPerUnit === null ? 'unavailable' : 'converted';
}

/**
 * Report GBP amounts in the configured base currency (#9768).
 *
 * Every portfolio amount from the backend is GBP, so one GBP rate converts
 * them all: `value / gbpPerUnit`, at today's rate (a translation, not
 * historical-rate accounting). Until that rate is known -- or when there is
 * none -- amounts are formatted in GBP: a value is never labelled with a
 * currency it was not converted to (#9753). Amounts in any other currency
 * (e.g. an instrument's quote price) are formatted as they are.
 */
export function useReportingCurrency(): ReportingCurrency {
  const { reportingCurrency } = useConfig();
  const configured = normalizeDisplayCurrency(reportingCurrency || 'GBP');
  const rate = useGbpRate(configured);
  const status = reportingStatus(configured, rate);
  const gbpPerUnit = status === 'converted' ? (rate?.gbpPerUnit ?? null) : null;
  const currency = gbpPerUnit === null ? 'GBP' : configured;

  const convertGbp = useCallback(
    (value: number) => (gbpPerUnit === null ? value : value / gbpPerUnit),
    [gbpPerUnit]
  );
  const format = useCallback<MoneyFormatter>(
    (value, sourceCurrency) => {
      const source = normalizeDisplayCurrency(sourceCurrency || 'GBP');
      if (source !== 'GBP') return money(value, source);
      const amount =
        typeof value === 'number' && Number.isFinite(value)
          ? convertGbp(value)
          : value;
      return money(amount, currency);
    },
    [convertGbp, currency]
  );

  const symbol = useMemo(() => currencySymbol(currency), [currency]);

  return useMemo(
    () => ({
      currency,
      symbol,
      configuredCurrency: configured,
      status,
      gbpPerUnit,
      convertGbp,
      format,
    }),
    [currency, symbol, configured, status, gbpPerUnit, convertGbp, format]
  );
}
