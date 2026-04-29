import { useState, useCallback, useContext } from 'react';
import type { ReactNode } from 'react';
import { loadStoredAuthUser, persistStoredAuthUser } from './authStorage';
import { AuthContext } from './contexts/auth';

export type { UserProfile } from './contexts/auth';
export { AuthContext } from './contexts/auth';

import type { UserProfile } from './contexts/auth';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<UserProfile | null>(() => loadStoredAuthUser());
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
