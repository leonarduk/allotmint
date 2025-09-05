import { createContext, useContext, useState, type ReactNode } from "react";

export interface UserProfile {
  email?: string;
  name?: string;
  picture?: string;
}

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
  const [user, setUser] = useState<UserProfile | null>(null);
  return (
    <AuthContext.Provider value={{ user, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

