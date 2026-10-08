import type {AuthenticatedUser} from '@/types/auth';

export const ROLE_USER = 'kullanici';
export const ROLE_MANAGER = 'yonetici';
export const APPLICATION_ROLES = [ROLE_USER, ROLE_MANAGER] as const;

/**
 * What the screens offer to the signed-in account (user-accounts Requirement 10 and 16). It only
 * shapes menus and routes; the backend checks the role on every request.
 */
export interface Access {
  /** The admin screen: `yonetici` and the super admin. */
  administer: boolean;
  /** The Kullanıcılar page: the super admin only. */
  manageUsers: boolean;
}

export function accessOf(user: AuthenticatedUser | null): Access {
  if (user === null) return {administer: false, manageUsers: false};
  const superAdmin = Boolean(user.is_super_admin);
  return {administer: superAdmin || user.role === ROLE_MANAGER, manageUsers: superAdmin};
}
