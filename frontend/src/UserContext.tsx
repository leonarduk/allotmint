import { createContext, useContext, useState, type ReactNode } from "react";

export interface UserProfile {
  email?: string;
  name?: string;
  picture?: string;
}

interface UserContextValue {
  profile?: UserProfile;
  setProfile: (profile?: UserProfile) => void;
}

const userContext = createContext<UserContextValue>({
  profile: undefined,
  setProfile: () => {},
});

export function UserProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<UserProfile>();
  return (
    <userContext.Provider value={{ profile, setProfile }}>
      {children}
    </userContext.Provider>
  );
}

export function useUser() {
  return useContext(userContext);
}
