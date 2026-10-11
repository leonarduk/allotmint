import { useCallback, useEffect, useRef, useState } from 'react';
import { getScreenerRiskReturn } from '../api';
import type { ScreenerRiskReturn } from '../types';

/**
 * "idle": nothing requested yet; "unavailable": this deployment lacks the
 * risk/return engine (HTTP 402) so the columns stay hidden.
 */
export type RiskReturnStatus =
  'idle' | 'loading' | 'ready' | 'unavailable' | 'error';

export interface RiskReturnState {
  status: RiskReturnStatus;
  data: ScreenerRiskReturn | null;
  error: string | null;
}

const IDLE: RiskReturnState = { status: 'idle', data: null, error: null };

function isPayload(value: unknown): value is ScreenerRiskReturn {
  const v = value as ScreenerRiskReturn | null | undefined;
  return Boolean(v && Array.isArray(v.rows) && Array.isArray(v.missing));
}

function failureState(e: unknown): RiskReturnState {
  const status = (e as { status?: number } | undefined)?.status;
  // 402 is the expected answer from a deployment without allotmint-pro:
  // hide the columns quietly rather than reporting an error.
  if (status === 402) return { status: 'unavailable', data: null, error: null };
  return {
    status: 'error',
    data: null,
    error: e instanceof Error ? e.message : String(e),
  };
}

/**
 * Loads risk/return figures for a ticker set independently of the
 * fundamentals screen, so the fundamentals table never waits on it
 * (allotmint#10607). A newer `load` aborts the previous request.
 */
export function useScreenerRiskReturn() {
  const [state, setState] = useState<RiskReturnState>(IDLE);
  const controllerRef = useRef<AbortController | null>(null);

  // Once the backend has said 402 it won't change its mind this session,
  // so later runs skip the request entirely.
  const unavailableRef = useRef(false);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const settle = useCallback((next: RiskReturnState) => {
    if (next.status === 'unavailable') unavailableRef.current = true;
    setState(next);
  }, []);

  const load = useCallback(
    (symbols: string[]) => {
      if (unavailableRef.current) return;
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setState({ status: 'loading', data: null, error: null });
      // Wrapped so even a synchronous throw lands in .catch below.
      Promise.resolve()
        .then(() => getScreenerRiskReturn(symbols, {}, controller.signal))
        .then((data) => {
          if (controller.signal.aborted) return;
          settle(
            isPayload(data)
              ? { status: 'ready', data, error: null }
              : failureState(new Error('Unexpected risk/return response'))
          );
        })
        .catch((e: unknown) => {
          if (controller.signal.aborted) return;
          settle(failureState(e));
        });
    },
    [settle]
  );

  return { ...state, load };
}
