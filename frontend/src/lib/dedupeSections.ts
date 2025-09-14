export interface Section<T> {
  /** Human-readable section title */
  title: string;
  /** Items belonging to the section */
  cards: T[];
}

/**
 * Merge sections with identical titles by concatenating their card lists.
 *
 * A new array is returned and the original input is left unmodified.
 */
export function dedupeSections<T>(sections: Section<T>[]): Section<T>[] {
  const map = new Map<string, T[]>();
  for (const { title, cards } of sections) {
    const existing = map.get(title);
    if (existing) {
      existing.push(...cards);
    } else {
      map.set(title, [...cards]);
    }
  }
  return Array.from(map.entries()).map(([title, cards]) => ({ title, cards }));
}
