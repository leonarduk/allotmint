import { dismissLastVisit, recordLastVisit } from '../api';
import { loadJSON, remove, saveJSON } from '../utils/storage';
import { advanceVisitRecord, dismissVisitRecord, type VisitRecord } from './sinceLastVisit';

/**
 * Where the since-last-visit digest keeps the viewer's visits (#11195).
 *
 * A signed-in user's visits live on the server (POST /last-visit/{slug}), so
 * they follow the user across devices and are never shared by two people on
 * one browser profile. This browser's localStorage record is the fallback:
 * with no signed-in user or in a demo session (the server answers
 * ``stored: false``), and while the API is unavailable.
 *
 * The first server call sends the localStorage record as a seed, which the
 * server uses only if it has no record for the group yet, so the move to the
 * server does not cost anyone a digest. Once the server holds the record the
 * local copy is removed, so a later outage falls back to a fresh local record
 * (no digest) rather than to a stale one.
 */

export const LAST_VISIT_KEY_PREFIX = 'allotmint.lastVisit.';

/** Which store holds this visit, so a dismissal goes to the same place. */
export type VisitSource = 'server' | 'local';

export interface RecordedVisit {
  /** Epoch ms of the previous visit, or null on a first visit. */
  since: number | null;
  source: VisitSource;
}

const keyFor = (slug: string): string => `${LAST_VISIT_KEY_PREFIX}${slug}`;

const isTimestamp = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

function parseInstant(value: string | null): number | null {
  if (value === null) return null;
  const at = Date.parse(value);
  return Number.isFinite(at) ? at : null;
}

/** The localStorage record as ISO instants, or undefined when there is none worth sending. */
function seedFrom(record: Partial<VisitRecord> | null) {
  if (!record || !isTimestamp(record.current)) return undefined;
  return {
    previous: isTimestamp(record.previous) ? new Date(record.previous).toISOString() : null,
    current: new Date(record.current).toISOString(),
  };
}

function persistLocal(slug: string, record: VisitRecord): void {
  try {
    saveJSON(keyFor(slug), record);
  } catch (err) {
    console.warn('Could not persist last-visit timestamp', err);
  }
}

function forgetLocal(slug: string): void {
  try {
    remove(keyFor(slug));
  } catch (err) {
    console.warn('Could not clear the local last-visit timestamp', err);
  }
}

function recordLocalVisit(slug: string, now: number): RecordedVisit {
  const record = advanceVisitRecord(loadJSON<VisitRecord | null>(keyFor(slug), null), now);
  persistLocal(slug, record);
  return { since: record.previous, source: 'local' };
}

/**
 * Record this visit to ``slug`` and return the previous one. Never rejects:
 * any server failure falls back to this browser's record. Blocked storage on
 * that path means the digest just never shows, the same as a first visit.
 */
export async function recordVisit(slug: string, now: number): Promise<RecordedVisit> {
  try {
    const seed = seedFrom(loadJSON<Partial<VisitRecord> | null>(keyFor(slug), null));
    const visit = await recordLastVisit(slug, seed);
    if (visit.stored) {
      forgetLocal(slug);
      return { since: parseInstant(visit.previous), source: 'server' };
    }
  } catch (err) {
    console.warn("Last visit unavailable from the server; using this browser's record", err);
  }
  return recordLocalVisit(slug, now);
}

/** Mark everything up to ``now`` as seen for ``slug`` (the card was dismissed). */
export async function recordDismissal(slug: string, now: number, source: VisitSource): Promise<void> {
  if (source === 'server') {
    try {
      const visit = await dismissLastVisit(slug);
      if (visit.stored) return;
    } catch (err) {
      // The server holds this visit, so a local record would never be read
      // back: the next load asks the server, which still has the visit. The
      // dismissal is lost rather than recorded somewhere nothing reads it.
      console.warn('Could not record the dismissal on the server', err);
      return;
    }
  }
  persistLocal(slug, dismissVisitRecord(now));
}
