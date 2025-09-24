export type StoredUserProfile = {
  email?: string;
  name?: string;
  picture?: string;
};

export const AUTH_USER_STORAGE_KEY = 'auth.user';
export const USER_PROFILE_STORAGE_KEY = 'user.profile';

type MaybeStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

const getStorage = (): MaybeStorage | undefined => {
  if (typeof localStorage === 'undefined') return undefined;
  return localStorage;
};

const safeParse = (value: string | null): StoredUserProfile | null => {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as StoredUserProfile;
    if (parsed && typeof parsed === 'object') {
      return {
        email: parsed.email,
        name: parsed.name,
        picture: parsed.picture,
      };
    }
  } catch {
    // ignore malformed JSON
  }
  return null;
};

export const loadStoredAuthUser = (): StoredUserProfile | null => {
  const storage = getStorage();
  if (!storage) return null;
  return safeParse(storage.getItem(AUTH_USER_STORAGE_KEY));
};

export const persistStoredAuthUser = (user: StoredUserProfile | null) => {
  const storage = getStorage();
  if (!storage) return;
  if (user) storage.setItem(AUTH_USER_STORAGE_KEY, JSON.stringify(user));
  else storage.removeItem(AUTH_USER_STORAGE_KEY);
};

export const loadStoredUserProfile = (): StoredUserProfile | undefined => {
  const storage = getStorage();
  if (!storage) return undefined;
  const parsed = safeParse(storage.getItem(USER_PROFILE_STORAGE_KEY));
  return parsed ?? undefined;
};

export const persistStoredUserProfile = (profile?: StoredUserProfile) => {
  const storage = getStorage();
  if (!storage) return;
  if (profile) storage.setItem(USER_PROFILE_STORAGE_KEY, JSON.stringify(profile));
  else storage.removeItem(USER_PROFILE_STORAGE_KEY);
};
