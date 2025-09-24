import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import {
  loadStoredUserProfile,
  persistStoredUserProfile,
  type StoredUserProfile,
} from "./authStorage";

export type UserProfile = StoredUserProfile;

interface UserContextValue {
  profile?: UserProfile;
  setProfile: (profile?: UserProfile) => void;
}

const userContext = createContext<UserContextValue>({
  profile: undefined,
  setProfile: () => {},
});

export function UserProvider({ children }: { children: ReactNode }) {
  const [profile, setProfileState] = useState<UserProfile | undefined>(() =>
    loadStoredUserProfile(),
  );
  const setProfile = useCallback((profile?: UserProfile) => {
    setProfileState(profile);
    persistStoredUserProfile(profile);
  }, []);
  return (
    <userContext.Provider value={{ profile, setProfile }}>
      {children}
    </userContext.Provider>
  );
}

export function useUser() {
  return useContext(userContext);
}
