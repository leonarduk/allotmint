import { useState, useCallback, useContext } from 'react';
import type { ReactNode } from 'react';
import { loadStoredAuthUser, persistStoredAuthUser } from './authStorage';
import { AuthContext } from './contexts/auth';
import type { UserProfile } from './contexts/auth';

export type { UserProfile } from './contexts/auth';
export { AuthContext } from './contexts/auth';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<UserProfile | null>(() => loadStoredAuthUser());
  const [logout, setLogoutState] = useState<(() => void) | null>(null);
  const setUser = useCallback((u: UserProfile | null) => {
    setUserState(u);
    persistStoredAuthUser(u);
  }, []);
  const setLogout = useCallback((fn: (() => void) | null) => {
    setLogoutState(() => fn);
  }, []);
  return (
    <AuthContext.Provider value={{ user, setUser, logout, setLogout }}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  return useContext(AuthContext);
}
