import {ApiError} from '@/lib/apiClient';

type Translate = (key: string, values?: Record<string, string | number>) => string;

/** Which form failed: the sign-in or a password change (first sign-in or voluntary). */
export type AccountForm = 'login' | 'password';

function waitMessage(seconds: number | undefined, t: Translate): string {
  if (seconds === undefined) return t('auth.error.tooManyAttempts');
  if (seconds < 60) return t('auth.error.tooManyAttemptsSeconds', {seconds});
  return t('auth.error.tooManyAttemptsMinutes', {minutes: Math.ceil(seconds / 60)});
}

/**
 * The person-facing message for a failed sign-in or password change (user-accounts Requirement
 * 1, 3, 4, 9 and 16). A wrong user name and a wrong password read the same. The password
 * policy's answer is shown as the server words it: it only names the rule that was broken
 * (Requirement 3), never the password or any internal detail. Anything else reads "unavailable".
 */
export function accountErrorMessage(error: unknown, form: AccountForm, t: Translate): string {
  if (!(error instanceof ApiError)) return t('auth.error.unavailable');
  switch (error.code) {
    case 'invalid_credentials':
      return t(form === 'login' ? 'auth.error.invalidCredentials' : 'auth.error.wrongCurrentPassword');
    case 'one_time_password_expired':
      return t('auth.error.oneTimeExpired');
    case 'user_inactive':
      return t('auth.error.inactive');
    case 'password_policy':
      return error.message;
    case 'rate_limited':
      return waitMessage(error.retryAfter, t);
  }
  if (error.status === 429) return waitMessage(error.retryAfter, t);
  if (error.status === 422) return t('auth.error.invalidInput');
  return t('auth.error.unavailable');
}
