import {useState, type FormEvent} from 'react';
import {Link, useLocation} from 'react-router';
import {Field} from '@/components/admin/Field';
import {AuthCard} from '@/components/auth/AuthCard';
import {useAuth} from '@/contexts/AuthContext';
import {useIntl} from '@/contexts/IntlContext';
import {accountErrorMessage} from '@/lib/accountErrors';

/** The screen to go back to: the one that opened "Parolamı değiştir", else the main screen. */
function returnOf(state: unknown): string {
  const from = (state as {from?: unknown} | null)?.from;
  return typeof from === 'string' && from.startsWith('/') && !from.startsWith('//') && from !== '/parola' ? from : '/';
}

/**
 * "Parolamı değiştir" (user-accounts Requirement 4 and 16): the current password, the new one and
 * its repeat. The change closes the person's other sessions and keeps this one.
 */
export default function PasswordChangePage() {
  const {user, changePassword} = useAuth();
  const {t} = useIntl();
  const location = useLocation();
  const back = returnOf(location.state);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!user) return;
    if (next !== repeat) {
      setError(t('auth.password.mismatch'));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await changePassword(user.username, current, next);
      setDone(true);
    } catch (failure) {
      setError(accountErrorMessage(failure, 'password', t));
    } finally {
      setBusy(false);
    }
  }

  const links = (
    <div className="auth-links">
      <Link to={back}>{t('auth.password.back')}</Link>
    </div>
  );

  if (done)
    return (
      <AuthCard title={t('auth.password.title')}>
        <div className="msg ok" role="status">
          {t('auth.password.changed')}
        </div>
        {links}
      </AuthCard>
    );

  return (
    <AuthCard title={t('auth.password.title')} lead={t('auth.password.lead')}>
      <form className="form" onSubmit={submit}>
        <Field id="current-password" label={t('auth.password.current')}>
          <input
            id="current-password"
            type="password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </Field>
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
          {busy ? t('auth.password.saving') : t('auth.password.submit')}
        </button>
      </form>
      {links}
    </AuthCard>
  );
}
