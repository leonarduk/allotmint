/**
 * The drawn crop glyph set: twelve allotment species on a 48×48 grid.
 *
 * Shapes are generated from the design canvas source rather than transcribed,
 * so the app and the spec cannot drift apart.
 *
 * Each species is one closed `body` path plus stroke-only `details` and `dots`.
 * The body doubles as a clip path, which is the point of the whole set: a fill
 * rises through the silhouette as the crop grows, so the glyph reports the
 * growth stage itself instead of sitting next to something that does.
 */

import type { GrowthStage } from './plotModel';

export const CROP_SPECIES = [
  'pear',
  'apple',
  'carrot',
  'beetroot',
  'peapod',
  'tomato',
  'pumpkin',
  'corn',
  'leek',
  'strawberry',
  'sunflower',
  'beanpod',
] as const;

export type CropSpecies = (typeof CROP_SPECIES)[number];

interface GlyphShape {
  /** Closed silhouette. Doubles as the clip path the fill rises through. */
  body: string;
  /** Stroke-only extras: stalks, leaves, ribs. Never filled. */
  details: readonly string[];
  /** Seeds and beans, drawn as outlines so they read at tray size. */
  dots: readonly (readonly [number, number, number])[];
}

export const GLYPH_SHAPES: Record<CropSpecies, GlyphShape> = {
  pear: {
    body: 'M24 43.5 C15 43.5 10.5 37.5 10.5 31 C10.5 25.5 15.5 22 17 18 C18.5 13.5 20 8.5 24 8.5 C28 8.5 29.5 13.5 31 18 C32.5 22 37.5 25.5 37.5 31 C37.5 37.5 33 43.5 24 43.5 Z',
    details: [
      'M24 9 L24 3.5',
      'M24.5 5.5 C28 2 33 3 33.5 5.5 C31.5 8.5 27 8.5 24.5 5.5',
    ],
    dots: [],
  },
  apple: {
    body: 'M24 13.5 C20 9 12 10 10 18.5 C8 27 12.5 38.5 17.5 41.5 C20.5 43 22 41.5 24 41.5 C26 41.5 27.5 43 30.5 41.5 C35.5 38.5 40 27 38 18.5 C36 10 28 9 24 13.5 Z',
    details: [
      'M24 13.5 L25.5 5.5',
      'M25.5 7.5 C29.5 3.5 35 4.5 35 7.5 C32.5 11 27.5 10.5 25.5 7.5',
    ],
    dots: [],
  },
  carrot: {
    body: 'M24 44.5 L14.5 20.5 C18 17.5 30 17.5 33.5 20.5 Z',
    details: [
      'M24 19 L24 7.5',
      'M24 12.5 L16 5',
      'M24 12.5 L32 5',
      'M18.5 26 L22 24.5',
      'M21 33 L25 31',
    ],
    dots: [],
  },
  beetroot: {
    body: 'M24 9.5 C33 9.5 38 18 36 27 C34 35 29 40 24 44.5 C19 40 14 35 12 27 C10 18 15 9.5 24 9.5 Z',
    details: ['M24 10 L19 2.5', 'M24 10 L29 2.5', 'M24 10 L24 1.5'],
    dots: [],
  },
  peapod: {
    body: 'M9.5 30 C13.5 15.5 30 7.5 40 11.5 C38 26 23.5 38.5 9.5 30 Z',
    details: [],
    dots: [
      [17, 27.5, 3.2],
      [24, 22.5, 3.2],
      [31, 17.5, 3.2],
    ],
  },
  tomato: {
    body: 'M24 14 C32 14 38 20 38 28 C38 36 32 42 24 42 C16 42 10 36 10 28 C10 20 16 14 24 14 Z',
    details: ['M24 14 L15.5 9.5', 'M24 14 L32.5 9.5', 'M24 14 L24 6.5'],
    dots: [],
  },
  pumpkin: {
    body: 'M24 12 C36 12 42 19.5 42 27 C42 35 34 42 24 42 C14 42 6 35 6 27 C6 19.5 12 12 24 12 Z',
    details: [
      'M16.5 13.5 C12.5 20 12.5 34 16.5 40.5',
      'M31.5 13.5 C35.5 20 35.5 34 31.5 40.5',
      'M24 12 L24 5.5',
      'M24 7 C28 3.5 31.5 4.5 31.5 7',
    ],
    dots: [],
  },
  corn: {
    body: 'M24 5.5 C32 12 35 22 33 32 C32 39 28 43.5 24 43.5 C20 43.5 16 39 15 32 C13 22 16 12 24 5.5 Z',
    details: [
      'M24 11 L24 43',
      'M16.5 19.5 L31.5 19.5',
      'M15 26.5 L33 26.5',
      'M16 33.5 L32 33.5',
      'M15.5 30 C10 32.5 8 38.5 10 43.5',
      'M32.5 30 C38 32.5 40 38.5 38 43.5',
    ],
    dots: [],
  },
  leek: {
    body: 'M19.5 24 C19.5 21 28.5 21 28.5 24 L30 40.5 C30 45.5 18 45.5 18 40.5 Z M20.5 22.5 C17 16 13.5 11 9.5 6.5 C11 13 15 19 19 23.5 Z M27.5 22.5 C31 16 34.5 11 38.5 6.5 C37 13 33 19 29 23.5 Z M22.5 22 C22.5 14.5 23 8.5 24 3.5 C25 8.5 25.5 14.5 25.5 22 Z',
    details: ['M21.5 44.5 L20 47.5', 'M26.5 44.5 L28 47.5'],
    dots: [],
  },
  strawberry: {
    body: 'M24 44.5 C16 38 9 30 9 22.5 C9 15.5 16 12 24 12 C32 12 39 15.5 39 22.5 C39 30 32 38 24 44.5 Z',
    details: ['M24 12 L17.5 6.5', 'M24 12 L30.5 6.5', 'M24 12 L24 4.5'],
    dots: [
      [18, 22, 1.3],
      [24, 20, 1.3],
      [30, 22, 1.3],
      [21, 29, 1.3],
      [27, 29, 1.3],
    ],
  },
  sunflower: {
    body: 'M19.5 21.0 C17.0 13.0 21.0 5.5 24.0 4.5 C27.0 5.5 31.0 13.0 28.5 21.0 Z M23.6 19.0 C27.5 11.6 35.7 9.1 38.5 10.5 C39.9 13.3 37.4 21.5 30.0 25.4 Z M28.0 20.5 C36.0 18.0 43.5 22.0 44.5 25.0 C43.5 28.0 36.0 32.0 28.0 29.5 Z M30.0 24.6 C37.4 28.5 39.9 36.7 38.5 39.5 C35.7 40.9 27.5 38.4 23.6 31.0 Z M28.5 29.0 C31.0 37.0 27.0 44.5 24.0 45.5 C21.0 44.5 17.0 37.0 19.5 29.0 Z M24.4 31.0 C20.5 38.4 12.3 40.9 9.5 39.5 C8.1 36.7 10.6 28.5 18.0 24.6 Z M20.0 29.5 C12.0 32.0 4.5 28.0 3.5 25.0 C4.5 22.0 12.0 18.0 20.0 20.5 Z M18.0 25.4 C10.6 21.5 8.1 13.3 9.5 10.5 C12.3 9.1 20.5 11.6 24.4 19.0 Z M24 15.5 C29 15.5 33.5 20 33.5 25 C33.5 30 29 34.5 24 34.5 C19 34.5 14.5 30 14.5 25 C14.5 20 19 15.5 24 15.5 Z',
    details: [],
    dots: [],
  },
  beanpod: {
    body: 'M24 3.5 C29.5 8.5 32.5 14.5 32.5 22.5 C32.5 32 29.5 40 24 44.5 C18.5 40 15.5 32 15.5 22.5 C15.5 14.5 18.5 8.5 24 3.5 Z',
    details: [],
    dots: [
      [24, 16, 3.1],
      [24, 24, 3.1],
      [24, 32, 3.1],
    ],
  },
};

/**
 * How much of the silhouette is filled at each growth stage.
 *
 * Wilting is deliberately not zero: an empty outline reads as "no data",
 * which is a different and more alarming claim than "down 20%".
 */
export const STAGE_FILL: Record<GrowthStage, number> = {
  wilting: 0.1,
  seed: 0.14,
  sprout: 0.28,
  leafing: 0.42,
  budding: 0.56,
  flowering: 0.7,
  fruiting: 0.85,
  bumper: 1.0,
};
