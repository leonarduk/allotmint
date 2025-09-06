export function loadJSON<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function saveJSON<T>(key: string, value: T): void {
  window.localStorage.setItem(key, JSON.stringify(value));
}

export function remove(key: string): void {
  window.localStorage.removeItem(key);
}
