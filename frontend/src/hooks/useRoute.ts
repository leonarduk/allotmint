import { useContext } from 'react';
import { RouteContext } from '../RouteContext';

export function useRoute() {
  const ctx = useContext(RouteContext);
  if (!ctx) throw new Error('useRoute must be used within RouteProvider');
  return ctx;
}
