import {useEffect, useState} from 'react';
import {Drawer} from '@/components/admin/Drawer';
import {Skeleton} from '@/components/admin/Skeleton';
import {useIntl} from '@/contexts/IntlContext';
import {useToast} from '@/hooks/useToast';
import {adminErrorText} from '@/lib/adminErrors';
import {versionDigits} from '@/lib/adminStatus';
import {runFailureText, runPill} from '@/lib/dictionarySync';
import {formatDateTime, formatNumber} from '@/lib/format';
import {DictionarySyncService} from '@/services/dictionarySync';
import {
  COLUMN_EDIT_FIELDS,
  OBJECT_EDIT_FIELDS,
  type SyncCounts,
  type SyncEditField,
  type SyncRecordEdit,
  type SyncRunDetail,
  type SyncRunSummary,
} from '@/types/dictionarySync';
import {Fact} from './Fact';
import {RecordEditor} from './RecordEditor';
import {RunChanges} from './RunChanges';
import {RunSuggestions} from './RunSuggestions';
import {confirmAction} from '@/lib/confirm';
import {ScoreCard} from './ScoreCard';

/** The report's numbers, in reading order. */
const COUNTS: readonly (keyof SyncCounts)[] = [
  'tables_added',
  'tables_removed',
  'tables_changed',
  'tables_excluded',
  'tables_corrected',
  'columns_added',
  'columns_removed',
  'columns_changed',
  'columns_excluded',
  'columns_corrected',
  'fields_filled',
  'fields_normalized',
  'scope_columns',
  'scope_code_changed',
  'fields_empty',
  'model_calls',
  'model_failures',
  'warnings',
];

const version = (value: string) => (value ? versionDigits(value) : '—');

interface Props {
  runId: string;
  onClose: () => void;
  /** An action changed the run: the page's lists and states follow. */
  onChanged: (run: SyncRunSummary) => void;
}

/**
 * The update report (dictionary-sync Requirement 7, 9, 12): when, who and what came out, the
 * counts, the warnings, the failure class, the suggestions and the change lines; a run waiting
 * for approval is applied or rejected here.
 */
export function RunReport({runId, onClose, onChanged}: Props) {
  const {t} = useIntl();
  const {toast, reportUnreachable} = useToast();
  const [run, setRun] = useState<SyncRunDetail | null>(null);
  const [failure, setFailure] = useState('');
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<{tableKey: string; columnName: string; field?: SyncEditField; value?: string} | null>(null);

  useEffect(() => {
    let live = true;
    DictionarySyncService.run(runId).then(
      (answer) => {
        if (live) setRun(answer);
      },
      (error: unknown) => {
        reportUnreachable(error);
        if (live) setFailure(adminErrorText(error, t));
      },
    );
    return () => {
      live = false;
    };
  }, [runId, t, reportUnreachable]);

  async function act(request: () => Promise<SyncRunDetail>, failedTitle: string): Promise<boolean> {
    setBusy(true);
    try {
      const answer = await request();
      setRun(answer);
      onChanged(answer);
      return true;
    } catch (error) {
      reportUnreachable(error);
      toast(t(failedTitle), [adminErrorText(error, t)], true);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (await confirmAction(t('dictionary.report.approveConfirm'), {action: t('dictionary.report.approve')}))
      void act(() => DictionarySyncService.approve(runId), 'dictionary.report.actionFailed');
  }

  async function save(edit: SyncRecordEdit) {
    // A refused text stays in the editor, so the admin can correct it.
    if (await act(() => DictionarySyncService.editRecord(runId, edit), 'dictionary.edit.failed')) setEditing(null);
  }

  async function reject() {
    if (await confirmAction(t('dictionary.report.rejectConfirm'), {action: t('dictionary.report.reject'), danger: true}))
      void act(() => DictionarySyncService.reject(runId), 'dictionary.report.actionFailed');
  }

  const pending = run?.status === 'pending_approval';
  const failed = run?.status === 'failed' || run?.status === 'interrupted';
  return (
    <Drawer
      wide
      title={t('dictionary.report.title')}
      sub={run ? formatDateTime(run.started_at) : undefined}
      onClose={onClose}
      foot={
        pending ? (
          <>
            <button className="btn danger" type="button" disabled={busy} onClick={() => void reject()}>
              {t('dictionary.report.reject')}
            </button>
            <button className="btn primary" type="button" disabled={busy} onClick={() => void approve()}>
              {t('dictionary.report.approve')}
            </button>
          </>
        ) : undefined
      }
    >
      {failure ? <div className="msg bad">{failure}</div> : null}
      {!run && !failure ? <Skeleton /> : null}
      {run ? (
        <>
          <div className="info">
            <Fact
              label={t('dictionary.report.result')}
              value={<span className={runPill(run.status)}>{t(`dictionary.sync.status.${run.status}`)}</span>}
            />
            <Fact label={t('dictionary.report.kind')} value={t(`dictionary.runs.kind.${run.kind}`)} />
            <Fact label={t('dictionary.report.finished')} value={run.finished_at ? formatDateTime(run.finished_at) : '—'} />
            <Fact label={t('dictionary.report.by')} value={run.started_by?.display_name ?? '—'} />
            <Fact label={t('dictionary.report.previous')} value={version(run.previous_version)} title={run.previous_version} />
            <Fact label={t('dictionary.report.new')} value={version(run.new_version)} title={run.new_version} />
            <Fact label={t('dictionary.report.model')} value={run.model || '—'} />
          </div>
          {failed ? (
            <div className="msg bad" id="d-failure">
              <b>{runFailureText(run, t)}</b>
              {run.error_message ? <div>{run.error_message}</div> : null}
            </div>
          ) : null}
          {pending ? <div className="msg warn">{t('dictionary.report.pendingNotice')}</div> : null}
          {run.score ? (
            <ScoreCard
              score={run.score}
              editable={pending}
              onFix={(row) => setEditing({tableKey: row.table, columnName: row.column, field: 'ColumnDescription'})}
            />
          ) : null}
          {editing && pending ? (
            <RecordEditor
              key={`${editing.tableKey}.${editing.columnName}.${editing.field ?? ''}`}
              tableKey={editing.tableKey}
              columnName={editing.columnName}
              field={editing.field}
              value={editing.value}
              busy={busy}
              onSave={(edit) => void save(edit)}
              onCancel={() => setEditing(null)}
            />
          ) : null}
          <h3>{t('dictionary.report.counts')}</h3>
          <div className="info" id="d-counts">
            {COUNTS.map((name) => (
              <Fact key={name} label={t(`dictionary.report.count.${name}`)} value={formatNumber(run.counts[name] ?? 0)} />
            ))}
          </div>
          {run.warnings.length ? (
            <div className="msg warn">
              {t('dictionary.report.warnings', {count: formatNumber(run.warnings.length)})}
              <ul>
                {run.warnings.map((warning, at) => (
                  <li key={at}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <RunSuggestions
            suggestions={run.suggestions}
            busy={busy}
            onApply={(ids) => void act(() => DictionarySyncService.applySuggestions(runId, ids), 'dictionary.suggestions.failed')}
          />
          <RunChanges
            key={run.new_version}
            runId={runId}
            onEdit={
              pending
                ? (change) => {
                    // Only an editable field starts from the line's value; any other starts empty.
                    const fields: readonly string[] = change.column_name ? COLUMN_EDIT_FIELDS : OBJECT_EDIT_FIELDS;
                    const editable = fields.includes(change.field);
                    setEditing({
                      tableKey: change.table_key,
                      columnName: change.column_name,
                      field: editable ? (change.field as SyncEditField) : undefined,
                      value: editable ? change.new_value : '',
                    });
                  }
                : undefined
            }
          />
        </>
      ) : null}
    </Drawer>
  );
}
