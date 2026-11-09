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

async function openPage(path = '/admin/kelimeler') {
  renderApp(path);
  return screen.findByRole('heading', {level: 2, name: message('vocabulary.terms.title', {count: 2})});
}

/** A tab is named "<label> <count>": the label first, then exactly this count. */
const tab = (list: 'terms' | 'stopwords', count: number) => {
  const label = message(`vocabulary.list.${list}`);
  return screen.getByRole('tab', {
    name: (name) =>
      name.startsWith(label) && /^\s*(\d+)\b/.exec(name.slice(label.length))?.[1] === String(count),
  });
};

/** The stopwords' tab, opened. */
function openStops(count = 3) {
  fireEvent.click(tab('stopwords', count));
  return screen.getByRole('heading', {level: 2, name: message('vocabulary.stops.title', {count})});
}

const termTile = (term: string) => screen.getByRole('button', {name: message('vocabulary.terms.open', {term})});
const stat = (label: string) =>
  [...document.querySelectorAll('.hb-stats .st')].find((node) => node.querySelector('dt')?.textContent === label);
const pickFile = (input: HTMLInputElement, name: string) => {
  Object.defineProperty(input, 'files', {value: [new File(['x'], name)]});
  input.onchange?.(new Event('change'));
};

describe('Kelimeler page (vocabulary-management Requirement 10-13)', () => {
  beforeEach(() => {
    signedIn('manager');
    serve();
  });
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
  });

  it('shows the lists in the hero, the terms as tiles and the stopword groups under their tab', async () => {
    await openPage();
    expect(screen.getByText(message('admin.page.kelimeler.description'))).toBeInTheDocument();
    expect(stat(message('vocabulary.stat.terms'))?.querySelector('dd')).toHaveTextContent('2');
    expect(stat(message('vocabulary.stat.equivalents'))?.querySelector('dd')).toHaveTextContent('3');
    expect(stat(message('vocabulary.stat.domains'))?.querySelector('dd')).toHaveTextContent('1');
    expect(stat(message('vocabulary.stat.stopwords'))?.querySelector('small')).toHaveTextContent(message('vocabulary.stat.groups', {count: 2}));
    expect(stat(message('vocabulary.stat.state'))).toHaveClass('st', 'ok');
    expect(tab('terms', 2)).toHaveAttribute('aria-selected', 'true');
    const tile = termTile('fon kullandırım');
    expect(within(tile).getAllByText(/kredi|finansman/).map((tag) => tag.className)).toEqual(['tag', 'tag']);
    expect(within(tile).getByText('katılım')).toHaveClass('dom');
    expect(within(tile).getByText('Kredinin karşılığı')).toHaveClass('tnote');
    expect(termTile('kâr payı').querySelector('.tnote')).toBeNull();
    expect(screen.getByRole('button', {name: message('vocabulary.export.button')})).toHaveAttribute('title', message('vocabulary.export.tip'));

    openStops();
    expect(tab('stopwords', 3)).toHaveAttribute('aria-selected', 'true');
    expect([...document.querySelectorAll('.sw-group .sw-h b')].map((node) => node.textContent)).toEqual(['Genel', 'İngilizce']);
    expect(screen.queryByRole('button', {name: message('vocabulary.terms.new')})).toBeNull();
    expect(screen.queryByText(/data\/terms\.jsonl/)).toBeNull();
  });

  it('opens the stopwords from the address', async () => {
    renderApp('/admin/kelimeler?liste=durak');
    expect(await screen.findByRole('heading', {level: 2, name: message('vocabulary.stops.title', {count: 3})})).toBeInTheDocument();
  });

  it('searches terms Turkish-aware, filters them by domain and says when nothing matches', async () => {
    serve([KREDI, KAR, {term: 'ikamet', equivalents: ['adres'], domain: 'müşteri', note: ''}]);
    renderApp('/admin/kelimeler');
    const title = await screen.findByRole('heading', {level: 2, name: message('vocabulary.terms.title', {count: 3})});
    const filter = screen.getByRole('group', {name: message('vocabulary.terms.domainFilter')});
    expect(within(filter).getAllByRole('button').map((chip) => chip.textContent)).toEqual([
      message('vocabulary.terms.allDomains') + '3',
      'katılım2',
      'müşteri1',
    ]);
    fireEvent.click(within(filter).getByRole('button', {name: /^müşteri\s*1$/}));
    expect(title).toHaveTextContent(message('vocabulary.terms.titleFiltered', {count: 1, total: 3}));
    expect(screen.queryByRole('button', {name: message('vocabulary.terms.open', {term: 'kâr payı'})})).toBeNull();
    fireEvent.click(within(filter).getByRole('button', {name: new RegExp(`^${message('vocabulary.terms.allDomains')}\\s*3$`)}));
    const search = screen.getByRole('searchbox', {name: message('vocabulary.terms.search')});
    fireEvent.change(search, {target: {value: 'KAR PAYI'}});
    expect(title).toHaveTextContent(message('vocabulary.terms.titleFiltered', {count: 1, total: 3}));
    fireEvent.change(search, {target: {value: 'yok böyle'}});
    expect(screen.getByText(message('vocabulary.terms.noMatch'))).toBeInTheDocument();
  });

  it('suggests the existing domains in its own list and keeps a new one as typed', async () => {
    await openPage();
    fireEvent.click(document.querySelector('.hb-acts .btn.primary') as HTMLElement);
    const drawer = await screen.findByRole('dialog', {name: message('vocabulary.term.new')});
    const box = within(drawer).getByRole('combobox', {name: message('vocabulary.term.domain')});
    const list = () => within(drawer).queryByRole('listbox', {name: message('vocabulary.term.domainList')});

    fireEvent.click(box);
    fireEvent.click(within(list() as HTMLElement).getByRole('option', {name: 'katılım'}));
    expect(box).toHaveValue('katılım');
    expect(list()).not.toBeInTheDocument();

    fireEvent.change(box, {target: {value: 'yeni alan'}});
    expect(box).toHaveValue('yeni alan');
    expect(list()).not.toBeInTheDocument();
  });

  it('adds a term at the top, checks it on the screen and saves the list with the index', async () => {
    const save = vi.spyOn(VocabularyService, 'save').mockImplementation(async (_list, items) => saved('terms', items as TermItem[]));
    await openPage();
    fireEvent.click(document.querySelector('#w-terms .tile.add') as HTMLElement);
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
    expect(document.querySelector('#w-terms .tile.term .nm')?.textContent).toBe('icare');
    expect(tab('terms', 3).querySelector('.dot')).not.toBeNull();
    expect(stat(message('vocabulary.stat.state'))).toHaveClass('st', 'warn');

    const bar = screen.getByText(message('vocabulary.pending.text')).closest('.wbar') as HTMLElement;
    fireEvent.click(within(bar).getByRole('button', {name: message('vocabulary.pending.save')}));
    expect(await screen.findByText(message('vocabulary.landed.saved', {list: message('vocabulary.list.terms')}))).toBeInTheDocument();
    expect(screen.getByText(message('vocabulary.landed.rebuilt', {count: 3, duration: '2,4 sn'}))).toBeInTheDocument();
    expect(save).toHaveBeenCalledWith('terms', [{term: 'icare', equivalents: ['a', 'b', 'c'], domain: '', note: ''}, KREDI, KAR]);
    expect(screen.queryByText(message('vocabulary.pending.text'))).toBeNull();
  });

  it('edits and removes a term from its tile, and drops the edits on "Geri al"', async () => {
    await openPage();
    fireEvent.click(termTile('kâr payı'));
    const drawer = await screen.findByRole('dialog', {name: 'kâr payı'});
    expect(within(drawer).getByText(message('vocabulary.term.sub'))).toBeInTheDocument();
    fireEvent.click(within(drawer).getByRole('button', {name: message('vocabulary.term.remove')}));
    expect(screen.queryByText('kâr payı')).toBeNull();
    const bar = screen.getByText(message('vocabulary.pending.text')).closest('.wbar') as HTMLElement;
    fireEvent.click(within(bar).getByRole('button', {name: message('vocabulary.pending.revert')}));
    expect(screen.getByText('kâr payı')).toBeInTheDocument();
  });

  it('adds, refuses and removes stopwords, adds a group and keeps the edits across admin pages', async () => {
    const save = vi
      .spyOn(VocabularyService, 'save')
      .mockRejectedValue(new ApiError(422, '“iki kelime”: durak kelime tek kelime olmalı', 'vocabulary_stopword_not_single_word'));
    await openPage();
    openStops();
    const box = screen.getByRole('textbox', {name: message('vocabulary.stops.addTo', {group: 'Genel'})});
    fireEvent.change(box, {target: {value: 'VE, ile'}});
    fireEvent.keyDown(box, {key: 'Enter'});
    expect(screen.getByRole('heading', {level: 2, name: message('vocabulary.stops.title', {count: 4})})).toBeInTheDocument();
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole('textbox', {name: message('vocabulary.stops.addTo', {group: 'Genel'})})),
    );
    fireEvent.change(document.activeElement as HTMLInputElement, {target: {value: 'veya'}});
    fireEvent.keyDown(document.activeElement as HTMLInputElement, {key: 'Enter'});
    expect(await screen.findByText(message('vocabulary.stops.already'))).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: message('vocabulary.stops.removeWord', {word: 'and'})}));
    expect(screen.queryByText(message('vocabulary.stops.ungrouped'))).toBeNull();

    const addGroup = () =>
      within(document.querySelector('.sw-new') as HTMLElement).getByRole('button', {name: message('vocabulary.stops.addGroup')});
    fireEvent.click(addGroup());
    expect(await screen.findByText(message('vocabulary.stops.groupMissing'))).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', {name: message('vocabulary.stops.newGroup')}), {target: {value: 'Dolgu'}});
    fireEvent.change(screen.getByRole('textbox', {name: message('vocabulary.stops.newWordsLabel')}), {target: {value: 'lütfen rica'}});
    fireEvent.click(addGroup());
    expect([...document.querySelectorAll('.sw-group .sw-h b')].map((node) => node.textContent)).toEqual(['Genel', 'Dolgu']);
    expect(screen.getByRole('textbox', {name: message('vocabulary.stops.newGroup')})).toHaveValue('');

    fireEvent.click(screen.getByRole('link', {name: message('admin.page.bakim.label')}));
    await screen.findByRole('heading', {level: 1, name: message('admin.page.bakim.label')});
    fireEvent.click(screen.getByRole('link', {name: message('admin.page.kelimeler.label')}));
    await screen.findByRole('heading', {level: 2, name: message('vocabulary.terms.title', {count: 2})});
    expect(openStops(5)).toBeInTheDocument();
    expect(VocabularyService.read).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByRole('button', {name: message('vocabulary.pending.save')}));
    expect(await screen.findByText('“iki kelime”: durak kelime tek kelime olmalı')).toBeInTheDocument();
    expect(save).toHaveBeenCalledWith('stopwords', expect.arrayContaining([{word: 'ile', group: 'Genel'}]));
    expect(screen.getByText(message('vocabulary.pending.text'))).toBeInTheDocument();
  });

  it('asks before leaving the admin screen with unsaved list edits', async () => {
    await openPage();
    openStops();
    fireEvent.click(screen.getByRole('button', {name: message('vocabulary.stops.removeWord', {word: 'and'})}));
    const confirm = answerConfirm(false);
    fireEvent.click(screen.getByRole('link', {name: message('admin.back')}));
    expect(confirm).toHaveBeenCalledWith(message('admin.leave.confirm'));
    expect(screen.getByTestId('where').textContent).toBe('/admin/kelimeler');
    const event = new Event('beforeunload', {cancelable: true});
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it('imports the open tab list from Excel after the confirmation and keeps the other list edits', async () => {
    const imported = vi.spyOn(VocabularyService, 'importWorkbook').mockResolvedValue(saved('terms', [KREDI, KAR], false));
    const pickers: HTMLInputElement[] = [];
    vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(function (this: HTMLInputElement) {
      pickers.push(this);
    });
    await openPage();
    openStops();
    fireEvent.click(screen.getByRole('button', {name: message('vocabulary.stops.removeWord', {word: 'and'})}));
    fireEvent.click(tab('terms', 2));
    const termsImport = screen.getByRole('button', {name: message('vocabulary.import.button')});
    expect(termsImport).toHaveAttribute('title', message('vocabulary.import.tip'));
    fireEvent.click(termsImport);
    const confirm = answerConfirm(true);
    pickFile(pickers[0], 'terimler.csv');
    expect(await screen.findByText(message('admin.excel.notExcel'))).toBeInTheDocument();
    fireEvent.click(termsImport);
    pickFile(pickers[1], 'terimler.xlsx');
    await waitFor(() => expect(confirm).toHaveBeenCalledWith(message('vocabulary.import.confirm.terms', {name: 'terimler.xlsx'})));
    expect(await screen.findByText(message('vocabulary.landed.unchanged', {count: 2}))).toBeInTheDocument();
    expect(imported).toHaveBeenCalledWith('terms', expect.objectContaining({name: 'terimler.xlsx'}));
    expect(openStops(2)).toBeInTheDocument();
  });

  it('names the dropped edits in the import confirmation', async () => {
    const pickers: HTMLInputElement[] = [];
    vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(function (this: HTMLInputElement) {
      pickers.push(this);
    });
    await openPage();
    openStops();
    fireEvent.click(screen.getByRole('button', {name: message('vocabulary.stops.removeWord', {word: 'and'})}));
    const confirm = answerConfirm(false);
    fireEvent.click(screen.getByRole('button', {name: message('vocabulary.import.button')}));
    pickFile(pickers[0], 'durak.xlsx');
    await waitFor(() => expect(confirm).toHaveBeenCalledWith(message('vocabulary.import.confirm.stopwordsDropped', {name: 'durak.xlsx'})));
  });
});
