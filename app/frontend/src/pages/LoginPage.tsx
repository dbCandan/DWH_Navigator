import {useState, type FormEvent} from 'react';
import {Navigate, useLocation, useNavigate} from 'react-router';
import {Field} from '@/components/admin/Field';
import {AuthCard} from '@/components/auth/AuthCard';
import {useAuth} from '@/contexts/AuthContext';
import {useIntl} from '@/contexts/IntlContext';
import {accountErrorMessage} from '@/lib/accountErrors';
import {ApiError} from '@/lib/apiClient';

/** Where to go after signing in: the protected page that sent the person here, else the main screen. */
function targetOf(state: unknown): string {
  const from = (state as {from?: unknown} | null)?.from;
  return typeof from === 'string' && from.startsWith('/') && !from.startsWith('//') && from !== '/login' ? from : '/';
}

/**
 * Sign-in (user-accounts Requirement 1 and 16). The message never says whether the user name or
 * the password was wrong. When the account still holds its one-time password, the same screen
 * turns into "Yeni parola belirleyin": the new password twice and the policy in plain words; the
 * change signs the person in.
 */
export default function LoginPage() {
  const {user, login, changePassword} = useAuth();
  const {t} = useIntl();
  const navigate = useNavigate();
  const location = useLocation();
  const target = targetOf(location.state);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [changing, setChanging] = useState(false);
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to={target} replace />;

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      navigate(target, {replace: true});
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === 'password_change_required') setChanging(true);
      else setError(accountErrorMessage(failure, 'login', t));
    } finally {
      setBusy(false);
    }
  }

  async function setNewPassword(event: FormEvent) {
    event.preventDefault();
    if (next !== repeat) {
      setError(t('auth.password.mismatch'));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await changePassword(username, password, next);
      navigate(target, {replace: true});
    } catch (failure) {
      setError(accountErrorMessage(failure, 'password', t));
    } finally {
      setBusy(false);
    }
  }

  if (changing)
    return (
      <AuthCard title={t('auth.firstLogin.title')} lead={t('auth.firstLogin.lead')}>
        <form className="form" onSubmit={setNewPassword}>
          <Field id="new-password" label={t('auth.password.new')} hint={t('auth.password.policy')}>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              aria-describedby="new-password-hint"
              required
              value={next}
              onChange={(e) => setNext(e.target.value)}
            />
          </Field>
          <Field id="repeat-password" label={t('auth.password.repeat')}>
            <input
              id="repeat-password"
              type="password"
              autoComplete="new-password"
              required
              value={repeat}
              onChange={(e) => setRepeat(e.target.value)}
            />
          </Field>
          {error && (
            <div className="msg bad" role="alert">
              {error}
            </div>
          )}
          <button className="btn primary" type="submit" disabled={busy}>
            {busy ? t('auth.password.saving') : t('auth.firstLogin.submit')}
          </button>
        </form>
      </AuthCard>
    );

  return (
    <AuthCard title={t('auth.login.title')} lead={t('auth.login.subtitle')}>
      <form className="form" onSubmit={signIn}>
        <Field id="username" label={t('auth.login.username')}>
          <input
            id="username"
            type="text"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </Field>
        <Field id="password" label={t('auth.login.password')}>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        {error && (
          <div className="msg bad" role="alert">
            {error}
          </div>
        )}
        <button className="btn primary" type="submit" disabled={busy}>
          {busy ? t('auth.login.busy') : t('auth.login.submit')}
        </button>
      </form>
    </AuthCard>
  );
}
