import type {ReactNode} from 'react';
import {Outlet} from 'react-router';
import {useAuth} from '@/contexts/AuthContext';
import type {Access} from '@/lib/access';
import {AccessDenied} from './AccessDenied';

/**
 * Show a route only to the roles it is for (user-accounts Requirement 10 and 16). Hiding is not
 * authorization: every request is checked on the backend.
 */
export function RequireAccess({need, children}: {need: keyof Access; children?: ReactNode}) {
  const {access} = useAuth();
  if (!access[need]) return <AccessDenied />;
  return children ?? <Outlet />;
}
