import {fireEvent, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from '@/lib/apiClient';
import {clearAuth} from '@/lib/authStorage';
import {VocabularyService} from '@/services/vocabulary';
import {answerConfirm, indexState, stopList, termList} from '@/test/admin';
import {message, renderApp, signedIn} from '@/test/render';
import type {StopwordItem, TermItem, VocabularyListSaved} from '@/types/vocabulary';

const KREDI: TermItem = {term: 'fon kullandırım', equivalents: ['kredi', 'finansman'], domain: 'katılım', note: 'Kredinin karşılığı'};
const KAR: TermItem = {term: 'kâr payı', equivalents: ['faiz'], domain: 'katılım', note: ''};
const STOPS: StopwordItem[] = [
  {word: 've', group: 'Genel'},
  {word: 'veya', group: 'Genel'},
  {word: 'and', group: 'İngilizce'},
];

function serve(terms: TermItem[] = [KREDI, KAR], stops: StopwordItem[] = STOPS) {
  vi.mocked(VocabularyService.read).mockImplementation(async (list) => (list === 'terms' ? termList(terms) : stopList(stops)));
}

const saved = (list: 'terms' | 'stopwords', items: TermItem[] | StopwordItem[], changed = true): VocabularyListSaved => ({
  list,
  revision: 2,
  items,
  changed,
  elapsed_ms: 2400,
  index: indexState(),
});

async function openPage() {
  renderApp('/admin/kelimeler');
  return screen.findByRole('heading', {level: 2, name: message('vocabulary.terms.title', {count: 2})});
}

describe('Kelimeler page (vocabulary-management Requirement 10-13)', () => {
  beforeEach(() => {
    signedIn('manager');
    serve();
  });
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
  });

  it('shows both cards, the terms table and the stopword groups in first-seen order', async () => {
    await openPage();
    expect(screen.getByText(message('admin.page.kelimeler.description'))).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 2, name: message('vocabulary.stops.title', {count: 3})})).toBeInTheDocument();
    const row = screen.getByText('fon kullandırım').closest('tr') as HTMLElement;
    expect(within(row).getAllByText(/kredi|finansman/).map((tag) => tag.className)).toEqual(['tag', 'tag']);
    expect(within(screen.getByText('kâr payı').closest('tr') as HTMLElement).getByText('—')).toBeInTheDocument();
    expect([...document.querySelectorAll('.sw-h b')].map((node) => node.textContent)).toEqual(['Genel', 'İngilizce']);
    expect(screen.getAllByRole('button', {name: message('vocabulary.export.button')})[0]).toHaveAttribute('title', message('vocabulary.export.tip'));
    expect(screen.queryByText(/data\/terms\.jsonl/)).toBeNull();
  });

  it('searches terms Turkish-aware and says when nothing matches', async () => {
    const title = await openPage();
    const search = screen.getByRole('searchbox', {name: message('vocabulary.terms.search')});
    fireEvent.change(search, {target: {value: 'KAR PAYI'}});
    expect(title).toHaveTextContent(message('vocabulary.terms.titleFiltered', {count: 1, total: 2}));
    fireEvent.change(search, {target: {value: 'yok böyle'}});
    expect(screen.getByText(message('vocabulary.terms.noMatch'))).toBeInTheDocument();
  });

  it('adds a term at the top, checks it on the screen and saves the list with the index', async () => {
    const save = vi.spyOn(VocabularyService, 'save').mockImplementation(async (_list, items) => saved('terms', items as TermItem[]));
    await openPage();
    fireEvent.click(screen.getByRole('button', {name: message('vocabulary.terms.new')}));
    const drawer = await screen.findByRole('dialog', {name: message('vocabulary.term.new')});
    const add = within(drawer).getByRole('button', {name: message('vocabulary.term.add')});
    fireEvent.change(within(drawer).getByLabelText(message('vocabulary.term.term')), {target: {value: 'Fon Kullandırım'}});
    fireEvent.click(add);
    expect(await screen.findByText(message('vocabulary.term.missingLine'))).toBeInTheDocument();
    fireEvent.change(within(drawer).getByLabelText(message('vocabulary.term.equivalents')), {target: {value: 'a\nb, a|c'}});
    fireEvent.click(add);
    expect(await screen.findByText(message('vocabulary.term.duplicateLine', {term: 'fon kullandırım'}))).toBeInTheDocument();
    fireEvent.change(within(drawer).getByLabelText(message('vocabulary.term.term')), {target: {value: ' icare '}});
    fireEvent.click(add);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByRole('heading', {level: 2, name: message('vocabulary.terms.title', {count: 3})})).toBeInTheDocument();
    expect(document.querySelector('#w-terms tbody tr td')?.textContent).toBe('icare');

    const bar = screen.getByText(message('vocabulary.pending.text')).closest('.wbar') as HTMLElement;
    fireEvent.click(within(bar).getByRole('button', {name: message('vocabulary.pending.save')}));
    expect(await screen.findByText(message('vocabulary.landed.saved', {list: message('vocabulary.list.terms')}))).toBeInTheDocument();
    expect(screen.getByText(message('vocabulary.landed.rebuilt', {count: 3, duration: '2,4 sn'}))).toBeInTheDocument();
    expect(save).toHaveBeenCalledWith('terms', [{term: 'icare', equivalents: ['a', 'b', 'c'], domain: '', note: ''}, KREDI, KAR]);
    expect(screen.queryByText(message('vocabulary.pending.text'))).toBeNull();
  });

  it('edits and removes a term from its drawer opened with the keyboard, and drops the edits on "Geri al"', async () => {
    await openPage();
    fireEvent.keyDown(screen.getByText('kâr payı').closest('tr') as HTMLElement, {key: 'Enter'});
    const drawer = await screen.findByRole('dialog', {name: 'kâr payı'});
    expect(within(drawer).getByText(message('vocabulary.term.sub'))).toBeInTheDocument();
    fireEvent.click(within(drawer).getByRole('button', {name: message('vocabulary.term.remove')}));
    expect(screen.queryByText('kâr payı')).toBeNull();
    const bar = screen.getByText(message('vocabulary.pending.text')).closest('.wbar') as HTMLElement;
    fireEvent.click(within(bar).getByRole('button', {name: message('vocabulary.pending.revert')}));
    expect(screen.getByText('kâr payı')).toBeInTheDocument();
  });

  it('adds, refuses and removes stopwords, adds a group and keeps the edits across admin pages', async () => {
    const save = vi.spyOn(VocabularyService, 'save').mockRejectedValue(new ApiError(422, '“iki kelime”: durak kelime tek kelime olmalı', 'vocabulary_stopword_not_single_word'));
    await openPage();
    const box = screen.getByRole('textbox', {name: message('vocabulary.stops.addTo', {group: 'Genel'})});
    fireEvent.change(box, {target: {value: 'VE, ile'}});
    fireEvent.keyDown(box, {key: 'Enter'});
    expect(screen.getByRole('heading', {level: 2, name: message('vocabulary.stops.title', {count: 4})})).toBeInTheDocument();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('textbox', {name: message('vocabulary.stops.addTo', {group: 'Genel'})})));
    fireEvent.change(document.activeElement as HTMLInputElement, {target: {value: 'veya'}});
    fireEvent.keyDown(document.activeElement as HTMLInputElement, {key: 'Enter'});
    expect(await screen.findByText(message('vocabulary.stops.already'))).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: message('vocabulary.stops.removeWord', {word: 'and'})}));
    expect(screen.queryByText(message('vocabulary.stops.ungrouped'))).toBeNull();

    fireEvent.click(screen.getByRole('button', {name: message('vocabulary.stops.addGroup')}));
    expect(await screen.findByText(message('vocabulary.stops.groupMissing'))).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', {name: message('vocabulary.stops.newGroup')}), {target: {value: 'Dolgu'}});
    fireEvent.change(screen.getByRole('textbox', {name: message('vocabulary.stops.newWordsLabel')}), {target: {value: 'lütfen rica'}});
    fireEvent.click(screen.getByRole('button', {name: message('vocabulary.stops.addGroup')}));
    expect([...document.querySelectorAll('.sw-h b')].map((node) => node.textContent)).toEqual(['Genel', 'Dolgu']);
    expect(screen.getByRole('textbox', {name: message('vocabulary.stops.newGroup')})).toHaveValue('');

    fireEvent.click(screen.getByRole('link', {name: message('admin.page.bakim.label')}));
    await screen.findByRole('heading', {level: 1, name: message('admin.page.bakim.label')});
    fireEvent.click(screen.getByRole('link', {name: message('admin.page.kelimeler.label')}));
    expect(await screen.findByRole('heading', {level: 2, name: message('vocabulary.stops.title', {count: 5})})).toBeInTheDocument();
    expect(VocabularyService.read).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByRole('button', {name: message('vocabulary.pending.save')}));
    expect(await screen.findByText('“iki kelime”: durak kelime tek kelime olmalı')).toBeInTheDocument();
    expect(save).toHaveBeenCalledWith('stopwords', expect.arrayContaining([{word: 'ile', group: 'Genel'}]));
    expect(screen.getByText(message('vocabulary.pending.text'))).toBeInTheDocument();
  });

  it('asks before leaving the admin screen with unsaved list edits', async () => {
    await openPage();
    fireEvent.click(screen.getByRole('button', {name: message('vocabulary.stops.removeWord', {word: 'and'})}));
    const confirm = answerConfirm(false);
    fireEvent.click(screen.getByRole('link', {name: message('admin.back')}));
    expect(confirm).toHaveBeenCalledWith(message('admin.leave.confirm'));
    expect(screen.getByTestId('where').textContent).toBe('/admin/kelimeler');
    const event = new Event('beforeunload', {cancelable: true});
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it('imports a list from Excel after the confirmation and keeps the other list\'s edits', async () => {
    const imported = vi.spyOn(VocabularyService, 'importWorkbook').mockResolvedValue(saved('terms', [KREDI, KAR], false));
    const pickers: HTMLInputElement[] = [];
    vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(function (this: HTMLInputElement) {
      pickers.push(this);
    });
    await openPage();
    fireEvent.click(screen.getByRole('button', {name: message('vocabulary.stops.removeWord', {word: 'and'})}));
    const [termsImport] = screen.getAllByRole('button', {name: message('vocabulary.import.button')});
    expect(termsImport).toHaveAttribute('title', message('vocabulary.import.tip'));
    fireEvent.click(termsImport);
    const confirm = answerConfirm(true);
    Object.defineProperty(pickers[0], 'files', {value: [new File(['x'], 'terimler.csv')]});
    pickers[0].onchange?.(new Event('change'));
    expect(await screen.findByText(message('admin.excel.notExcel'))).toBeInTheDocument();
    fireEvent.click(termsImport);
    Object.defineProperty(pickers[1], 'files', {value: [new File(['x'], 'terimler.xlsx')]});
    pickers[1].onchange?.(new Event('change'));
    expect(confirm).toHaveBeenCalledWith(message('vocabulary.import.confirm.terms', {name: 'terimler.xlsx'}));
    expect(await screen.findByText(message('vocabulary.landed.unchanged', {count: 2}))).toBeInTheDocument();
    expect(imported).toHaveBeenCalledWith('terms', expect.objectContaining({name: 'terimler.xlsx'}));
    expect(screen.getByRole('heading', {level: 2, name: message('vocabulary.stops.title', {count: 2})})).toBeInTheDocument();
  });

  it('names the dropped edits in the import confirmation', async () => {
    const pickers: HTMLInputElement[] = [];
    vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(function (this: HTMLInputElement) {
      pickers.push(this);
    });
    await openPage();
    fireEvent.click(screen.getByRole('button', {name: message('vocabulary.stops.removeWord', {word: 'and'})}));
    const confirm = answerConfirm(false);
    fireEvent.click(screen.getAllByRole('button', {name: message('vocabulary.import.button')})[1]);
    Object.defineProperty(pickers[0], 'files', {value: [new File(['x'], 'durak.xlsx')]});
    pickers[0].onchange?.(new Event('change'));
    expect(confirm).toHaveBeenCalledWith(message('vocabulary.import.confirm.stopwordsDropped', {name: 'durak.xlsx'}));
  });
});
