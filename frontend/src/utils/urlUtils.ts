/**
 * Utilities for encoding and decoding URL path segments.
 *
 * Owner values stored in state are always decoded (human-readable).
 * Owner values embedded in URL paths are always percent-encoded via
 * encodePathSegment before being passed to navigate().
 *
 * Note: window.location.pathname in browsers returns percent-encoded strings
 * for most characters. The segments extracted from it should be decoded with
 * decodePathSegment before being stored in state.
 */

/**
 * Decode a percent-encoded URL path segment.
 * Falls back to the raw value if the segment is malformed.
 */
export function decodePathSegment(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch (error) {
    console.warn("Failed to decode owner path segment; using raw value", {
      segment,
      error,
    });
    return segment;
  }
}

/**
 * Encode a string for safe inclusion as a URL path segment.
 * Trims whitespace before encoding.
 */
export function encodePathSegment(segment: string): string {
  return encodeURIComponent(segment.trim());
}
