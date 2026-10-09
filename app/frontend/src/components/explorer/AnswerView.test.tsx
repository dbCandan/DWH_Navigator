import {fireEvent, render, screen, within} from '@testing-library/react';
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

  it('shows "Bir bakışta": the word, the missing part, the count, the best match and the others', () => {
    show(answer());
    expect(document.querySelector('.ans-verdict .av-word')).toHaveTextContent(message('answer.verdict.partial'));
    expect(document.querySelector('.ans-verdict .av-icon')).toHaveTextContent('◐');
    expect(screen.getByText(message('answer.missing', {items: 'oran'}))).toHaveAttribute('title', message('answer.missingTip'));
    expect(screen.getByText(message('answer.suggested', {count: 2}))).toHaveClass('av-for');
    const best = document.querySelector('.ans-best.lc-Yüksek') as HTMLElement;
    expect(within(best).getByRole('img', {name: message('answer.ring', {score: 80, level: 'Yüksek'})})).toBeInTheDocument();
    expect(best).toHaveTextContent(message('answer.best'));
    expect(best.querySelector('.ab-path')).toHaveTextContent('DWH.Kart · Kartlar');
    const also = document.querySelector('ol.ans-also') as HTMLElement;
    expect(also).toHaveAttribute('start', '2');
    expect(within(also).getByRole('button')).toHaveTextContent('vCardLimit2');
  });

  it('draws the coverage matrix with named symbols, open, and the guide cards closed with their counts', () => {
    show(answer());
    const matrix = document.querySelector('details.side-card.matrix') as HTMLDetailsElement;
    expect(matrix.open).toBe(true);
    expect(within(matrix).getAllByLabelText(message('answer.cell.on')).length).toBeGreaterThan(0);
    expect(within(matrix).getByLabelText(message('answer.cell.long'))).toHaveTextContent('◐');
    expect(within(matrix).getAllByLabelText(message('answer.cell.off'))[0]).toHaveTextContent('○');
    const plan = document.querySelector('details.side-card.plan') as HTMLDetailsElement;
    expect(plan.open).toBe(false);
    expect(plan.querySelector('.side-n')).toHaveTextContent('2');
    expect(document.querySelector('details.side-card.warn .side-n')).toHaveTextContent('1');
    expect(document.querySelector('details.side-card.notes li.nt.t-warn')).not.toBeNull();
  });

  it('opens one suggestion row at a time, from the row or from a link to it', () => {
    show(answer());
    const rows = screen.getAllByRole('button', {expanded: false}).filter((b) => b.classList.contains('pick-row'));
    expect(rows).toHaveLength(2);
    fireEvent.click(rows[0]);
    expect(rows[0]).toHaveAttribute('aria-expanded', 'true');
    expect(rows[0].closest('article')).toHaveClass('pick', 'open');
    fireEvent.click(document.querySelector('.ans-also .aa-row') as HTMLElement);
    expect(rows[0]).toHaveAttribute('aria-expanded', 'false');
    expect(rows[1]).toHaveAttribute('aria-expanded', 'true');
    expect(document.getElementById('res-DWH_Kart_vCardLimit2')).toHaveClass('flash');
  });

  it('shows the first six columns, "+N kolon" and one column detail', () => {
    show(answer());
    const card = document.getElementById('res-DWH_Kart_vCardLimit1') as HTMLElement;
    const chips = card.querySelectorAll('.cols .col:not(.more)');
    expect(chips).toHaveLength(8);
    expect(card.querySelectorAll('.cols .col.hidden')).toHaveLength(2);
    expect(chips[0]).toHaveAttribute('title', 'eşleşme · Kolon 0 açıklaması');
    expect(chips[1]).toHaveAttribute('title', message('answer.roleStructural') + ' · Kolon 1 açıklaması');
    expect(within(chips[1] as HTMLElement).getByTitle(message('answer.pii'))).toBeInTheDocument();
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
});
