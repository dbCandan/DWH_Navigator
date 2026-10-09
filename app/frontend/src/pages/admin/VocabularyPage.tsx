import {useEffect, useState} from 'react';
import {PageHead} from '@/components/admin/PageHead';
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
import type {TermItem, VocabularyListName, VocabularyListSaved} from '@/types/vocabulary';

/**
 * The "Kelimeler" page (vocabulary-management Requirement 10-13; admin.html Words): the term
 * dictionary above, the stopwords below. Edits gather on each card and are written with one
 * press, the index rebuilt with them; the saved lists are read again only when no edit waits.
 */
export default function VocabularyPage() {
  const {t} = useIntl();
  const {toast, hold, reportUnreachable} = useToast();
  const {saved, draft, dirty, adoptBoth, adoptOne, edit, revert} = useVocabularyDraft();
  const refresh = useAdminRefresh();
  const download = useDownload();
  const [failure, setFailure] = useState<unknown>(null);
  const [editing, setEditing] = useState<{at: number; opened: number} | null>(null);
  const label = t('admin.page.kelimeler.label');
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
    if (!window.confirm(question)) return;
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

  const actions = (list: VocabularyListName) => (
    <ListActions
      onImport={(file) => void importFile(list, file)}
      onExport={() => void download(() => VocabularyService.exportWorkbook(list))}
    />
  );
  const pending = (list: VocabularyListName) =>
    dirty(list) ? <PendingBar onRevert={() => revert(list)} onSave={() => save(list)} /> : null;

  if (!saved)
    return (
      <section className="page on" id="p-kelimeler" aria-label={label}>
        <PageHead title={label} />
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

  return (
    <section className="page on" id="p-kelimeler" aria-label={label}>
      <PageHead title={label} description={t('admin.page.kelimeler.description')} />
      <TermCard
        terms={draft.terms}
        actions={actions('terms')}
        pending={pending('terms')}
        onEdit={(at) => setEditing({at, opened: (editing?.opened ?? 0) + 1})}
      />
      <StopwordCard
        stops={draft.stopwords}
        actions={actions('stopwords')}
        pending={pending('stopwords')}
        onChange={(items) => edit('stopwords', items)}
      />
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
