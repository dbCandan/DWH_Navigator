import {useState, type ReactNode} from 'react';
import {useNavigate, useParams} from 'react-router';
import {Icon} from '@/components/admin/Icon';
import {adminPath, dictionaryTablePath} from '@/components/admin/nav';
import {PageHead} from '@/components/admin/PageHead';
import {Skeleton} from '@/components/admin/Skeleton';
import {TableDrawer} from '@/components/dictionary/TableDrawer';
import {TableList} from '@/components/dictionary/TableList';
import {useIntl} from '@/contexts/IntlContext';
import {pickDictionaryWorkbook, useDownload, useIndexRebuild} from '@/hooks/useAdminActions';
import {useDictionaryState} from '@/hooks/useDictionaryState';
import {adminErrorText} from '@/lib/adminErrors';
import {dictionaryStatus, versionDigits} from '@/lib/adminStatus';
import {formatDateTime, formatNumber} from '@/lib/format';
import {DictionaryService} from '@/services/dictionary';

function Fact({label, value, title}: {label: string; value: ReactNode; title?: string}) {
  return (
    <div className="it" title={title ?? ''}>
      <div className="k">{label}</div>
      <div className="v">{value}</div>
    </div>
  );
}

/**
 * The "Sözlük" page (dictionary-management Requirement 13-15; admin.html PAGES.sozluk): import,
 * export and the empty template; before the first import the drop area and the template card;
 * after it the version's facts, the index state and the table list. `/admin/sozluk/<key>` opens
 * the table's drawer.
 */
export default function DictionaryPage() {
  const {t} = useIntl();
  const navigate = useNavigate();
  const tableKey = useParams()['*'] ?? '';
  const {dictionary, tables, failure} = useDictionaryState();
  const download = useDownload();
  const rebuild = useIndexRebuild();
  const [rebuilding, setRebuilding] = useState(false);
  const label = t('admin.page.sozluk.label');
  const status = dictionaryStatus(dictionary);
  const active = status.active;

  async function runRebuild() {
    setRebuilding(true);
    try {
      await rebuild();
    } finally {
      setRebuilding(false);
    }
  }

  // The drawer keeps its place while the page loads, so a deep link's drawer is not opened twice.
  const page = (body: ReactNode) => (
    <section className="page on" id="p-sozluk" aria-label={label}>
      <>{body}</>
      {tableKey ? <TableDrawer tableKey={tableKey} onClose={() => navigate(adminPath('sozluk'))} /> : null}
    </section>
  );
  if (dictionary === null || (active && tables === null))
    return page(
      <>
        <PageHead title={label} />
        {failure ? <div className="msg bad">{t('admin.pageFailed', {reason: adminErrorText(failure, t)})}</div> : <Skeleton />}
      </>,
    );

  const head = (
    <PageHead
      title={label}
      description={t('admin.page.sozluk.description')}
      actions={
        <>
          <button className="btn primary" type="button" onClick={pickDictionaryWorkbook}>
            <Icon name="import" />
            {t('dictionary.import.button')}
          </button>
          {active ? (
            <button className="btn" type="button" onClick={() => void download(DictionaryService.exportWorkbook)}>
              <Icon name="export" />
              {t('dictionary.export.button')}
            </button>
          ) : null}
          <button className="btn ghost" type="button" onClick={() => void download(DictionaryService.template)}>
            <Icon name="file" />
            {t('dictionary.template.button')}
          </button>
        </>
      }
    />
  );

  if (!active)
    return page(
      <>
        {head}
        <section className="card">
          <div
            className="dz"
            role="button"
            tabIndex={0}
            onClick={pickDictionaryWorkbook}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                pickDictionaryWorkbook();
              }
            }}
          >
            <Icon name="import" />
            <b>{t('dictionary.empty.title')}</b>
            <div className="muted">{t('dictionary.empty.body')}</div>
          </div>
        </section>
        <section className="card">
          <h2>{t('dictionary.templateCard.title')}</h2>
          <p className="intro">
            {t('dictionary.templateCard.before')}
            <b>{t('dictionary.templateCard.objects')}</b>
            {t('dictionary.templateCard.objectsFields')}
            <b>{t('dictionary.templateCard.columns')}</b>
            {t('dictionary.templateCard.columnsFields')}
          </p>
          <button className="btn" type="button" onClick={() => void download(DictionaryService.template)}>
            <Icon name="file" />
            {t('dictionary.templateCard.download')}
          </button>
        </section>
      </>,
    );

  return page(
    <>
      {head}
      <section className="card">
        <div className="info">
          <Fact label={t('dictionary.info.tables')} value={formatNumber(active.object_count)} />
          <Fact label={t('dictionary.info.columns')} value={formatNumber(active.column_count)} />
          <Fact label={t('dictionary.info.source')} value={active.source_name} />
          <Fact label={t('dictionary.info.imported')} value={formatDateTime(active.imported_at)} />
          <Fact label={t('dictionary.info.version')} value={versionDigits(active.version)} title={active.version} />
          <div className="grow" />
          {status.state === 'ok' ? (
            <span className="pill ok">{t('dictionary.info.indexOk')}</span>
          ) : (
            <button className="btn sm primary" type="button" disabled={rebuilding} onClick={() => void runRebuild()}>
              {rebuilding ? (
                t('maintenance.index.rebuilding')
              ) : (
                <>
                  <Icon name="refresh" />
                  {t('dictionary.info.buildIndex')}
                </>
              )}
            </button>
          )}
        </div>
        {active.warning_count ? <div className="msg warn">{t('dictionary.info.warnings', {count: active.warning_count})}</div> : null}
      </section>
      <TableList tables={tables ?? []} onOpen={(key) => navigate(dictionaryTablePath(key))} />
    </>,
  );
}
