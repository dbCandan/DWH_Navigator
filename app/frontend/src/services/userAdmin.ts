import {apiRequest} from '@/lib/apiClient';
import type {
  ActiveChange,
  ApplicationRole,
  OneTimePassword,
  RoleChange,
  UserCreateRequest,
  UserCreated,
  UserPage,
  UserSummary,
} from '@/types/auth';

const path = (user: Pick<UserSummary, 'public_id'>, action: string) =>
  `/admin/users/${encodeURIComponent(user.public_id)}/${action}`;

/** Super-admin account administration (user-accounts Requirement 2 and 5). */
export const UserAdminService = {
  list(params: {page: number; size: number; q?: string}): Promise<UserPage> {
    const query = new URLSearchParams({page: String(params.page), size: String(params.size)});
    if (params.q) query.set('q', params.q);
    return apiRequest<UserPage>(`/admin/users?${query.toString()}`);
  },
  create(body: UserCreateRequest): Promise<UserCreated> {
    return apiRequest<UserCreated>('/admin/users', {method: 'POST', body: JSON.stringify(body)});
  },
  setRole(user: Pick<UserSummary, 'public_id'>, role: ApplicationRole): Promise<RoleChange> {
    return apiRequest<RoleChange>(path(user, 'role'), {method: 'PUT', body: JSON.stringify({role})});
  },
  setActive(user: Pick<UserSummary, 'public_id'>, active: boolean): Promise<ActiveChange> {
    return apiRequest<ActiveChange>(path(user, 'active'), {method: 'PUT', body: JSON.stringify({active})});
  },
  resetPassword(user: Pick<UserSummary, 'public_id'>): Promise<OneTimePassword> {
    return apiRequest<OneTimePassword>(path(user, 'password-reset'), {method: 'POST'});
  },
};
