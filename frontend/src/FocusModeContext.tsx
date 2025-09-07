import { createContext, useContext, useState, type ReactNode } from 'react';

interface FocusModeContextValue {
  focusMode: boolean;
  setFocusMode: (on: boolean) => void;
}

const defaultValue: FocusModeContextValue = {
  focusMode: false,
  setFocusMode: () => {},
};

export const FocusModeContext = createContext<FocusModeContextValue>(defaultValue);

export function FocusModeProvider({ children }: { children: ReactNode }) {
  const [focusMode, setFocusMode] = useState(false);
  return (
    <FocusModeContext.Provider value={{ focusMode, setFocusMode }}>
      {children}
    </FocusModeContext.Provider>
  );
}

export function useFocusMode() {
  return useContext(FocusModeContext);
}

