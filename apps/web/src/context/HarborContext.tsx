import { createContext, useContext } from 'react';

import type { Identity } from '@/api/harbor';
export const HarborContext = createContext<Identity | null>(null);
export function useHarbor() {
  const identity = useContext(HarborContext);
  if (!identity) throw new Error('请先登录');
  return identity;
}
