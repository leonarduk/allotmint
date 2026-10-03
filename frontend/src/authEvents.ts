// Auth-state change notifications. api.setAuthToken emits here whenever the
// token actually changes; modules that own per-user state (e.g. the chat
// conversation) subscribe, so the API client never imports UI code.
//
// A change from null to a token is either a login or a reload re-applying the
// stored token, and a token to a different token is usually a refresh for the
// same user, so subscribers that must survive a reload should react only to
// `isLogout`.
export type AuthChange = {
  previousToken: string | null;
  nextToken: string | null;
};

export type AuthChangeListener = (change: AuthChange) => void;

const listeners = new Set<AuthChangeListener>();

export function isLogout({ previousToken, nextToken }: AuthChange): boolean {
  return previousToken !== null && nextToken === null;
}

export function onAuthChange(listener: AuthChangeListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function emitAuthChange(change: AuthChange) {
  for (const listener of [...listeners]) {
    try {
      listener(change);
    } catch (error) {
      // One failing subscriber must not stop the others or the token change.
      console.error('Auth change listener failed:', error);
    }
  }
}
