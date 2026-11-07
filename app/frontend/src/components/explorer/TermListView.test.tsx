import {act, fireEvent, render, screen, within} from '@testing-library/react';
import {useState} from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {ListFormatHelp, TermListView} from '@/components/explorer/TermListView';
import {IntlProvider} from '@/contexts/IntlContext';
import {ApiError} from '@/lib/apiClient';
import {TermListService} from '@/services/termLists';
import {answer, LIST_ID, termList, termRow} from '@/test/explorer';
import {message} from '@/test/render';
import type {TermList} from '@/types/termLists';

interface Spies {
  onStop: () => Promise<void>;
  onResume: () => Promise<unknown>;
  onRedo: (query: string) => void;
}

function Harness({list, spies}: {list: TermList; spies: Spies}) {
  const [opened, setOpened] = useState<ReadonlySet<number>>(() => new Set());
  return (
    <TermListView
      list={list}
      opened={opened}
      onToggle={(n) =>
        setOpened((was) => {
          const next = new Set(was);
          if (next.has(n)) next.delete(n);
          else next.add(n);
          return next;
        })
      }
      {...spies}
    />
  );
}

function show(list: TermList) {
  const spies: Spies = {
    onStop: vi.fn().mockResolvedValue(undefined),
    onResume: vi.fn().mockResolvedValue(null),
    onRedo: vi.fn(),
  };
  const view = render(
    <IntlProvider>
      <Harness list={list} spies={spies} />
    </IntlProvider>,
  );
  const update = (next: TermList) =>
    view.rerender(
      <IntlProvider>
        <Harness list={next} spies={spies} />
      </IntlProvider>,
    );
  return {...spies, update};
}

const sub = () => document.querySelector('.list-head .sub') as HTMLElement;
const rows = () => [...document.querySelectorAll('ol.list-items > li')] as HTMLElement[];

describe('term list view (list-search Requirement 17)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('heads a running list with its progress, the estimate, the header, "■ Durdur" and the report so far', () => {
    show(termList());
    expect(screen.getByRole('heading', {level: 2, name: 'terimler.xlsx'})).toBeInTheDocument();
    expect(sub()).toHaveTextContent(
      message('list.progress.running', {done: 1, total: 3}) +
        message('list.progress.eta', {eta: message('list.seconds', {count: 8})}) +
        message('list.header', {header: 'Terim'}),
    );
    expect(screen.getByRole('button', {name: message('list.stop')})).toHaveClass('ghost');
    expect(screen.queryByRole('button', {name: message('list.resume')})).toBeNull();
    expect(screen.getByRole('link', {name: message('list.reportSoFar')})).toHaveAttribute(
      'href',
      `/api/dwhnavigator/v1/term-lists/${LIST_ID}/report`,
    );
    const bar = document.querySelector('.list-bar') as HTMLElement;
    expect(bar).toHaveClass('live');
    expect((bar.firstChild as HTMLElement).style.width).toBe(`${(1 / 3) * 100}%`);
  });

  it.each([
    ['cancelled', 'list.progress.cancelled', true],
    ['interrupted', 'list.progress.interrupted', true],
  ] as const)('offers "▶ Devam et" on a %s list with unanswered terms', (status, key, resume) => {
    show(termList({status, eta_ms: null}));
    expect(sub()).toHaveTextContent(message(key, {done: 1, total: 3}));
    const button = screen.queryByRole('button', {name: message('list.resume')});
    expect(button !== null).toBe(resume);
    expect(button).toHaveAttribute('title', message('list.resumeTip'));
    expect(screen.queryByRole('button', {name: message('list.stop')})).toBeNull();
    expect(screen.getByRole('link', {name: message('list.report')})).toBeInTheDocument();
  });

  it('has no "▶ Devam et" when every term ended, even with an error (the source\'s condition)', () => {
    show(termList({status: 'cancelled', done: 3, items: [termRow(1, {state: 'error', summary: 'x'}), termRow(2, {state: 'error'}), termRow(3, {state: 'error'})]}));
    expect(screen.queryByRole('button', {name: message('list.resume')})).toBeNull();
  });

  it('says "Tamamlandı" with the time', () => {
    show(termList({status: 'completed', done: 3, total: 3, elapsed_ms: 125000, eta_ms: null}));
    expect(sub()).toHaveTextContent(message('list.progress.completed', {total: 3, elapsed: message('list.minutes', {count: 2})}));
    expect(document.querySelector('.list-bar')).not.toHaveClass('live');
  });

  it('offers no report before a term ended', () => {
    show(termList({done: 0, items: [termRow(1, {state: 'running'})]}));
    expect(screen.queryByRole('link', {name: message('list.reportSoFar')})).toBeNull();
    expect((document.querySelector('.list-bar i') as HTMLElement).style.width).toBe('2%');
  });

  it('shows the reading notes and how many terms could not be analysed', () => {
    show(
      termList({
        notes: ['1 boş satır atlandı.'],
        items: [termRow(1, {state: 'answered', verdict: 'BULUNAMADI', flow: 'unavailable'}), termRow(2, {state: 'answered', verdict: 'VAR', flow: 'reused'})],
      }),
    );
    expect(document.querySelector('.list-notes')).toHaveTextContent('ℹ 1 boş satır atlandı.');
    expect(screen.getByText(message('list.unavailable', {count: 1}))).toHaveClass('answer-fallback');
  });

  it('labels the rows: kept answer, not analysed, best table, missing part, error and state words', () => {
    show(
      termList({
        items: [
          termRow(1, {
            state: 'answered',
            verdict: 'KISMEN VAR',
            flow: 'reused',
            missing: ['oran'],
            best: {key: 'DWH.Kart.vCardLimit1', name: 'vCardLimit1', score: 0.62, level: 'Orta'},
            elapsed_ms: 900,
          }),
          termRow(2, {state: 'answered', verdict: 'BULUNAMADI', flow: 'unavailable', elapsed_ms: 61000}),
          termRow(3, {state: 'error', summary: 'Bu terim analiz edilirken beklenmeyen bir hata oluştu; listeyi sürdürerek yeniden deneyin.'}),
          termRow(4, {state: 'running'}),
          termRow(5, {state: 'stopped'}),
          termRow(6),
        ],
      }),
    );
    const [r1, r2, r3, r4, r5, r6] = rows();
    expect(within(r1).getByText(message('list.flow.reused'))).toHaveAttribute('title', message('list.flow.reusedTip'));
    expect(r1.querySelector('.li-best')).toHaveTextContent('vCardLimit1 · %62');
    expect(r1.querySelector('.li-best b')).toHaveClass('lc-Orta');
    expect(r1.querySelector('.li-miss')).toHaveTextContent(message('list.missing', {items: 'oran'}));
    expect(r1.querySelector('.st')).toHaveClass('v-KISMEN');
    expect(r1.querySelector('.li-ms')).toHaveTextContent(message('list.seconds', {count: 1}));
    expect(within(r2).getByText(message('list.flow.unavailable'))).toHaveAttribute('title', message('list.flow.unavailableTip'));
    expect(r2.querySelector('.li-ms')).toHaveTextContent(message('list.minutes', {count: 1}));
    expect(r3.querySelector('.li-best')).toHaveTextContent(/beklenmeyen bir hata/);
    expect(r3.querySelector('.st.err')).toHaveTextContent(message('list.state.error'));
    expect(r4.querySelector('.st.run')).toHaveTextContent(message('list.state.running'));
    expect(r5.querySelector('.st.wait')).toHaveTextContent(message('list.state.stopped'));
    expect(r6.querySelector('.st.wait')).toHaveTextContent(message('list.state.queued'));
    // Only answered rows open.
    expect(r1.querySelector('.li-row')).toHaveAttribute('aria-expanded', 'false');
    expect(r4.querySelector('.li-row')).not.toHaveAttribute('aria-expanded');
  });

  it('opens an answered term under its row and keeps it open while the list moves on', async () => {
    const item = vi.spyOn(TermListService, 'item').mockResolvedValue(answer());
    const {update, onRedo} = show(termList());
    const row = rows()[0].querySelector('.li-row') as HTMLElement;
    fireEvent.click(row);
    expect(row).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(message('list.loading'))).toHaveClass('faint');
    await screen.findByText(message('answer.best'));
    expect(item).toHaveBeenCalledWith(LIST_ID, 1);
    const detail = rows()[0].querySelector('.li-detail') as HTMLElement;
    // The next poll: the second term ended; the opened answer stays where it was, not read again.
    update(termList({done: 2, items: [termList().items[0], termRow(2, {state: 'answered', verdict: 'VAR', flow: 'analyst'}), termRow(3, {state: 'running'})]}));
    expect(rows()[0].querySelector('.li-detail')).toBe(detail);
    expect(item).toHaveBeenCalledTimes(1);
    expect(rows()[1].querySelector('.st')).toHaveTextContent('VAR');
    // Its report and "Yeniden analiz et" belong to the term.
    const report = vi.spyOn(TermListService, 'itemReport').mockResolvedValue('VSA_ask_x.xlsx');
    fireEvent.click(within(detail).getByRole('link', {name: message('answer.report')}));
    expect(report).toHaveBeenCalledWith(LIST_ID, 1);
    fireEvent.click(row);
    expect(rows()[0].querySelector('.li-detail')).toBeNull();
    expect(onRedo).not.toHaveBeenCalled();
  });

  it('shows why a term could not be opened', async () => {
    vi.spyOn(TermListService, 'item').mockRejectedValue(new ApiError(404, 'Kayıt bulunamadı', 'term_list_item_not_answered'));
    show(termList());
    fireEvent.click(rows()[0].querySelector('.li-row') as HTMLElement);
    expect(await screen.findByText(message('explorer.error.term_list_item_not_answered'))).toHaveClass('error');
  });

  it('stops with "■ Durdur"; the button waits for the answer', async () => {
    let done: () => void = () => undefined;
    const {onStop} = show(termList());
    vi.mocked(onStop).mockImplementation(() => new Promise<void>((resolve) => (done = resolve)));
    const stop = screen.getByRole('button', {name: message('list.stop')});
    fireEvent.click(stop);
    expect(onStop).toHaveBeenCalled();
    expect(stop).toBeDisabled();
    await act(async () => done());
    expect(stop).not.toBeDisabled();
  });

  it('shows a refused resume in the browser\'s alert', async () => {
    const alert = vi.fn();
    vi.stubGlobal('alert', alert);
    const {onResume} = show(termList({status: 'cancelled', eta_ms: null}));
    const resume = screen.getByRole('button', {name: message('list.resume')});
    await act(async () => fireEvent.click(resume));
    expect(onResume).toHaveBeenCalled();
    expect(alert).not.toHaveBeenCalled();
    vi.mocked(onResume).mockResolvedValue(
      new ApiError(409, 'Bir liste zaten çalışıyor; bitmesini bekleyin ya da durdurun.', 'term_list_running'),
    );
    await act(async () => fireEvent.click(resume));
    expect(alert).toHaveBeenCalledWith('Bir liste zaten çalışıyor; bitmesini bekleyin ya da durdurun.');
    expect(resume).not.toBeDisabled();
  });

  it('explains a refused file with the accepted layout, without "Beklenen biçim"', () => {
    render(
      <IntlProvider>
        <ListFormatHelp
          name="liste.xlsx"
          message="Liste tek sütunlu olmalı; dosyada A, B sütunlarında veri var. Terimleri A sütununa yazıp diğer sütunları silin. Beklenen biçim: A sütununda, ilk satırda bir başlık (ör. “Terim”), altında her satırda bir terim."
        />
      </IntlProvider>,
    );
    const help = document.querySelector('section.xl-help') as HTMLElement;
    expect(help.querySelector('.error')).toHaveTextContent(
      message('list.help.failed', {name: 'liste.xlsx'}).trim() +
        ' Liste tek sütunlu olmalı; dosyada A, B sütunlarında veri var. Terimleri A sütununa yazıp diğer sütunları silin.',
    );
    expect(help).not.toHaveTextContent('Beklenen biçim');
    const cells = [...help.querySelectorAll('tbody td:first-of-type')].map((c) => c.textContent);
    expect(cells).toEqual(['list.help.header', 'list.help.example1', 'list.help.example2', 'list.help.example3'].map((k) => message(k)));
    expect(help.querySelectorAll('ul li')).toHaveLength(4);
  });
});
