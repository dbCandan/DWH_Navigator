import {cleanup, fireEvent, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from '@/lib/apiClient';
import {TOUR_QUESTION, tourPace} from '@/lib/tourSample';
import {forgetWelcomeForTests, shouldShowWelcome} from '@/lib/welcomeGuide';
import {AuthService} from '@/services/auth';
import {VoteService} from '@/services/votes';
import {message, renderApp} from '@/test/render';

/** A visitor without a session opens the main screen, as an analyst does. */
async function openAsVisitor() {
  vi.spyOn(AuthService, 'refresh').mockRejectedValue(new ApiError(401, 'x', 'session_expired', true));
  renderApp('/');
  await screen.findByRole('heading', {level: 1, name: message('explorer.hero.title')});
}

const tour = () => screen.queryByRole('dialog', {name: /./});
const title = () => document.getElementById('wt-title');
const press = (name: string) => fireEvent.click(screen.getByRole('button', {name}));
const waitForStep = (key: string) => waitFor(() => expect(title()).toHaveTextContent(message(`welcome.${key}.title`)));

describe('welcome tour: once per browser', () => {
  const pace = {...tourPace};
  beforeEach(() => {
    forgetWelcomeForTests();
    tourPace.typeMs = 1;
    tourPace.stageMs = 1;
  });
  afterEach(() => {
    Object.assign(tourPace, pace);
    vi.restoreAllMocks();
    document.documentElement.className = '';
  });

  it('opens on the first visit and counts as seen the moment it opens', async () => {
    await openAsVisitor();
    expect(await screen.findByRole('dialog', {name: message('welcome.intro.title')})).toBeInTheDocument();
    expect(localStorage.getItem('dwhnavigator.welcome')).toBe('1');
    expect(document.documentElement).toHaveClass('welcome-open');
  });

  it('never opens again for the same browser, even after a reload', async () => {
    await openAsVisitor();
    await screen.findByRole('dialog');
    cleanup();
    forgetWelcomeForTests({keepStorage: true});

    await openAsVisitor();
    expect(tour()).toBeNull();
    expect(shouldShowWelcome()).toBe(false);
  });

  it('stays away after being left half way, even when the page is opened again', async () => {
    await openAsVisitor();
    await screen.findByRole('dialog');
    press(message('welcome.start'));
    fireEvent.keyDown(document, {key: 'Escape'});
    expect(tour()).toBeNull();
    cleanup();
    forgetWelcomeForTests({keepStorage: true});

    await openAsVisitor();
    expect(tour()).toBeNull();
  });

  it('can be put off from the opening card', async () => {
    await openAsVisitor();
    await screen.findByRole('dialog');
    press(message('welcome.later'));
    expect(tour()).toBeNull();
    expect(localStorage.getItem('dwhnavigator.welcome')).toBe('1');
  });

  it('lets the visitor ask, read, open a table and vote on the sample, sending nothing', async () => {
    const cast = vi.spyOn(VoteService, 'cast');
    await openAsVisitor();
    await screen.findByRole('dialog');
    press(message('welcome.start'));

    // Ask: the sample question types itself; "Ara" is the visitor's to press.
    await waitForStep('ask');
    const sample = document.querySelector<HTMLTextAreaElement>('.wt-ask textarea');
    await waitFor(() => expect(sample).toHaveValue(TOUR_QUESTION));
    expect(sample).not.toHaveAttribute('id');
    expect(screen.queryByRole('button', {name: message('welcome.next')})).toBeNull();
    fireEvent.click(document.querySelector<HTMLButtonElement>('.wt-ask .primary')!);

    // The sample analysis runs, then the answer arrives on its own.
    await waitForStep('verdict');
    expect(document.querySelector('.wt-out .ans')).not.toBeNull();
    press(message('welcome.next'));
    await waitForStep('brief');
    press(message('welcome.next'));

    // The visitor opens the first suggestion.
    await waitForStep('best');
    expect(screen.queryByRole('button', {name: message('welcome.next')})).toBeNull();
    fireEvent.click(document.querySelector<HTMLElement>('.ans-main .pick-list .pick-row')!);
    // ...and reads one of its columns.
    await waitForStep('detail');
    expect(screen.queryByRole('button', {name: message('welcome.next')})).toBeNull();
    fireEvent.click(document.querySelector<HTMLElement>('.ans-main .pick.open .col')!);
    await screen.findByText(message('welcome.detail.thanks'));
    press(message('welcome.next'));
    await waitForStep('side');
    press(message('welcome.next'));

    // The vote stays in the page.
    await waitForStep('vote');
    const bar = document.querySelector<HTMLElement>('.ans-main .pick.open .fb')!;
    fireEvent.click(within(bar).getByRole('button', {name: message('vote.up')}));
    await screen.findByText(message('welcome.vote.thanks'));
    expect(cast).not.toHaveBeenCalled();
    press(message('welcome.next'));

    await waitForStep('report');
    press(message('welcome.next'));
    await waitForStep('done');
    press(message('welcome.finish'));
    expect(tour()).toBeNull();
    expect(document.documentElement).not.toHaveClass('welcome-open');
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole('textbox', {name: message('explorer.search.label')})),
    );
  });

  it('stays away when the browser storage is closed, rather than opening on every load', async () => {
    const blocked = () => {
      throw new DOMException('blocked', 'SecurityError');
    };
    vi.stubGlobal('localStorage', {getItem: blocked, setItem: blocked, removeItem: blocked});
    try {
      await openAsVisitor();
      expect(tour()).toBeNull();
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
