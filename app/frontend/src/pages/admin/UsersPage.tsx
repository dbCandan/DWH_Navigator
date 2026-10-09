import {useEffect, useState, type FormEvent} from 'react';
import {Drawer} from '@/components/admin/Drawer';
import {Field} from '@/components/admin/Field';
import {Icon} from '@/components/admin/Icon';
import {PageHead} from '@/components/admin/PageHead';
import {useToast} from '@/hooks/useToast';
import {useAuth} from '@/contexts/AuthContext';
import {useIntl} from '@/contexts/IntlContext';
import {APPLICATION_ROLES, ROLE_MANAGER, ROLE_USER} from '@/lib/access';
import {ApiError} from '@/lib/apiClient';
import {formatDateTime, formatNumber, formatWhen} from '@/lib/format';
import {UserAdminService} from '@/services/userAdmin';
import type {ApplicationRole, UserPage, UserSummary} from '@/types/auth';
import './users.css';

const PAGE_SIZE = 50;
const SEARCH_DELAY_MS = 250;

/** Catalog keys of the error codes this page can meet; anything else is a generic failure. */
const ERROR_KEYS: Record<string, string> = {
  username_taken: 'users.error.usernameTaken',
  super_admin_protected: 'users.error.superAdminProtected',
  own_account: 'users.error.ownAccount',
  user_not_found: 'users.error.notFound',
  invalid_request: 'users.error.invalid',
  forbidden: 'users.error.forbidden',
};

type Listing =
  | {state: 'loading'}
  | {state: 'error'; message: string}
  | {state: 'ready'; data: UserPage};

/** A one-time password shown once (user-accounts Requirement 2, 5, 16). */
interface Secret {
  username: string;
  password: string;
  expiresAt: string;
}

const roleKey = (role: string | null) =>
  role === ROLE_MANAGER ? 'users.role.manager' : role === ROLE_USER ? 'users.role.user' : 'users.role.superAdmin';

/**
 * The super admin's Kullanıcılar page (user-accounts Requirement 16): search, a paged list,
 * "Kullanıcı ekle", role change, deactivation and reactivation and "Parolayı sıfırla". A new or
 * reset one-time password shows once, with a copy button and its expiry; it is gone when the
 * drawer closes. Deactivation, role change and reset ask for confirmation in the browser's
 * dialog, as the admin screen's other confirmations do.
 */
export default function UsersPage() {
  const {t} = useIntl();
  const {user: current} = useAuth();
  const {toast, reportUnreachable} = useToast();
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [listing, setListing] = useState<Listing>({state: 'loading'});
  const [busy, setBusy] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [secret, setSecret] = useState<Secret | null>(null);

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      UserAdminService.list({page, size: PAGE_SIZE, q: query.trim() || undefined})
        .then((data) => {
          if (active) setListing({state: 'ready', data});
        })
        .catch((error: unknown) => {
          if (!active) return;
          reportUnreachable(error);
          setListing({state: 'error', message: t('users.loadFailed')});
        });
    }, SEARCH_DELAY_MS);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [page, query, reload, reportUnreachable, t]);

  function failure(error: unknown): string {
    if (error instanceof ApiError && error.code && ERROR_KEYS[error.code]) return t(ERROR_KEYS[error.code]);
    return t('users.error.generic');
  }

  async function act(target: UserSummary, work: () => Promise<string>) {
    setBusy(target.public_id);
    try {
      toast(await work());
      setReload((n) => n + 1);
    } catch (error) {
      if (!reportUnreachable(error)) toast(t('users.failed'), [failure(error)], true);
    } finally {
      setBusy(null);
    }
  }

  function changeRole(target: UserSummary, role: ApplicationRole) {
    if (role === target.role) return;
    const roleName = t(roleKey(role));
    if (!window.confirm(t('users.confirm.role', {username: target.username, role: roleName}))) {
      setReload((n) => n + 1); // put the select back
      return;
    }
    void act(target, async () => {
      await UserAdminService.setRole(target, role);
      return t('users.done.role', {username: target.username, role: roleName});
    });
  }

  function changeActive(target: UserSummary, active: boolean) {
    if (!active && !window.confirm(t('users.confirm.deactivate', {username: target.username}))) return;
    void act(target, async () => {
      await UserAdminService.setActive(target, active);
      return t(active ? 'users.done.activated' : 'users.done.deactivated', {username: target.username});
    });
  }

  async function resetPassword(target: UserSummary) {
    if (!window.confirm(t('users.confirm.reset', {username: target.username}))) return;
    setBusy(target.public_id);
    try {
      const issued = await UserAdminService.resetPassword(target);
      setSecret({
        username: target.username,
        password: issued.one_time_password,
        expiresAt: issued.one_time_password_expires_at,
      });
      setReload((n) => n + 1);
    } catch (error) {
      if (!reportUnreachable(error)) toast(t('users.failed'), [failure(error)], true);
    } finally {
      setBusy(null);
    }
  }

  const data = listing.state === 'ready' ? listing.data : null;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;
  return (
    <section className="page on" id="p-kullanicilar" aria-label={t('admin.page.kullanicilar.label')}>
      <PageHead
        title={t('admin.page.kullanicilar.label')}
        description={t('admin.page.kullanicilar.description')}
        actions={
          <button className="btn primary" type="button" onClick={() => setAdding(true)}>
            <Icon name="plus" />
            {t('users.add')}
          </button>
        }
      />
      <div className="toolbar">
        <input
          type="search"
          placeholder={t('users.search.placeholder')}
          aria-label={t('users.search.label')}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setPage(1);
          }}
        />
        {data && <span className="note">{t('users.count', {count: formatNumber(data.total)})}</span>}
      </div>
      <div className="card grow">
        {listing.state === 'loading' && (
          <div role="status" aria-label={t('users.loading')}>
            <div className="skel" />
            <div className="skel" />
            <div className="skel" />
          </div>
        )}
        {listing.state === 'error' && <div className="msg bad">{listing.message}</div>}
        {data && data.items.length === 0 && <p className="empty">{t('users.empty')}</p>}
        {data && data.items.length > 0 && (
          <div className="list-box">
            <table className="t">
              <thead>
                <tr>
                  <th scope="col">{t('users.column.username')}</th>
                  <th scope="col">{t('users.column.displayName')}</th>
                  <th scope="col">{t('users.column.role')}</th>
                  <th scope="col">{t('users.column.status')}</th>
                  <th scope="col">{t('users.column.lastLogin')}</th>
                  <th scope="col" className="r">
                    {t('users.column.actions')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => {
                  const protectedAccount = item.role === 'super_admin';
                  const own = item.public_id === current?.public_id;
                  const working = busy === item.public_id;
                  return (
                    <tr key={item.public_id}>
                      <td className="nm">{item.username}</td>
                      <td>{item.display_name}</td>
                      <td>
                        {protectedAccount ? (
                          <span className="role">{t('users.role.superAdmin')}</span>
                        ) : (
                          <select
                            aria-label={t('users.roleOf', {username: item.username})}
                            value={item.role ?? ''}
                            disabled={working}
                            onChange={(event) => changeRole(item, event.target.value as ApplicationRole)}
                          >
                            {APPLICATION_ROLES.map((role) => (
                              <option key={role} value={role}>
                                {t(roleKey(role))}
                              </option>
                            ))}
                          </select>
                        )}
                      </td>
                      <td>
                        <span className={'pill' + (item.active ? ' ok' : '')}>
                          {t(item.active ? 'users.status.active' : 'users.status.inactive')}
                        </span>{' '}
                        {item.password_change_required && (
                          <span className="tag warn" title={t('users.status.newPasswordTip')}>
                            {t('users.status.newPassword')}
                          </span>
                        )}
                      </td>
                      <td className="when" title={item.last_login_at ? formatDateTime(item.last_login_at) : undefined}>
                        {item.last_login_at ? formatWhen(item.last_login_at, t) : t('users.never')}
                      </td>
                      <td className="r">
                        {!protectedAccount && (
                          <div className="acts-row">
                            <button
                              className="btn sm"
                              type="button"
                              disabled={working}
                              onClick={() => void resetPassword(item)}
                            >
                              {t('users.reset')}
                            </button>
                            {!own && (
                              <button
                                className={'btn sm' + (item.active ? ' danger' : '')}
                                type="button"
                                disabled={working}
                                onClick={() => changeActive(item, !item.active)}
                              >
                                {t(item.active ? 'users.deactivate' : 'users.activate')}
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {data && pages > 1 && (
          <div className="more">
            <button className="btn sm ghost" type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              {t('users.previous')}
            </button>
            <span className="note">{t('users.pageOf', {page, pages})}</span>
            <button className="btn sm ghost" type="button" disabled={page >= pages} onClick={() => setPage(page + 1)}>
              {t('users.next')}
            </button>
          </div>
        )}
      </div>
      {adding && (
        <AddUserDrawer
          onClose={() => setAdding(false)}
          onCreated={(created) => {
            setAdding(false);
            setSecret(created);
            setReload((n) => n + 1);
          }}
          describe={failure}
        />
      )}
      {secret && <SecretDrawer secret={secret} onClose={() => setSecret(null)} />}
    </section>
  );
}

function AddUserDrawer({
  onClose,
  onCreated,
  describe,
}: {
  onClose: () => void;
  onCreated: (secret: Secret) => void;
  describe: (error: unknown) => string;
}) {
  const {t} = useIntl();
  const {reportUnreachable} = useToast();
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [role, setRole] = useState<ApplicationRole>(ROLE_USER);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const created = await UserAdminService.create({username, display_name: displayName, role});
      onCreated({
        username: created.user.username,
        password: created.one_time_password,
        expiresAt: created.one_time_password_expires_at,
      });
    } catch (failure) {
      if (!reportUnreachable(failure)) setError(describe(failure));
      setSaving(false);
    }
  }

  return (
    <Drawer
      title={t('users.add')}
      sub={t('users.addSub')}
      onClose={onClose}
      foot={
        <>
          <span className="grow" />
          <button className="btn ghost" type="button" onClick={onClose}>
            {t('users.cancel')}
          </button>
          <button className="btn primary" type="submit" form="user-add" disabled={saving}>
            {saving ? t('users.creating') : t('users.create')}
          </button>
        </>
      }
    >
      <form className="form" id="user-add" onSubmit={submit}>
        <Field id="user-username" label={t('users.column.username')} hint={t('users.usernameHint')}>
          <input
            id="user-username"
            type="text"
            className="mono"
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            aria-describedby="user-username-hint"
            required
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </Field>
        <Field id="user-display-name" label={t('users.column.displayName')}>
          <input
            id="user-display-name"
            type="text"
            autoComplete="off"
            required
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
          />
        </Field>
        <Field id="user-role" label={t('users.column.role')}>
          <select id="user-role" value={role} onChange={(event) => setRole(event.target.value as ApplicationRole)}>
            {APPLICATION_ROLES.map((option) => (
              <option key={option} value={option}>
                {t(roleKey(option))}
              </option>
            ))}
          </select>
        </Field>
        <p className="note">{t('users.onceNote')}</p>
        {error && (
          <div className="msg bad" role="alert">
            {error}
          </div>
        )}
      </form>
    </Drawer>
  );
}

function SecretDrawer({secret, onClose}: {secret: Secret; onClose: () => void}) {
  const {t} = useIntl();
  const [copy, setCopy] = useState<'idle' | 'done' | 'failed'>('idle');

  useEffect(() => {
    if (copy === 'idle') return;
    const timer = window.setTimeout(() => setCopy('idle'), 1400);
    return () => window.clearTimeout(timer);
  }, [copy]);

  async function copyPassword() {
    try {
      await navigator.clipboard.writeText(secret.password);
      setCopy('done');
    } catch {
      setCopy('failed');
    }
  }

  return (
    <Drawer
      title={t('users.secret.title')}
      sub={secret.username}
      onClose={onClose}
      foot={
        <>
          <span className="grow" />
          <button className="btn primary" type="button" onClick={onClose}>
            {t('users.secret.done')}
          </button>
        </>
      }
    >
      <div className="msg warn">{t('users.secret.once')}</div>
      <dl className="kv">
        <dt>{t('users.secret.password')}</dt>
        <dd>
          <span className="mono secret">{secret.password}</span>{' '}
          <button className="btn sm" type="button" onClick={() => void copyPassword()}>
            {copy === 'done' ? t('users.secret.copied') : copy === 'failed' ? t('users.secret.copyFailed') : t('users.secret.copy')}
          </button>
        </dd>
        <dt>{t('users.secret.expires')}</dt>
        <dd>{formatDateTime(secret.expiresAt)}</dd>
      </dl>
      <p className="note">{t('users.secret.handOver')}</p>
    </Drawer>
  );
}
