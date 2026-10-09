import type {components} from './api';

type Schemas = components['schemas'];

/** The signed-in account as `/auth/me`, login, password change and refresh return it. */
export type AuthenticatedUser = Schemas['AuthenticatedUser'];
export type LoginResponse = Schemas['LoginResponse'];
export type PasswordChangeRequest = Schemas['PasswordChangeRequest'];

/** Super-admin account administration (user-accounts Requirement 2 and 5). */
export type UserSummary = Schemas['UserSummary'];
export type UserPage = Schemas['UserPage'];
export type UserCreateRequest = Schemas['UserCreateRequest'];
export type UserCreated = Schemas['UserCreated'];
export type OneTimePassword = Schemas['OneTimePassword'];
export type ApplicationRole = Schemas['RoleChange']['role'];
export type RoleChange = Schemas['RoleChange'];
export type ActiveChange = Schemas['ActiveChange'];
