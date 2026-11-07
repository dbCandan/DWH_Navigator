import {useState} from 'react';
import {Drawer} from '@/components/admin/Drawer';
import {Field} from '@/components/admin/Field';
import {SuggestCombobox} from '@/components/admin/SuggestCombobox';
import {useIntl} from '@/contexts/IntlContext';
import {useToast} from '@/hooks/useToast';
import {fold} from '@/lib/fold';
import type {TermItem} from '@/types/vocabulary';

const EMPTY: TermItem = {term: '', equivalents: [], domain: '', note: ''};

/**
 * The term drawer (vocabulary-management Requirement 11; admin.html Words.editTerm): term,
 * equivalents one per line (or comma, or bar), domain with suggestions, note. The change gathers
 * on the card; the screen's check is a convenience, the binding one is the server's.
 */
export function TermDrawer({
  terms,
  at,
  onApply,
  onRemove,
  onClose,
}: {
  terms: readonly TermItem[];
  /** The edited term's place in the list; -1 for a new term. */
  at: number;
  onApply: (item: TermItem) => void;
  onRemove: () => void;
  onClose: () => void;
}) {
  const {t} = useIntl();
  const {toast} = useToast();
  const item = at >= 0 ? terms[at] : EMPTY;
  const [term, setTerm] = useState(item.term);
  const [equivalents, setEquivalents] = useState(item.equivalents.join('\n'));
  const [domain, setDomain] = useState(item.domain);
  const [note, setNote] = useState(item.note);
  const domains = [...new Set(terms.map((other) => other.domain).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'tr'));

  function apply() {
    const record: TermItem = {
      term: term.trim(),
      equivalents: [...new Set(equivalents.split(/[\n,|]/).map((word) => word.trim()).filter(Boolean))],
      domain: domain.trim(),
      note: note.trim(),
    };
    if (!record.term || !record.equivalents.length) {
      toast(t('vocabulary.term.missing'), [t('vocabulary.term.missingLine')], true);
      return;
    }
    const clash = terms.findIndex((other, index) => index !== at && fold(other.term) === fold(record.term));
    if (clash >= 0) {
      toast(t('vocabulary.term.duplicate'), [t('vocabulary.term.duplicateLine', {term: terms[clash].term})], true);
      return;
    }
    onApply(record);
  }

  return (
    <Drawer
      title={at >= 0 ? item.term : t('vocabulary.term.new')}
      sub={t('vocabulary.term.sub')}
      onClose={onClose}
      foot={
        <>
          {at >= 0 ? (
            <button className="btn danger" type="button" onClick={onRemove}>
              {t('vocabulary.term.remove')}
            </button>
          ) : null}
          <div className="grow" />
          <button className="btn ghost" type="button" onClick={onClose}>
            {t('vocabulary.term.cancel')}
          </button>
          <button className="btn primary" type="button" onClick={apply}>
            {at >= 0 ? t('vocabulary.term.apply') : t('vocabulary.term.add')}
          </button>
        </>
      }
    >
      <div className="form">
        <Field id="term-term" label={t('vocabulary.term.term')}>
          <input
            id="term-term"
            type="text"
            value={term}
            placeholder={t('vocabulary.term.termPlaceholder')}
            autoComplete="off"
            onChange={(event) => setTerm(event.target.value)}
          />
        </Field>
        <Field id="term-equivalents" label={t('vocabulary.term.equivalents')} hint={t('vocabulary.term.equivalentsHelp')}>
          <textarea
            id="term-equivalents"
            rows={6}
            value={equivalents}
            placeholder={t('vocabulary.term.equivalentsPlaceholder')}
            spellCheck={false}
            aria-describedby="term-equivalents-hint"
            onChange={(event) => setEquivalents(event.target.value)}
          />
        </Field>
        <Field id="term-domain" label={t('vocabulary.term.domain')} hint={t('vocabulary.term.domainHelp')}>
          <SuggestCombobox
            id="term-domain"
            value={domain}
            options={domains.map((name) => ({value: name}))}
            listLabel={t('vocabulary.term.domainList')}
            placeholder={t('vocabulary.term.domainPlaceholder')}
            describedBy="term-domain-hint"
            onChange={setDomain}
          />
        </Field>
        <Field id="term-note" label={t('vocabulary.term.note')} hint={t('vocabulary.term.noteHelp')}>
          <input
            id="term-note"
            type="text"
            value={note}
            autoComplete="off"
            aria-describedby="term-note-hint"
            onChange={(event) => setNote(event.target.value)}
          />
        </Field>
      </div>
    </Drawer>
  );
}
