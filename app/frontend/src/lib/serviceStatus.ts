import {formatNumber} from '@/lib/format';
import type {ServiceStatus} from '@/types/analysis';

type Translate = (key: string, values?: Record<string, string | number>) => string;

/** What the main screen's status pill and the warning under the question bar show. */
export interface StatusView {
  /** "" (ready), "warn" or "bad". */
  tone: '' | 'warn' | 'bad';
  label: string;
  /** The pill's two-line tooltip. */
  tip: string;
  /** The line under the question bar; "" hides it. */
  warn: string;
}

/**
 * The status pill's states in their priority (dictionary-explorer Requirement 2): no dictionary,
 * no chat model, model unreachable, ready. The reason never carries the model server's address.
 */
export function statusView(status: ServiceStatus, t: Translate): StatusView {
  const m = status.llm_state;
  const tip = [
    t('explorer.status.tipDictionary', {columns: formatNumber(status.columns), tables: formatNumber(status.objects)}),
    m.state === 'ok'
      ? t('explorer.status.tipAnalyst', {model: m.model})
      : t('explorer.status.tipModel', {reason: m.reason || t('explorer.status.tipNotConnected')}),
  ].join('\n');
  if (!status.objects)
    return {tone: 'warn', label: t('explorer.status.noDictionary'), tip, warn: t('explorer.warn.noDictionary')};
  if (m.state === 'ok') return {tone: '', label: t('explorer.status.ready'), tip, warn: ''};
  if (m.state === 'down')
    return {
      tone: 'bad',
      label: t('explorer.status.modelDown'),
      tip,
      warn: t('explorer.warn.modelDown', {reason: m.reason.replace(/\.?$/, '.')}),
    };
  return {tone: 'warn', label: t('explorer.status.modelNone'), tip, warn: t('explorer.warn.modelNone')};
}
