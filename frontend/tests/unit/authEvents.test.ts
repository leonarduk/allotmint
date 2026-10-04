import { afterEach, describe, expect, it, vi } from 'vitest';
import { emitAuthChange, isLogout, onAuthChange } from '@/authEvents';

describe('authEvents', () => {
  const unsubscribers: Array<() => void> = [];
  const subscribe = (listener: Parameters<typeof onAuthChange>[0]) => {
    unsubscribers.push(onAuthChange(listener));
  };

  afterEach(() => {
    unsubscribers.splice(0).forEach((unsubscribe) => unsubscribe());
    vi.restoreAllMocks();
  });

  it('delivers each change to every subscriber', () => {
    const first = vi.fn();
    const second = vi.fn();
    subscribe(first);
    subscribe(second);

    emitAuthChange({ previousToken: 'a', nextToken: null });

    expect(first).toHaveBeenCalledWith({ previousToken: 'a', nextToken: null });
    expect(second).toHaveBeenCalledWith({
      previousToken: 'a',
      nextToken: null,
    });
  });

  it('stops delivering after unsubscribe', () => {
    const listener = vi.fn();
    const unsubscribe = onAuthChange(listener);
    unsubscribe();

    emitAuthChange({ previousToken: 'a', nextToken: null });

    expect(listener).not.toHaveBeenCalled();
  });

  it('keeps notifying the rest when one subscriber throws', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const after = vi.fn();
    subscribe(() => {
      throw new Error('boom');
    });
    subscribe(after);

    expect(() =>
      emitAuthChange({ previousToken: 'a', nextToken: null })
    ).not.toThrow();
    expect(after).toHaveBeenCalled();
  });

  it('treats only a token-to-null change as a logout', () => {
    expect(isLogout({ previousToken: 'a', nextToken: null })).toBe(true);
    // Login, or a reload re-applying the stored token.
    expect(isLogout({ previousToken: null, nextToken: 'a' })).toBe(false);
    // Token refresh for the same user.
    expect(isLogout({ previousToken: 'a', nextToken: 'b' })).toBe(false);
  });
});
