import { createContext } from 'react';
import type { StoredUserProfile } from '../authStorage';

export type UserProfile = StoredUserProfile;

export interface AuthContextValue {
  user: UserProfile | null;
  setUser: (u: UserProfile | null) => void;
  // Session-ending callback registered by the app shell (main.tsx's Root),
  // once the auth mode (Cognito vs local disable_auth) is known. Null until
  // registered, so consumers like Menu can tell "not authenticated yet" apart
  // from "no-op". This lets Menu render a working logout control regardless
  // of whether the page that mounts it remembers to thread an onLogout prop
  // through (see #4751 — the button was disappearing on standalone routes).
  logout: (() => void) | null;
  setLogout: (fn: (() => void) | null) => void;
}

// Default context used when no provider is present. The setters are no-ops so
// components can still call them safely in tests or non-authenticated scenarios.
export const AuthContext = createContext<AuthContextValue>({
  user: null,
  setUser: () => {},
  logout: null,
  setLogout: () => {},
});
