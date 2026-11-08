import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {AnswerView} from '@/components/explorer/AnswerView';
import {IntlProvider} from '@/contexts/IntlContext';
import {answer, answerObject} from '@/test/explorer';
import {message} from '@/test/render';
import type {AnalysisAnswer} from '@/types/analysis';

function show(r: AnalysisAnswer, props: Partial<Parameters<typeof AnswerView>[0]> = {}) {
  const onRedo = vi.fn();
  const onReport = vi.fn();
  render(
    <IntlProvider>
      <AnswerView answer={r} onRedo={onRedo} onReport={onReport} reportHref="/api/dwhnavigator/v1/analyses/x/report" {...props} />
    </IntlProvider>,
  );
  return {onRedo, onReport};
}

describe('answer view (question-analysis Requirement 21)', () => {
  afterEach(() => vi.restoreAllMocks());

  it('heads the answer with the verdict, the analyst, the question and the report', () => {
    const {onReport} = show(answer());
    const head = document.querySelector('.ans.v-KISMEN > .answer.ans-head .answer-top') as HTMLElement;
    expect(within(head).getByText('KISMEN VAR')).toHaveClass('vbadge');
    expect(within(head).getByText(message('answer.analyst', {model: 'fake-analyst'}))).toHaveAttribute(
      'title',
      message('answer.analystTip'),
    );
    expect(head.querySelector('.answer-q')).toHaveTextContent('kart limit doluluk oranı');
    expect(head.querySelector('.redo')).toBeNull();
    const report = within(head).getByRole('link', {name: message('answer.report')});
    expect(report.getAttribute('href')).not.toMatch(/token|bearer/i);
    fireEvent.click(report);
    expect(onReport).toHaveBeenCalledTimes(1);
  });

  it('shows "Bir bakışta": the word, the missing part, the count and the best match', () => {
    show(answer());
    expect(document.querySelector('.ans-verdict .av-word')).toHaveTextContent(message('answer.verdict.partial'));
    expect(document.querySelector('.ans-verdict .av-icon')).toHaveTextContent('◐');
    expect(screen.getByText(message('answer.missing', {items: 'oran'}))).toHaveAttribute('title', message('answer.missingTip'));
    expect(screen.getByText(message('answer.suggested', {count: 2}))).toHaveClass('av-for');
    const best = document.querySelector('.ans-best.lc-Yüksek') as HTMLElement;
    expect(within(best).getByRole('img', {name: message('answer.ring', {score: 80, level: 'Yüksek'})})).toBeInTheDocument();
    expect(best).toHaveTextContent(message('answer.best'));
    expect(best.querySelector('.ab-path')).toHaveTextContent('DWH.Kart · Kartlar');
    expect(document.querySelector('.ans-also')).toBeNull(); // the others are the rows below, once
  });

  it('keeps the analyst reading open and lit: the finding, how it understood the request, what it searched', () => {
    show(answer());
    const brief = screen.getByRole('region', {name: message('answer.summary')});
    expect(brief.querySelector('.ans-title')).toHaveTextContent('Kart limit doluluğu vCardLimit1 tablosunda hesaplanabilir');
    expect(brief.querySelector('.ans-lead')).toHaveTextContent('Oran hazır bir kolon değildir.');
    expect(brief.closest('details')).toBeNull(); // nothing to unfold
    const read = brief.querySelector('.brief-read') as HTMLElement;
    expect(read).toHaveTextContent(message('answer.understood'));
    expect(read).toHaveTextContent('Kart başına limit kullanım oranı isteniyor.');
    const terms = brief.querySelector('.brief-terms') as HTMLElement;
    expect(terms).toHaveTextContent(message('answer.searchedFor'));
    expect(terms.querySelectorAll('.chip')).toHaveLength(4); // three concepts and the expansion
  });

  it('counts the plan, the warnings and the notes beside the best match; a count opens its card', () => {
    show(answer());
    const facts = document.querySelector('.ans-find .facts') as HTMLElement;
    const warn = within(facts).getByRole('button', {name: '1 ' + message('answer.fact.watch')});
    expect(within(facts).getByRole('button', {name: '2 ' + message('answer.fact.plan')})).toHaveClass('fact', 'plan');
    expect(within(facts).getByRole('button', {name: '1 ' + message('answer.fact.notes')})).toHaveClass('fact', 'notes');
    const notes = document.querySelector('details.side-card.notes') as HTMLDetailsElement;
    expect(notes.open).toBe(false);
    fireEvent.click(within(facts).getByRole('button', {name: '1 ' + message('answer.fact.notes')}));
    expect(notes.open).toBe(true);
    expect(notes).toHaveClass('flash');
    expect(warn).toHaveClass('warn');
  });

  it('opens the plan and the warnings, keeps the notes closed and draws no coverage matrix', () => {
    show(answer());
    expect(document.querySelector('.side-card.matrix, .ov-mx')).toBeNull();
    const plan = document.querySelector('details.side-card.plan') as HTMLDetailsElement;
    expect(plan.open).toBe(true);
    expect(plan.querySelector('.side-n')).toHaveTextContent('2');
    const warn = document.querySelector('details.side-card.warn') as HTMLDetailsElement;
    expect(warn.open).toBe(true);
    expect(warn.querySelector('.side-n')).toHaveTextContent('1');
    expect((document.querySelector('details.side-card.notes') as HTMLDetailsElement).open).toBe(false);
    expect(document.querySelector('details.side-card.notes li.nt.t-warn')).not.toBeNull();
  });

  it('opens one suggestion row at a time, from the row or from a link to it', () => {
    show(answer());
    const rows = screen.getAllByRole('button', {expanded: false}).filter((b) => b.classList.contains('pick-row'));
    expect(rows).toHaveLength(2);
    fireEvent.click(rows[1]);
    expect(rows[1]).toHaveAttribute('aria-expanded', 'true');
    expect(rows[1].closest('article')).toHaveClass('pick', 'open');
    fireEvent.click(document.querySelector('.ans-best') as HTMLElement);
    expect(rows[1]).toHaveAttribute('aria-expanded', 'false');
    expect(rows[0]).toHaveAttribute('aria-expanded', 'true');
    expect(document.getElementById('res-DWH_Kart_vCardLimit1')).toHaveClass('flash');
  });

  it('shows the first six columns, "+N kolon" and one column detail', () => {
    show(answer());
    const card = document.getElementById('res-DWH_Kart_vCardLimit1') as HTMLElement;
    const chips = card.querySelectorAll('.cols .col:not(.more)');
    expect(chips).toHaveLength(8);
    expect(card.querySelectorAll('.cols .col.hidden')).toHaveLength(2);
    expect(chips[0]).toHaveAttribute('title', 'eşleşme · Kolon 0 açıklaması');
    expect(chips[1]).toHaveAttribute('title', message('answer.roleStructural') + ' · Kolon 1 açıklaması');
    fireEvent.click(within(card).getByRole('button', {name: message('answer.moreColumns', {count: 2})}));
    expect(card.querySelectorAll('.cols .col.hidden')).toHaveLength(0);
    fireEvent.click(chips[0]);
    const detail = card.querySelector('.detail.on') as HTMLElement;
    expect(detail).toHaveTextContent(message('answer.synonyms', {items: 'limit tutarı'}));
    expect(detail).toHaveTextContent('✓ ad eşleşmesi');
    expect(detail).toHaveTextContent('! boş olabilir');
  });

  it('keeps the analyst text plain: tables become buttons to their card, CamelCase names mono', () => {
    show(answer({objects: [answerObject(1, {reason: '<img src=x onerror=alert(1)> DWH.Kart.vCardLimit1 ve UsedAmount'})]}));
    const reason = document.querySelector('#res-DWH_Kart_vCardLimit1 .res-reason') as HTMLElement;
    expect(reason.querySelector('img')).toBeNull();
    expect(reason).toHaveTextContent('<img src=x onerror=alert(1)>');
    const chip = within(reason).getByTitle(message('answer.openDetail', {key: 'DWH.Kart.vCardLimit1'}));
    expect(chip.tagName).toBe('BUTTON');
    expect(chip).toHaveTextContent('vCardLimit1');
    expect(chip.querySelectorAll('wbr')).toHaveLength(2);
    expect(reason.querySelector('code.cn')).toHaveTextContent('UsedAmount');
  });

  it('shows "Analiz yapılamadı" with its reason and the empty answer text', () => {
    show(
      answer({
        analyst: false,
        verdict: 'BULUNAMADI',
        objects: [],
        notes: [],
        design: [],
        attention: [],
        missing: [],
        llm_model: '',
        fallback: 'Model sunucusuna ulaşılamadı.',
        summary: 'Analiz yapılamadı: Model sunucusuna ulaşılamadı.',
      }),
    );
    const note = message('answer.unavailableNote', {why: 'Model sunucusuna ulaşılamadı.'});
    expect(screen.getByText(message('answer.unavailable'))).toHaveAttribute('title', note);
    expect(document.querySelector('.answer-fallback')).toHaveTextContent(
      message('answer.unavailableShort', {why: 'Model sunucusuna ulaşılamadı.'}),
    );
    expect(screen.getByText(message('answer.noneAboveThreshold'))).toBeInTheDocument();
    expect(screen.getByText(message('answer.empty'))).toHaveClass('empty');
    expect(document.querySelector('.ans-grid')).toHaveClass('solo');
    expect(document.querySelector('.ans-side')).toBeNull();
  });

  it('marks a kept answer with its date and asks for a new analysis on "Yeniden analiz et"', () => {
    const {onRedo} = show(answer({reused: {at: '08.10.2026 14:05', query: 'kart limiti', match: 'aynı anlam'}}));
    expect(screen.getByText(message('answer.reused', {date: '08.10.2026'}))).toHaveAttribute(
      'title',
      message('answer.reusedMeaning', {query: 'kart limiti', at: '08.10.2026 14:05'}),
    );
    fireEvent.click(screen.getByRole('button', {name: message('answer.redo')}));
    expect(onRedo).toHaveBeenCalledTimes(1);
  });

  it('lists the search details: concepts, expansion terms, method and the timing line', () => {
    show(answer());
    const details = screen.getByText(message('answer.searchDetails')).closest('details') as HTMLElement;
    expect(details.querySelector('.chip.k-olcu')).toHaveTextContent('ölçü · doluluk');
    expect(within(details).getByText(message('answer.expansion', {count: 2}))).toHaveAttribute('title', 'kredi limiti, limit tutarı');
    expect(details).toHaveTextContent('48.2 sn · sözlük abcdef12-11136 · LLM yerel/fake-analyst');
  });

  it('folds the guide cards, the notes first, while the answer would run past the window', async () => {
    const height = window.innerHeight;
    // The board runs 300 px past the window while two guide cards are open.
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      const open = document.querySelectorAll('details.side-card[open]').length;
      const bottom = this.classList.contains('ans') ? height + (open >= 2 ? 300 : -100) : 0;
      return {bottom, top: 0, left: 0, right: 0, width: 0, height: 0, x: 0, y: 0, toJSON: () => ({})} as DOMRect;
    });
    show(answer());
    const open = (cls: string) => (document.querySelector('details.side-card.' + cls) as HTMLDetailsElement).open;
    expect(open('warn')).toBe(true); // measured once the page settled, two frames later
    await waitFor(() => expect(open('warn')).toBe(false)); // folded first among the open ones
    expect(open('notes')).toBe(false);
    expect(open('plan')).toBe(true); // the board fits once the warnings fold
  });

  it('draws a table the analyst names but did not suggest apart, opening its dictionary file', () => {
    const openTable = vi.fn();
    show(answer({attention: ['vUMECustomer tablosundaki CUSRecordingTime ile karıştırılmamalı.']}), {
      openTable,
      hasTable: () => true,
      catalog: [{key: 'EDWDM.DGM.vUMECustomer', name: 'vUMECustomer'}],
    });
    const chip = document.querySelector('.watch button.tn.other') as HTMLElement;
    expect(chip).toHaveTextContent('vUMECustomer');
    expect(chip.getAttribute('title')).toContain(message('answer.notSuggested'));
    fireEvent.click(chip);
    expect(openTable).toHaveBeenCalledWith('EDWDM.DGM.vUMECustomer');
  });

  it('keeps a table and its column on one line', () => {
    show(answer({design: ['vCardLimit1.UsedAmount kolonunu alın.']}));
    const pair = document.querySelector('.steps .tc') as HTMLElement;
    expect(pair.querySelector('.tn')).toHaveTextContent('vCardLimit1');
    expect(pair.querySelector('.cn')).toHaveTextContent('.UsedAmount');
  });
});

