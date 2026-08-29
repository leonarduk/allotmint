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
  // True for the lifetime of a demo-token session (issue #7410) — a visitor
  // who landed via /demo?token=<...> rather than a real sign-in. This is a
  // UI courtesy flag only (drives the read-only banner and, in #7411,
  // hiding mutating controls); it is not itself an authorization boundary —
  // the server-side gates (#7407, #7408) enforce read-only access.
  demoReadOnly: boolean;
  setDemoReadOnly: (value: boolean) => void;
}

// Default context used when no provider is present. The setters are no-ops so
// components can still call them safely in tests or non-authenticated scenarios.
export const AuthContext = createContext<AuthContextValue>({
  user: null,
  setUser: () => {},
  logout: null,
  setLogout: () => {},
  demoReadOnly: false,
  setDemoReadOnly: () => {},
});
