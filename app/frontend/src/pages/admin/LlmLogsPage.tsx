import {useEffect, useState} from 'react';
import {Drawer} from '@/components/admin/Drawer';
import {Icon} from '@/components/admin/Icon';
import {PageHead} from '@/components/admin/PageHead';
import {Skeleton} from '@/components/admin/Skeleton';
import {useIntl} from '@/contexts/IntlContext';
import {useToast} from '@/hooks/useToast';
import {adminErrorText} from '@/lib/adminErrors';
import {formatDateTime, formatDuration, formatNumber, formatWhen} from '@/lib/format';
import {prettyJson, replyText, requestMessages} from '@/lib/llmCallBody';
import {LlmCallLogService} from '@/services/llmCallLogs';
import type {LlmCallDetail, LlmCallExchange, LlmCallPage, LlmCallPurpose} from '@/types/llmCallLogs';
import './llmLogs.css';

const LIVE_MS = 5000;
const TYPING_MS = 300;
const PAGE_SIZE = 50;
const MAX_ROWS = 500;
const PURPOSES: readonly LlmCallPurpose[] = ['analysis', 'dictionary_sync', 'connection_test', 'evaluation'];

function Exchange({exchange, index, count}: {exchange: LlmCallExchange; index: number; count: number}) {
  const {t} = useIntl();
  const messages = requestMessages(exchange.request);
  const reply = replyText(exchange.response);
  return (
    <section className="llm-exchange">
      {count > 1 ? (
        <h3>{t('llmLogs.detail.attempt', {index: index + 1, count})}</h3>
      ) : null}
      <h4>{t('llmLogs.detail.request')}</h4>
      {exchange.request_truncated ? <p className="note">{t('llmLogs.detail.truncated')}</p> : null}
      {messages.map((message, at) => (
        <div className="llm-message" key={at}>
          <span className="pill">{message.role}</span>
          <pre>{message.content}</pre>
        </div>
      ))}
      <details>
        <summary>{t('llmLogs.detail.rawRequest')}</summary>
        <pre>{prettyJson(exchange.request)}</pre>
      </details>
      <h4>
        {t('llmLogs.detail.response')}
        <span className="note">
          {exchange.status === null
            ? t('llmLogs.detail.noResponse')
            : `HTTP ${exchange.status} · ${formatDuration(exchange.duration_ms, t)}`}
        </span>
      </h4>
      {exchange.response_truncated ? <p className="note">{t('llmLogs.detail.truncated')}</p> : null}
      {reply !== null ? <pre>{reply}</pre> : null}
      {exchange.response ? (
        <details open={reply === null}>
          <summary>{t('llmLogs.detail.rawResponse')}</summary>
          <pre>{prettyJson(exchange.response)}</pre>
        </details>
      ) : null}
    </section>
  );
}

/** The "LLM kayıtları" page: chat calls newest first; a row opens what was sent and what came back. */
export default function LlmLogsPage() {
  const {t} = useIntl();
  const {reportUnreachable} = useToast();
  const [purpose, setPurpose] = useState('');
  const [outcome, setOutcome] = useState('');
  const [text, setText] = useState('');
  const [q, setQ] = useState('');
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [live, setLive] = useState(true);
  const [page, setPage] = useState<LlmCallPage | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [openId, setOpenId] = useState('');
  const [detail, setDetail] = useState<LlmCallDetail | null>(null);
  const [detailFailure, setDetailFailure] = useState<unknown>(null);
  /** Every step reads the list again: the live refresh and "Yenile". */
  const [reads, setReads] = useState(0);
  const label = t('admin.page.llm-kayitlari.label');

  useEffect(() => {
    let current = true;
    LlmCallLogService.list({purpose, outcome, q, limit}).then(
      (answer) => {
        if (!current) return;
        setPage(answer);
        setFailure(null);
      },
      (error: unknown) => {
        if (!current) return;
        reportUnreachable(error);
        setFailure(error);
      },
    );
    return () => {
      current = false;
    };
  }, [purpose, outcome, q, limit, reads, reportUnreachable]);

  useEffect(() => {
    const timer = window.setTimeout(() => setQ(text.trim()), TYPING_MS);
    return () => window.clearTimeout(timer);
  }, [text]);

  // Live: while the switch is on, the tab is visible and no call is open.
  useEffect(() => {
    if (!live || openId) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) setReads((count) => count + 1);
    }, LIVE_MS);
    return () => window.clearInterval(timer);
  }, [live, openId]);

  useEffect(() => {
    if (!openId) return;
    let current = true;
    LlmCallLogService.read(openId).then(
      (answer) => {
        if (current) setDetail(answer);
      },
      (error: unknown) => {
        if (!current) return;
        reportUnreachable(error);
        setDetailFailure(error);
      },
    );
    return () => {
      current = false;
    };
  }, [openId, reportUnreachable]);

  const listBox = (() => {
    if (failure) return <div className="msg bad">{t('llmLogs.failed', {reason: adminErrorText(failure, t)})}</div>;
    if (!page) return <Skeleton />;
    if (!page.rows.length) {
      const filtered = Boolean(purpose || outcome || q);
      return <p className="empty">{t(filtered ? 'llmLogs.empty.filter' : 'llmLogs.empty.none')}</p>;
    }
    return (
      <>
        <table className="t">
          <thead>
            <tr>
              <th>{t('llmLogs.col.when')}</th>
              <th>{t('llmLogs.col.purpose')}</th>
              <th>{t('llmLogs.col.model')}</th>
              <th>{t('llmLogs.col.outcome')}</th>
              <th className="r">{t('llmLogs.col.tokens')}</th>
              <th className="r">{t('llmLogs.col.duration')}</th>
            </tr>
          </thead>
          <tbody>
            {page.rows.map((row) => {
              const open = () => {
                setDetail(null);
                setDetailFailure(null);
                setOpenId(row.public_id);
              };
              return (
                <tr
                  key={row.public_id}
                  className={'click' + (openId === row.public_id ? ' sel' : '')}
                  tabIndex={0}
                  onClick={open}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      open();
                    }
                  }}
                >
                  <td className="when" title={formatDateTime(row.started_at)}>
                    {formatWhen(row.started_at, t)}
                  </td>
                  <td>{t(`llmLogs.purpose.${row.purpose}`)}</td>
                  <td className="mono">{row.model}</td>
                  <td>
                    <span className={'pill ' + (row.outcome === 'ok' ? 'ok' : 'bad')}>{row.outcome}</span>
                    {row.requests > 1 ? (
                      <span className="note"> {t('llmLogs.requests', {count: row.requests})}</span>
                    ) : null}
                  </td>
                  <td className="r">
                    {formatNumber(row.prompt_tokens)} / {formatNumber(row.completion_tokens)}
                  </td>
                  <td className="dur">{formatDuration(row.duration_ms, t)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {page.rows.length < page.total && limit < MAX_ROWS ? (
          <div className="more">
            <button className="btn" type="button" onClick={() => setLimit(Math.min(limit + PAGE_SIZE, MAX_ROWS))}>
              {t('llmLogs.more', {count: formatNumber(page.total - page.rows.length)})}
            </button>
          </div>
        ) : null}
      </>
    );
  })();

  return (
    <section className="page on" id="p-llm-kayitlari" aria-label={label}>
      <PageHead
        title={label}
        description={t('admin.page.llm-kayitlari.description')}
        actions={
          <button className="btn" type="button" onClick={() => setReads((count) => count + 1)}>
            <Icon name="refresh" />
            {t('llmLogs.refresh')}
          </button>
        }
      />
      <div className="toolbar">
        <select aria-label={t('llmLogs.purposeFilter')} value={purpose} onChange={(event) => setPurpose(event.target.value)}>
          <option value="">{t('llmLogs.purposeAll')}</option>
          {PURPOSES.map((value) => (
            <option value={value} key={value}>
              {t(`llmLogs.purpose.${value}`)}
            </option>
          ))}
        </select>
        <select aria-label={t('llmLogs.outcomeFilter')} value={outcome} onChange={(event) => setOutcome(event.target.value)}>
          <option value="">{t('llmLogs.outcomeAll')}</option>
          <option value="ok">ok</option>
          <option value="timeout">timeout</option>
          <option value="invalid_json">invalid_json</option>
          <option value="output_truncated">output_truncated</option>
          <option value="upstream_status">upstream_status</option>
          <option value="cancelled">cancelled</option>
        </select>
        <input
          type="search"
          placeholder={t('llmLogs.search')}
          aria-label={t('llmLogs.search')}
          maxLength={200}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <label className="live">
          <span className="switch">
            <input type="checkbox" checked={live} onChange={(event) => setLive(event.target.checked)} />
            <span />
          </span>
          {t('llmLogs.live')}
        </label>
      </div>
      {page?.retention_days === 0 ? <div className="msg warn">{t('llmLogs.off')}</div> : null}
      <section className="card grow">
        <div className="card-h">
          <h2>
            {page
              ? t('llmLogs.title', {count: formatNumber(page.total), days: page.retention_days})
              : label}
          </h2>
        </div>
        <div className="list-box">{listBox}</div>
      </section>
      {openId ? (
        <Drawer
          wide
          title={detail ? `${t(`llmLogs.purpose.${detail.purpose}`)} · ${detail.model}` : t('llmLogs.detail.title')}
          sub={
            detail
              ? t('llmLogs.detail.sub', {
                  at: formatDateTime(detail.started_at),
                  outcome: detail.outcome,
                  duration: formatDuration(detail.duration_ms, t),
                  wait: formatDuration(detail.wait_ms, t),
                })
              : undefined
          }
          onClose={() => setOpenId('')}
        >
          {detailFailure ? (
            <div className="msg bad">{t('llmLogs.failed', {reason: adminErrorText(detailFailure, t)})}</div>
          ) : !detail ? (
            <Skeleton />
          ) : detail.exchanges.length === 0 ? (
            <p className="empty">{t('llmLogs.detail.nothingSent')}</p>
          ) : (
            detail.exchanges.map((exchange, index) => (
              <Exchange exchange={exchange} index={index} count={detail.exchanges.length} key={index} />
            ))
          )}
        </Drawer>
      ) : null}
    </section>
  );
}
