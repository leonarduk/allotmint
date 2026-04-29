import { createContext } from 'react';
import type { Mode } from '../modes';

export interface RouteContextValue {
  mode: Mode;
  setMode: (m: Mode) => void;
  selectedOwner: string;
  setSelectedOwner: (s: string) => void;
  selectedGroup: string;
  setSelectedGroup: (s: string) => void;
}

export const RouteContext = createContext<RouteContextValue | undefined>(undefined);
