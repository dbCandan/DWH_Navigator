import {useEffect, useState} from 'react';
import {useSearchParams} from 'react-router';
import {Icon} from '@/components/admin/Icon';
import {PageHero} from '@/components/admin/PageHero';
import {Skeleton} from '@/components/admin/Skeleton';
import {ListActions, PendingBar} from '@/components/vocabulary/ListActions';
import {StopwordCard} from '@/components/vocabulary/StopwordCard';
import {TermCard} from '@/components/vocabulary/TermCard';
import {TermDrawer} from '@/components/vocabulary/TermDrawer';
import {useIntl} from '@/contexts/IntlContext';
import {useAdminRefresh, useDownload} from '@/hooks/useAdminActions';
import {useToast} from '@/hooks/useToast';
import {useVocabularyDraft} from '@/hooks/useVocabularyDraft';
import {adminErrorText} from '@/lib/adminErrors';
import {isWorkbookName} from '@/lib/excelUpload';
import {formatDuration, formatNumber} from '@/lib/format';
import {VocabularyService} from '@/services/vocabulary';
import type {StopwordItem, TermItem, VocabularyListName, VocabularyListSaved} from '@/types/vocabulary';
import {confirmAction} from '@/lib/confirm';
import './vocabulary.css';

/**
 * The "Kelimeler" page (vocabulary-management Requirement 10-13): the lists' numbers in the
 * hero, then one list at a time under its tab (`?liste=durak` for the stopwords), each with its
 * own Excel actions. Edits gather per list and are written with one press, the index rebuilt with
 * them; the saved lists are read again only when no edit waits.
 */
/** The hero's numbers over the lists as edited. */
function vocabularyStats(terms: readonly TermItem[], stopwords: readonly StopwordItem[]) {
  return {
    terms: terms.length,
    equivalents: terms.reduce((sum, item) => sum + item.equivalents.length, 0),
    domains: new Set(terms.map((item) => item.domain).filter(Boolean)).size,
    stopwords: stopwords.length,
    groups: new Set(stopwords.map((item) => item.group)).size,
  };
}

export default function VocabularyPage() {
  const {t} = useIntl();
  const {toast, hold, reportUnreachable} = useToast();
  const {saved, draft, dirty, adoptBoth, adoptOne, edit, revert} = useVocabularyDraft();
  const refresh = useAdminRefresh();
  const download = useDownload();
  const [failure, setFailure] = useState<unknown>(null);
  const [editing, setEditing] = useState<{at: number; opened: number} | null>(null);
  const label = t('admin.page.kelimeler.label');
  const [params, setParams] = useSearchParams();
  const tab: VocabularyListName = params.get('liste') === 'durak' ? 'stopwords' : 'terms';
  const showTab = (list: VocabularyListName) => setParams(list === 'stopwords' ? {liste: 'durak'} : {}, {replace: true});
  // The saved lists are read when the page opens, unless an edit is waiting (admin.html Words.show).
  const [readOnOpen] = useState(() => !(saved && (dirty('terms') || dirty('stopwords'))));

  useEffect(() => {
    if (!readOnOpen) return;
    let live = true;
    Promise.all([VocabularyService.read('terms'), VocabularyService.read('stopwords')]).then(
      ([terms, stopwords]) => {
        if (live) adoptBoth(terms, stopwords);
      },
      (error: unknown) => {
        reportUnreachable(error);
        if (live) setFailure(error);
      },
    );
    return () => {
      live = false;
    };
  }, [readOnOpen, adoptBoth, reportUnreachable]);

  const listName = (list: VocabularyListName) => t(list === 'terms' ? 'vocabulary.list.terms' : 'vocabulary.list.stopwords');

  /** A list written on the server: the other list keeps its own edits. */
  function landed(list: VocabularyListName, answer: VocabularyListSaved, imported: boolean) {
    adoptOne(answer);
    const count = formatNumber(answer.items.length);
    toast(t(imported ? 'vocabulary.landed.imported' : 'vocabulary.landed.saved', {list: listName(list)}), [
      answer.changed
        ? t('vocabulary.landed.rebuilt', {count, duration: formatDuration(answer.elapsed_ms, t)})
        : t('vocabulary.landed.unchanged', {count}),
    ]);
    void refresh();
  }

  async function save(list: VocabularyListName) {
    try {
      const answer = list === 'terms' ? await VocabularyService.save('terms', draft.terms) : await VocabularyService.save('stopwords', draft.stopwords);
      landed(list, answer, false);
    } catch (error) {
      reportUnreachable(error);
      toast(t('vocabulary.saveFailed'), [adminErrorText(error, t)], true);
    }
  }

  async function importFile(list: VocabularyListName, file: File) {
    if (!isWorkbookName(file.name)) {
      toast(t('admin.excel.notExcel'), [file.name], true);
      return;
    }
    const question = t(`vocabulary.import.confirm.${list}${dirty(list) ? 'Dropped' : ''}`, {name: file.name});
    if (!(await confirmAction(question, {action: t('vocabulary.import.confirmAction'), danger: true}))) return;
    const dismiss = hold(t('vocabulary.import.running'), [t('vocabulary.import.runningLine', {name: file.name})]);
    try {
      const answer = await VocabularyService.importWorkbook(list, file);
      dismiss();
      landed(list, answer, true);
    } catch (error) {
      dismiss();
      reportUnreachable(error);
      toast(t('vocabulary.import.failed'), [adminErrorText(error, t)], true);
    }
  }

  const pending = (list: VocabularyListName) =>
    dirty(list) ? <PendingBar onRevert={() => revert(list)} onSave={() => save(list)} /> : null;

  if (!saved)
    return (
      <section className="page on" id="p-kelimeler" aria-label={label}>
        <PageHero icon="list" title={label} />
        {failure ? <div className="msg bad">{t('admin.pageFailed', {reason: adminErrorText(failure, t)})}</div> : <Skeleton />}
      </section>
    );

  function applyTerm(at: number, item: TermItem) {
    const terms = [...draft.terms];
    if (at >= 0) terms[at] = item;
    else terms.unshift(item);
    edit('terms', terms);
    setEditing(null);
  }

  const stats = vocabularyStats(draft.terms, draft.stopwords);
  const tabs: {list: VocabularyListName; count: number}[] = [
    {list: 'terms', count: draft.terms.length},
    {list: 'stopwords', count: draft.stopwords.length},
  ];
  return (
    <section className="page on" id="p-kelimeler" aria-label={label}>
      <PageHero
        icon="list"
        title={label}
        description={t('admin.page.kelimeler.description')}
        actions={
          <>
            <ListActions
              onImport={(file) => void importFile(tab, file)}
              onExport={() => void download(() => VocabularyService.exportWorkbook(tab))}
            />
            {tab === 'terms' ? (
              <button className="btn primary" type="button" onClick={() => setEditing({at: -1, opened: (editing?.opened ?? 0) + 1})}>
                <Icon name="plus" />
                {t('vocabulary.terms.new')}
              </button>
            ) : null}
          </>
        }
        stats={[
          {label: t('vocabulary.stat.terms'), value: formatNumber(stats.terms)},
          {label: t('vocabulary.stat.equivalents'), value: formatNumber(stats.equivalents), note: t('vocabulary.stat.equivalentsNote')},
          {label: t('vocabulary.stat.domains'), value: formatNumber(stats.domains)},
          {
            label: t('vocabulary.stat.stopwords'),
            value: formatNumber(stats.stopwords),
            note: t('vocabulary.stat.groups', {count: formatNumber(stats.groups)}),
          },
          dirty('terms') || dirty('stopwords')
            ? {label: t('vocabulary.stat.state'), value: t('vocabulary.stat.unsaved'), tone: 'warn' as const}
            : {label: t('vocabulary.stat.state'), value: t('vocabulary.stat.saved'), tone: 'ok' as const},
        ]}
      />
      <div className="tabs" role="tablist" aria-label={t('vocabulary.tabs')}>
        {tabs.map(({list, count}) => (
          <button key={list} type="button" role="tab" aria-selected={tab === list} onClick={() => showTab(list)}>
            {listName(list)}
            <span className="n">{formatNumber(count)}</span>
            {dirty(list) ? <span className="dot" title={t('vocabulary.tabUnsaved')} /> : null}
          </button>
        ))}
      </div>
      <div className="fill scroll w-body" role="tabpanel">
        {tab === 'terms' ? (
          <TermCard
            terms={draft.terms}
            pending={pending('terms')}
            onEdit={(at) => setEditing({at, opened: (editing?.opened ?? 0) + 1})}
          />
        ) : (
          <StopwordCard stops={draft.stopwords} pending={pending('stopwords')} onChange={(items) => edit('stopwords', items)} />
        )}
      </div>
      {editing ? (
        <TermDrawer
          key={editing.opened}
          terms={draft.terms}
          at={editing.at}
          onApply={(item) => applyTerm(editing.at, item)}
          onRemove={() => {
            edit(
              'terms',
              draft.terms.filter((_, index) => index !== editing.at),
            );
            setEditing(null);
          }}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </section>
  );
}
