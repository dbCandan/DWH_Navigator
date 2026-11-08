import {useEffect, useState, type FormEvent} from 'react';
import {Drawer} from '@/components/admin/Drawer';
import {Field} from '@/components/admin/Field';
import {Icon} from '@/components/admin/Icon';
import {PageHero} from '@/components/admin/PageHero';
import {useToast} from '@/hooks/useToast';
import {useAuth} from '@/contexts/AuthContext';
import {useIntl} from '@/contexts/IntlContext';
import {APPLICATION_ROLES, ROLE_MANAGER, ROLE_USER} from '@/lib/access';
import {ApiError} from '@/lib/apiClient';
import {formatDateTime, formatNumber, formatWhen} from '@/lib/format';
import {UserAdminService} from '@/services/userAdmin';
import type {ApplicationRole, UserPage, UserSummary} from '@/types/auth';
import './users.css';
import {confirmAction} from '@/lib/confirm';

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

/** Up to two letters for the avatar: the first of the first two words. */
function initials(name: string): string {
  const words = name.trim().split(/[\s._-]+/).filter(Boolean);
  return words.slice(0, 2).map((word) => word[0]!.toLocaleUpperCase('tr-TR')).join('') || '?';
}

/** One of five avatar colours, steady for a user name. */
function toneOf(username: string): number {
  let sum = 0;
  for (const char of username) sum = (sum * 31 + char.charCodeAt(0)) % 9973;
  return sum % 5;
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
  const [show, setShow] = useState<'all' | 'active' | 'inactive'>('all');

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

  async function changeRole(target: UserSummary, role: ApplicationRole) {
    if (role === target.role) return;
    const roleName = t(roleKey(role));
    if (!(await confirmAction(t('users.confirm.role', {username: target.username, role: roleName}), {action: t('users.confirm.roleAction')}))) {
      setReload((n) => n + 1); // put the select back
      return;
    }
    void act(target, async () => {
      await UserAdminService.setRole(target, role);
      return t('users.done.role', {username: target.username, role: roleName});
    });
  }

  async function changeActive(target: UserSummary, active: boolean) {
    if (
      !active &&
      !(await confirmAction(t('users.confirm.deactivate', {username: target.username}), {
        action: t('users.confirm.deactivateAction'),
        danger: true,
      }))
    )
      return;
    void act(target, async () => {
      await UserAdminService.setActive(target, active);
      return t(active ? 'users.done.activated' : 'users.done.deactivated', {username: target.username});
    });
  }

  async function resetPassword(target: UserSummary) {
    if (!(await confirmAction(t('users.confirm.reset', {username: target.username}), {action: t('users.reset'), danger: true}))) return;
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
  const items = data?.items ?? [];
  // The status chips and the counts read the loaded accounts; with more pages they say so.
  const whole = data !== null && items.length >= data.total;
  const counts = {
    active: items.filter((item) => item.active).length,
    inactive: items.filter((item) => !item.active).length,
    waiting: items.filter((item) => item.password_change_required).length,
  };
  const shown = items.filter((item) => show === 'all' || (show === 'active' ? item.active : !item.active));
  const label = t('admin.page.kullanicilar.label');
  return (
    <section className="page on" id="p-kullanicilar" aria-label={label}>
      <PageHero
        icon="users"
        title={label}
        description={t('admin.page.kullanicilar.description')}
        actions={
          <button className="btn primary" type="button" onClick={() => setAdding(true)}>
            <Icon name="plus" />
            {t('users.add')}
          </button>
        }
        stats={
          data
            ? [
                {label: t('users.stat.total'), value: formatNumber(data.total)},
                {label: t('users.stat.active'), value: formatNumber(counts.active), tone: 'ok', note: whole ? undefined : t('users.stat.thisPage')},
                {label: t('users.stat.inactive'), value: formatNumber(counts.inactive), note: whole ? undefined : t('users.stat.thisPage')},
                {
                  label: t('users.stat.waiting'),
                  value: formatNumber(counts.waiting),
                  tone: counts.waiting ? 'warn' : undefined,
                  note: t('users.stat.waitingNote'),
                },
              ]
            : undefined
        }
      />
      <div className="toolbar people-tools">
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
        {data && whole && data.total > 1 ? (
          <div className="fchips" role="group" aria-label={t('users.filter.label')}>
            {(['all', 'active', 'inactive'] as const).map((value) => (
              <button className="fchip" type="button" key={value} aria-pressed={show === value} onClick={() => setShow(value)}>
                {t(`users.filter.${value}`)}
                <i>{formatNumber(value === 'all' ? items.length : counts[value])}</i>
              </button>
            ))}
          </div>
        ) : null}
        {data && <span className="note">{t('users.count', {count: formatNumber(data.total)})}</span>}
      </div>
      <div className="fill scroll people-body">
        {listing.state === 'loading' && (
          <div role="status" aria-label={t('users.loading')}>
            <div className="skel" />
            <div className="skel" />
            <div className="skel" />
          </div>
        )}
        {listing.state === 'error' && <div className="msg bad">{listing.message}</div>}
        {data && shown.length === 0 && <p className="empty">{t('users.empty')}</p>}
        {shown.length > 0 && (
          <ul className="people" aria-label={t('users.listLabel')}>
            {shown.map((item) => {
              const protectedAccount = item.role === 'super_admin';
              const own = item.public_id === current?.public_id;
              const working = busy === item.public_id;
              return (
                <li key={item.public_id} className={'person' + (item.active ? '' : ' off') + (working ? ' busy' : '')}>
                  <span className={'avatar a' + toneOf(item.username)} aria-hidden="true">
                    {initials(item.display_name || item.username)}
                  </span>
                  <div className="person-who">
                    <b>
                      {item.display_name}
                      {own ? <span className="tag me">{t('users.you')}</span> : null}
                    </b>
                    <span className="nm">@{item.username}</span>
                  </div>
                  <div className="role-cell">
                    {protectedAccount ? (
                      <span className="role-badge">{t('users.role.superAdmin')}</span>
                    ) : (
                      <select
                        className="role-select"
                        aria-label={t('users.roleOf', {username: item.username})}
                        value={item.role ?? ''}
                        disabled={working}
                        onChange={(event) => void changeRole(item, event.target.value as ApplicationRole)}
                      >
                        {APPLICATION_ROLES.map((role) => (
                          <option key={role} value={role}>
                            {t(roleKey(role))}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                  <div className="state">
                    <span className={'pill' + (item.active ? ' ok' : '')}>
                      {t(item.active ? 'users.status.active' : 'users.status.inactive')}
                    </span>
                    {item.password_change_required && (
                      <span className="tag warn" title={t('users.status.newPasswordTip')}>
                        {t('users.status.newPassword')}
                      </span>
                    )}
                  </div>
                  <div className="when" title={item.last_login_at ? formatDateTime(item.last_login_at) : undefined}>
                    <Icon name="clock" />
                    {item.last_login_at ? formatWhen(item.last_login_at, t) : t('users.neverLong')}
                  </div>
                  <div className="acts-row">
                    {!protectedAccount && (
                      <>
                        <button className="btn sm" type="button" disabled={working} onClick={() => void resetPassword(item)}>
                          <Icon name="key" />
                          {t('users.reset')}
                        </button>
                        {!own && (
                          <button
                            className={'btn sm' + (item.active ? ' ghost danger' : '')}
                            type="button"
                            disabled={working}
                            onClick={() => void changeActive(item, !item.active)}
                          >
                            {t(item.active ? 'users.deactivate' : 'users.activate')}
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
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
        {data && data.total < 4 && !query.trim() ? (
          <section className="panel people-guide" aria-labelledby="people-guide-title">
            <div className="panel-h">
              <h2 id="people-guide-title">{t('users.guide.title')}</h2>
            </div>
            <ol className="panel-b">
              <li>
                <span className="n">1</span>
                <div>
                  <b>{t('users.guide.addTitle')}</b>
                  <p>{t('users.guide.add')}</p>
                </div>
              </li>
              <li>
                <span className="n">2</span>
                <div>
                  <b>{t('users.guide.firstTitle')}</b>
                  <p>{t('users.guide.first')}</p>
                </div>
              </li>
              <li>
                <span className="n">3</span>
                <div>
                  <b>{t('users.guide.rolesTitle')}</b>
                  <p>{t('users.guide.roles')}</p>
                </div>
              </li>
            </ol>
          </section>
        ) : null}
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
