import { useState, useCallback, useContext } from 'react';
import type { ReactNode } from 'react';
import { loadStoredAuthUser, persistStoredAuthUser } from './authStorage';
import { isDemoSession } from './demoAuth';
import { AuthContext } from './contexts/auth';
import type { UserProfile } from './contexts/auth';

export type { UserProfile } from './contexts/auth';
export { AuthContext } from './contexts/auth';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<UserProfile | null>(() =>
    loadStoredAuthUser()
  );
  const [logout, setLogoutState] = useState<(() => void) | null>(null);
  // Seeded from the sessionStorage marker set by applyDemoTokenFromUrl()
  // during bootstrap, which always runs before this provider mounts.
  const [demoReadOnly, setDemoReadOnlyState] = useState<boolean>(() =>
    isDemoSession()
  );
  const setUser = useCallback((u: UserProfile | null) => {
    setUserState(u);
    persistStoredAuthUser(u);
  }, []);
  const setLogout = useCallback((fn: (() => void) | null) => {
    setLogoutState(() => fn);
  }, []);
  const setDemoReadOnly = useCallback((value: boolean) => {
    setDemoReadOnlyState(value);
  }, []);
  return (
    <AuthContext.Provider
      value={{
        user,
        setUser,
        logout,
        setLogout,
        demoReadOnly,
        setDemoReadOnly,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  return useContext(AuthContext);
}
