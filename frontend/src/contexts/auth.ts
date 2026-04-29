import { createContext } from 'react';
import type { StoredUserProfile } from '../authStorage';

export type UserProfile = StoredUserProfile;

export interface AuthContextValue {
  user: UserProfile | null;
  setUser: (u: UserProfile | null) => void;
}

// Default context used when no provider is present. The setter is a no-op so
// components can still call it safely in tests or non-authenticated scenarios.
export const AuthContext = createContext<AuthContextValue>({
  user: null,
  setUser: () => {},
});
