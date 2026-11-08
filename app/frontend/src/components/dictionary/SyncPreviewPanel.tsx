import {useIntl} from '@/contexts/IntlContext';
import {formatNumber} from '@/lib/format';
import type {SyncPreview} from '@/types/dictionarySync';
import {Fact} from './Fact';

const duration = (seconds: number) =>
  seconds < 90 ? `${formatNumber(seconds)} sn` : `${formatNumber(Math.round(seconds / 60))} dk`;

interface Props {
  preview: SyncPreview;
  busy: boolean;
  onStart: () => void;
  onCancel: () => void;
}

/** What an update would look at and how long its model work would take, before it starts. */
export function SyncPreviewPanel({preview, busy, onStart, onCancel}: Props) {
  const {t} = useIntl();
  return (
    <section className="card" id="d-preview" aria-label={t('dictionary.preview.title')}>
      <h3>{t('dictionary.preview.title')}</h3>
      {preview.has_changes ? (
        <div className="info">
          <Fact label={t('dictionary.preview.tables')} value={formatNumber(preview.tables_needing_model)} />
          <Fact label={t('dictionary.preview.rows')} value={formatNumber(preview.rows_to_describe)} />
          <Fact label={t('dictionary.preview.codeChanged')} value={formatNumber(preview.scope.scope_code_changed ?? 0)} />
          <Fact label={t('dictionary.preview.calls')} value={formatNumber(preview.model_calls)} />
          <Fact label={t('dictionary.preview.duration')} value={duration(preview.estimated_seconds)} />
        </div>
      ) : (
        <div className="msg ok">{t('dictionary.preview.noChange')}</div>
      )}
      {preview.requires_approval && preview.has_changes ? <p className="sub2">{t('dictionary.preview.approval')}</p> : null}
      <div className="row-actions">
        <button className="btn" type="button" disabled={busy} onClick={onCancel}>
          {t('dictionary.edit.cancel')}
        </button>
        <button className="btn primary" type="button" disabled={busy || !preview.has_changes} onClick={onStart}>
          {t('dictionary.preview.start')}
        </button>
      </div>
    </section>
  );
}
