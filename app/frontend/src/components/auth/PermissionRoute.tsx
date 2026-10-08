import type {ReactNode} from 'react';
import {useAuth} from '@/contexts/AuthContext';
import {AccessDenied} from './AccessDenied';

/** A generated route that needs one permission; the backend checks it on every request. */
export function PermissionRoute({permission, children}: {permission?: string; children: ReactNode}) {
  const {hasPermission} = useAuth();
  if (permission && !hasPermission(permission)) return <AccessDenied />;
  return <>{children}</>;
}
