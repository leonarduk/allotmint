import { createContext, useContext, useState, useCallback } from "react";
import type { ReactNode } from "react";
import {
  loadStoredAuthUser,
  persistStoredAuthUser,
  type StoredUserProfile,
} from "./authStorage";

export type UserProfile = StoredUserProfile;

interface AuthContextValue {
  user: UserProfile | null;
  setUser: (u: UserProfile | null) => void;
}

// Default context used when no provider is present. The setter is a no-op so
// components can still call it safely in tests or non-authenticated scenarios.
export const AuthContext = createContext<AuthContextValue>({
  user: null,
  setUser: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<UserProfile | null>(() =>
    loadStoredAuthUser(),
  );
  const setUser = useCallback((u: UserProfile | null) => {
    setUserState(u);
    persistStoredAuthUser(u);
  }, []);
  return (
    <AuthContext.Provider value={{ user, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

