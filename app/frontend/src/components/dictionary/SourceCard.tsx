import {useEffect, useRef, useState} from 'react';
import {Field} from '@/components/admin/Field';
import {Icon} from '@/components/admin/Icon';
import {useIntl} from '@/contexts/IntlContext';
import {useToast} from '@/hooks/useToast';
import {adminErrorText} from '@/lib/adminErrors';
import {formatDateTime, formatNumber} from '@/lib/format';
import {DictionarySyncService} from '@/services/dictionarySync';
import type {DictionarySource, DictionarySourceInput, DictionarySourceTest} from '@/types/dictionarySync';

const DEFAULT_DATABASE = 'EDWUTIL';
const DEFAULT_PORT = 1433;

type Tested = {state: 'idle' | 'busy'} | {state: 'done'; answer: DictionarySourceTest} | {state: 'bad'; message: string};

interface Props {
  source: DictionarySource;
  /** Grows each time the page sends the person here; the host field takes the focus. */
  focusRequest: number;
  onSaved: (source: DictionarySource) => void;
}

/**
 * The source connection (dictionary-sync Requirement 1; plan.md): SQL Server host, port, database,
 * user, password and encryption. The password is only ever sent: an empty field keeps the saved
 * one, and it leaves this form once it is saved.
 */
export function SourceCard({source, focusRequest, onSaved}: Props) {
  const {t} = useIntl();
  const {toast, reportUnreachable} = useToast();
  const [host, setHost] = useState(source.host);
  const [port, setPort] = useState(String(source.port || DEFAULT_PORT));
  const [database, setDatabase] = useState(source.database || DEFAULT_DATABASE);
  const [username, setUsername] = useState(source.username);
  const [password, setPassword] = useState('');
  const [encrypt, setEncrypt] = useState(source.configured ? source.encrypt : true);
  const [saving, setSaving] = useState(false);
  const [tested, setTested] = useState<Tested>({state: 'idle'});
  const hostField = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (focusRequest) hostField.current?.focus();
  }, [focusRequest]);

  const portNumber = Number(port);
  const complete =
    Boolean(host.trim() && database.trim() && username.trim()) &&
    Number.isInteger(portNumber) &&
    portNumber >= 1 &&
    portNumber <= 65535;

  /** An edit makes the last test's answer one about another connection. */
  const edited =
    <T,>(set: (value: T) => void) =>
    (value: T) => {
      set(value);
      setTested({state: 'idle'});
    };

  function input(): DictionarySourceInput {
    const body: DictionarySourceInput = {
      host: host.trim(),
      port: portNumber,
      database: database.trim(),
      username: username.trim(),
      encrypt,
    };
    if (password) body.password = password;
    return body;
  }

  async function save() {
    setSaving(true);
    try {
      const saved = await DictionarySyncService.saveSource(input());
      setPassword('');
      onSaved(saved);
      toast(t('dictionary.source.saved'));
    } catch (error) {
      reportUnreachable(error);
      toast(t('dictionary.source.saveFailed'), [adminErrorText(error, t)], true);
    } finally {
      setSaving(false);
    }
  }

  async function test() {
    setTested({state: 'busy'});
    try {
      setTested({state: 'done', answer: await DictionarySyncService.testSource(input())});
    } catch (error) {
      reportUnreachable(error);
      setTested({state: 'bad', message: adminErrorText(error, t)});
    }
  }

  const passwordHint = source.has_password ? t('dictionary.source.passwordKept') : undefined;
  const missing = tested.state === 'done' ? (tested.answer.missing_databases ?? []) : [];
  return (
    <section className="card" id="d-source">
      <h2>{t('dictionary.source.title')}</h2>
      <p className="intro">{t('dictionary.source.intro')}</p>
      <div className="form">
        <Field id="ds-host" label={t('dictionary.source.host')}>
          <input
            id="ds-host"
            ref={hostField}
            type="text"
            className="mono"
            autoComplete="off"
            spellCheck={false}
            value={host}
            onChange={(event) => edited(setHost)(event.target.value)}
          />
        </Field>
        <Field id="ds-port" label={t('dictionary.source.port')}>
          <input
            id="ds-port"
            type="number"
            min={1}
            max={65535}
            value={port}
            onChange={(event) => edited(setPort)(event.target.value)}
          />
        </Field>
        <Field id="ds-database" label={t('dictionary.source.database')}>
          <input
            id="ds-database"
            type="text"
            className="mono"
            autoComplete="off"
            spellCheck={false}
            value={database}
            onChange={(event) => edited(setDatabase)(event.target.value)}
          />
        </Field>
        <Field id="ds-username" label={t('dictionary.source.username')}>
          <input
            id="ds-username"
            type="text"
            className="mono"
            autoComplete="off"
            spellCheck={false}
            value={username}
            onChange={(event) => edited(setUsername)(event.target.value)}
          />
        </Field>
        <Field id="ds-password" label={t('dictionary.source.password')} hint={passwordHint}>
          <input
            id="ds-password"
            type="password"
            className="mono"
            autoComplete="new-password"
            aria-describedby={passwordHint ? 'ds-password-hint' : undefined}
            value={password}
            onChange={(event) => edited(setPassword)(event.target.value)}
          />
        </Field>
        <label className="check">
          <input type="checkbox" checked={encrypt} onChange={(event) => edited(setEncrypt)(event.target.checked)} />
          {t('dictionary.source.encrypt')}
        </label>
        <div className="info">
          <button className="btn primary" type="button" disabled={!complete || saving} onClick={() => void save()}>
            {t('dictionary.source.save')}
          </button>
          <button className="btn" type="button" disabled={!complete || tested.state === 'busy'} onClick={() => void test()}>
            <Icon name="bolt" />
            {tested.state === 'busy' ? t('dictionary.source.testing') : t('dictionary.source.test')}
          </button>
          {source.updated_at ? (
            <span className="note">{t('dictionary.source.updatedAt', {when: formatDateTime(source.updated_at)})}</span>
          ) : null}
        </div>
      </div>
      {tested.state === 'bad' ? <div className="msg bad">{tested.message}</div> : null}
      {tested.state === 'done' ? (
        tested.answer.ok ? (
          <div className="msg ok">
            {t('dictionary.source.testOk', {
              tables: formatNumber(tested.answer.table_count),
              columns: formatNumber(tested.answer.column_count),
            })}
            {tested.answer.last_change_at
              ? ' ' + t('dictionary.source.testLastChange', {when: formatDateTime(tested.answer.last_change_at)})
              : ''}
          </div>
        ) : (
          <div className="msg bad">{tested.answer.message}</div>
        )
      ) : null}
      {missing.length ? <div className="msg warn">{t('dictionary.source.missingDatabases', {names: missing.join(', ')})}</div> : null}
    </section>
  );
}
