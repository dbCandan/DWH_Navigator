import {act, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {AnswerView} from '@/components/explorer/AnswerView';
import {IntlProvider} from '@/contexts/IntlContext';
import {ApiError} from '@/lib/apiClient';
import {VoteService} from '@/services/votes';
import {answer, answerObject, tally} from '@/test/explorer';
import {message} from '@/test/render';
import type {AnalysisAnswer} from '@/types/analysis';

const ANSWER_AT = '2026-10-09T08:00:12.345000+00:00';

function show(r: AnalysisAnswer, openTable = vi.fn()) {
  render(
    <IntlProvider>
      <AnswerView answer={r} onRedo={vi.fn()} onReport={vi.fn()} reportHref="/x" openTable={openTable} hasTable={() => true} />
    </IntlProvider>,
  );
  return {openTable};
}

const voted = (overrides: Partial<AnalysisAnswer> = {}): AnalysisAnswer =>
  answer({
    feedback: {answer: tally(), answer_rejected: false, mine: {}, answer_at: ANSWER_AT},
    rejected: [],
    endorsed: [],
    ...overrides,
  });

/** The vote bar under the first suggestion's card. */
function tableBar(): HTMLElement {
  fireEvent.click(document.querySelectorAll('.pick-row')[0]);
  return document.querySelector('.pick.open .res-foot .fb') as HTMLElement;
}

describe('votes in the answer (answer-feedback Requirement 11-13)', () => {
  let cast: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    cast = vi.spyOn(VoteService, 'cast').mockResolvedValue({votes: tally({up: 1}), answer_rejected: false, forgotten: 0});
  });
  afterEach(() => vi.restoreAllMocks());

  it('asks "İşinize yarar mı?" on every card with the person\'s own vote pressed', () => {
    show(voted({feedback: {answer: tally(), answer_rejected: false, mine: {'DWH.Kart.vCardLimit1': 'down'}, answer_at: ANSWER_AT}}));
    const bar = tableBar();
    expect(within(bar).getByText(message('vote.question'))).toHaveClass('fb-q');
    expect(within(bar).getByRole('button', {name: message('vote.up')})).toHaveAttribute('aria-pressed', 'false');
    expect(within(bar).getByRole('button', {name: message('vote.down')})).toHaveAttribute('aria-pressed', 'true');
  });

  it('sends a 👍 at once with the question and the answer\'s time, and thanks', async () => {
    show(voted());
    const bar = tableBar();
    await act(async () => fireEvent.click(within(bar).getByRole('button', {name: message('vote.up')})));
    expect(cast).toHaveBeenCalledWith({
      query: 'kart limit doluluk oranı',
      scope: 'table',
      table_key: 'DWH.Kart.vCardLimit1',
      vote: 'up',
      answer_at: ANSWER_AT,
    });
    expect(within(bar).getByRole('status')).toHaveTextContent(message('vote.thanks'));
    expect(within(bar).getByRole('button', {name: message('vote.up')})).toHaveAttribute('aria-pressed', 'true');
    expect(bar.querySelector('.fb-why')).toHaveClass('hidden');
  });

  it('opens the reasons after a 👎: ready reasons, a free text with Enter and "Gönder"', async () => {
    show(voted());
    const bar = tableBar();
    await act(async () => fireEvent.click(within(bar).getByRole('button', {name: message('vote.down')})));
    expect(cast).toHaveBeenLastCalledWith(expect.not.objectContaining({note: expect.anything()}));
    const why = bar.querySelector('.fb-why') as HTMLElement;
    expect(why).not.toHaveClass('hidden');
    expect(within(bar).getByRole('status')).toBeEmptyDOMElement();
    const chips = [...why.querySelectorAll('.fb-chip')].map((c) => c.textContent);
    expect(chips).toEqual(['vote.reason.topic', 'vote.reason.column', 'vote.reason.stale', 'vote.reason.partial'].map((k) => message(k)));
    const input = within(why).getByRole('textbox', {name: message('vote.noteLabel')});
    expect(document.activeElement).toBe(input);
    expect(input).toHaveAttribute('maxlength', '300');
    expect(input).toHaveAttribute('placeholder', message('vote.notePlaceholder'));
    // "Gönder" with nothing written sends nothing; Enter sends "—".
    fireEvent.click(within(why).getByRole('button', {name: message('vote.send')}));
    expect(cast).toHaveBeenCalledTimes(1);
    await act(async () => fireEvent.keyDown(input, {key: 'Enter'}));
    expect(cast).toHaveBeenLastCalledWith(expect.objectContaining({vote: 'down', note: message('vote.emptyNote')}));
    expect(within(bar).getByRole('status')).toHaveTextContent(message('vote.reasonSaved'));
    expect(why).toHaveClass('hidden');
  });

  it('sends a ready reason as a second 👎', async () => {
    show(voted());
    const bar = tableBar();
    await act(async () => fireEvent.click(within(bar).getByRole('button', {name: message('vote.down')})));
    await act(async () => fireEvent.click(within(bar).getByRole('button', {name: message('vote.reason.column')})));
    expect(cast).toHaveBeenLastCalledWith(expect.objectContaining({vote: 'down', note: message('vote.reason.column')}));
    expect(within(bar).getByRole('status')).toHaveTextContent(message('vote.reasonSaved'));
  });

  it('says when a vote could not be saved', async () => {
    cast.mockRejectedValue(new ApiError(422, 'Bu tablo artık sözlükte yok', 'vote_table_unknown'));
    show(voted());
    const bar = tableBar();
    await act(async () => fireEvent.click(within(bar).getByRole('button', {name: message('vote.up')})));
    expect(within(bar).getByRole('status')).toHaveTextContent(
      message('vote.failed', {message: message('explorer.error.vote_table_unknown')}),
    );
  });

  it('writes the badges with the counts, the reasons and the confidence before the votes', () => {
    const approved = answerObject(1, {
      score: 0.85,
      score_before: 0.8,
      level: 'Yüksek',
      votes: tally({up: 2, down: 1, support: 0.2, status: 'approved', reasons: ['Eski / kullanılmıyor']}),
    });
    const doubted = answerObject(2, {votes: tally({down: 1, support: -0.33, status: 'doubted'})});
    const disputed = answerObject(3, {key: 'DWH.Kart.vCardLimit3', votes: tally({up: 1, down: 1, status: 'disputed'})});
    const promoted = answerObject(4, {key: 'DWH.Kart.vCardLimit4', promoted: true, votes: tally({up: 1, status: 'approved'})});
    show(voted({objects: [approved, doubted, disputed, promoted]}));
    const badges = [...document.querySelectorAll('.pick-body .vb')];
    expect(badges.map((b) => [b.className, b.textContent])).toEqual([
      ['vb up', message('vote.badge.approved', {count: 2})],
      ['vb warn', message('vote.badge.doubted', {count: 1})],
      ['vb mix', message('vote.badge.disputed', {up: 1, down: 1})],
      ['vb up', message('vote.badge.promoted')],
    ]);
    expect(badges[0].getAttribute('title')).toBe(
      message('vote.badge.tip', {up: 2, down: 1}) +
        '\n' +
        message('vote.badge.reasons', {reasons: 'Eski / kullanılmıyor'}) +
        '\n' +
        message('vote.badge.moved', {before: 80, after: 85}),
    );
    expect(badges[3]).toHaveAttribute('title', message('vote.badge.promotedTip'));
    // Marks: in the rows (↑ ✓ !) and in the head ("Kullanıcılar doğruladı").
    const marks = [...document.querySelectorAll('.pk-name .pk-mark')].map((m) => [m.textContent, m.getAttribute('title')]);
    expect(marks).toEqual([
      ['✓', message('vote.mark.approved', {count: 2})],
      ['!', message('vote.mark.rejected', {count: 1})],
      ['↑', message('vote.mark.promoted')],
    ]);
    expect(document.querySelector('.ab-name .ov-ok')).toHaveAttribute('title', message('vote.mark.usersApproved'));
    expect(document.querySelectorAll('.aa-name .ov-ok')).toHaveLength(1);
    const ring = document.querySelector('.ans-best .ring') as HTMLElement;
    expect(ring).toHaveAttribute('title', message('answer.ringTip', {score: 85}) + message('vote.ringBefore', {before: 80}));
    expect(document.querySelector('.pick-row')).toHaveAttribute(
      'title',
      message('answer.pickTip', {key: approved.key, score: 85, level: 'Yüksek'}) + message('vote.pickBefore', {before: 80}),
    );
  });

  it('lists the tables people approved apart and opens their columns', () => {
    const {openTable} = show(
      voted({endorsed: [{key: 'DWH.Musteri.vCustomerInfo', name: 'vCustomerInfo', schema: 'DWH.Musteri', votes: tally({up: 3, status: 'approved'})}]}),
    );
    const crowd = document.querySelector('section.guide.crowd') as HTMLElement;
    expect(within(crowd).getByText(message('vote.endorsed'))).toHaveClass('label');
    const item = crowd.querySelector('button.crowd-item') as HTMLElement;
    expect(item).toHaveTextContent('vCustomerInfoDWH.Musteri');
    expect(item).toHaveAttribute('title', message('vote.endorsedTip'));
    expect(within(item).getByText(message('vote.endorsedCount', {count: 3}))).toHaveClass('vb', 'up');
    fireEvent.click(item);
    expect(openTable).toHaveBeenCalledWith('DWH.Musteri.vCustomerInfo');
  });

  it('shows the rejected tables folded, faded and with their own votes; the answer vote stays', () => {
    const rejected = answerObject(9, {
      key: 'DWH.Kart.vEski',
      name: 'vEski',
      votes: tally({down: 2, support: -0.5, status: 'rejected', reasons: ['Konu farklı']}),
    });
    show(voted({objects: [], rejected: [rejected]}));
    const fold = [...document.querySelectorAll('details.ask-more')].find((d) =>
      d.textContent?.includes(message('vote.rejected', {count: 1})),
    ) as HTMLDetailsElement;
    expect(fold.open).toBe(false);
    expect(within(fold).getByText(message('vote.rejectedNote'))).toHaveClass('faint');
    const card = fold.querySelector('article.pick.dim') as HTMLElement;
    expect(card.querySelector('.pk-n')).toHaveTextContent('·');
    expect(card.querySelector('.vb.down')).toHaveTextContent(message('vote.badge.rejected', {count: 2}));
    expect(card.querySelector('.fb')).not.toBeNull();
    expect(screen.getByText(message('vote.answer.title'))).toBeInTheDocument();
  });

  it('asks about the whole answer only when it suggests or rejects tables', () => {
    show(voted({objects: [], rejected: [], verdict: 'BULUNAMADI'}));
    expect(screen.queryByText(message('vote.answer.title'))).toBeNull();
  });

  it('does not ask about an answer the analyst could not write', () => {
    show(voted({objects: [], analyst: false, fallback: 'Model sunucusuna ulaşılamadı', verdict: 'BULUNAMADI'}));
    expect(screen.queryByText(message('vote.answer.title'))).toBeNull();
  });

  it('counts the answer\'s votes and says what a vote did', async () => {
    show(voted({feedback: {answer: tally({up: 1, down: 2}), answer_rejected: false, mine: {'': 'up'}, answer_at: ANSWER_AT}}));
    const section = document.querySelector('section.answer-fb') as HTMLElement;
    expect(within(section).getByText(message('vote.answer.past', {count: 3, up: 1, down: 2}))).toHaveClass('faint');
    expect(within(section).getByRole('button', {name: message('vote.up')})).toHaveAttribute('aria-pressed', 'true');
    expect(section.querySelector('.fb-q')).toBeEmptyDOMElement();
    await act(async () => fireEvent.click(within(section).getByRole('button', {name: message('vote.down')})));
    expect(cast).toHaveBeenLastCalledWith({query: 'kart limit doluluk oranı', scope: 'answer', vote: 'down', answer_at: ANSWER_AT});
    expect(section.querySelector('.fb-after')).toHaveTextContent(message('vote.answer.noted'));
    cast.mockResolvedValue({votes: tally(), answer_rejected: true, forgotten: 1});
    await act(async () => fireEvent.click(within(section).getByRole('button', {name: message('vote.reason.partial')})));
    expect(section.querySelector('.fb-after')).toHaveTextContent(message('vote.answer.forgotten'));
  });

  it('warns on a kept answer people found lacking', () => {
    show(
      voted({
        reused: {at: '09.10.2026 08:00', query: 'kart limit doluluk oranı', match: 'aynı soru'},
        feedback: {answer: tally({down: 2}), answer_rejected: true, mine: {}, answer_at: ANSWER_AT},
      }),
    );
    expect(screen.getByText(message('vote.keptRejected'))).toHaveClass('answer-fallback');
  });

  it('keeps nothing in the browser', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    show(voted());
    const bar = tableBar();
    await act(async () => fireEvent.click(within(bar).getByRole('button', {name: message('vote.up')})));
    expect(setItem).not.toHaveBeenCalled();
  });

  it('leaves an answer without votes as it was', () => {
    show(answer());
    expect(document.querySelector('.pick-body .vb')).toBeNull();
    expect(document.querySelector('.pk-mark')).toBeNull();
    expect(document.querySelector('section.crowd')).toBeNull();
  });
});
