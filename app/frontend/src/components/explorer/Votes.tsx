import {useEffect, useRef, useState} from 'react';
import {useIntl} from '@/contexts/IntlContext';
import {movedBefore, pct} from '@/lib/answerText';
import {explorerErrorText} from '@/lib/explorerErrors';
import type {AnswerObject} from '@/types/analysis';
import type {Tally, VoteRecorded, VoteValue} from '@/types/feedback';

/*
 * The vote elements of the answer view (answer-feedback Requirement 11-13; index.html voteBar,
 * voteBadge, ring, resultCard, foundBlock, answerVote): the source's elements, class names and
 * texts. Votes are tied to the signed-in person on the server; nothing is kept in the browser.
 */

type Translate = (key: string, values?: Record<string, string | number>) => string;

/** Sends one vote: a 👎's reason travels as its note. */
export type SendVote = (vote: VoteValue, note: string) => Promise<VoteRecorded>;

/** The ready reasons of a 👎 (index.html REASONS). */
const REASON_KEYS = ['vote.reason.topic', 'vote.reason.column', 'vote.reason.stale', 'vote.reason.partial'] as const;

/** What earlier votes say about a table, in a few words; the reasons go in the tooltip. */
export function VoteBadge({m}: {m: AnswerObject}) {
  const {t} = useIntl();
  if (m.promoted)
    return (
      <span className="vb up" title={t('vote.badge.promotedTip')}>
        {t('vote.badge.promoted')}
      </span>
    );
  const v = m.votes;
  if (!v || !(v.up || v.down)) return null;
  const before = movedBefore(m);
  const title =
    t('vote.badge.tip', {up: v.up, down: v.down}) +
    (v.reasons.length ? '\n' + t('vote.badge.reasons', {reasons: v.reasons.join(' · ')}) : '') +
    (before !== null ? '\n' + t('vote.badge.moved', {before, after: pct(m.score)}) : '');
  const [cls, text] = badgeOf(v, t);
  return (
    <span className={'vb ' + cls} title={title}>
      {text}
    </span>
  );
}

function badgeOf(v: Tally, t: Translate): [string, string] {
  switch (v.status) {
    case 'approved':
      return ['up', t('vote.badge.approved', {count: v.up})];
    case 'rejected':
      return ['down', t('vote.badge.rejected', {count: v.down})];
    case 'doubted':
      return ['warn', t('vote.badge.doubted', {count: v.down})];
    case 'disputed':
      return ['mix', t('vote.badge.disputed', {up: v.up, down: v.down})];
    default:
      return ['mix', t('vote.badge.counts', {up: v.up, down: v.down})];
  }
}

/** The mark after a suggestion's name in its row: ↑ added by approval, ✓ approved, ! rejected or doubted. */
export function PickMark({m}: {m: AnswerObject}) {
  const {t} = useIntl();
  const v = m.votes;
  if (m.promoted)
    return (
      <i className="pk-mark up" title={t('vote.mark.promoted')}>
        ↑
      </i>
    );
  if (v && v.status === 'approved')
    return (
      <i className="pk-mark up" title={t('vote.mark.approved', {count: v.up})}>
        ✓
      </i>
    );
  if (v && (v.status === 'rejected' || v.status === 'doubted'))
    return (
      <i className="pk-mark down" title={t('vote.mark.rejected', {count: v.down})}>
        !
      </i>
    );
  return null;
}

/** The "En iyi eşleşme" and ranking rows' mark: ✓ approved, ↑ added by approval. */
export function ApprovedMark({m}: {m: AnswerObject}) {
  const {t} = useIntl();
  if (m.votes && m.votes.status === 'approved')
    return (
      <i className="ov-ok" title={t('vote.mark.usersApproved')}>
        ✓
      </i>
    );
  if (m.promoted)
    return (
      <i className="ov-ok" title={t('vote.mark.promoted')}>
        ↑
      </i>
    );
  return null;
}

interface VoteBarProps {
  /** "İşinize yarar mı?" on a table; empty on the whole answer. */
  label: string;
  /** The person's own last vote in this question. */
  mine: VoteValue | '';
  send: SendVote;
  onSent?: (result: VoteRecorded, vote: VoteValue) => void;
}

/** "İşinize yarar mı?": a vote is sent at once; a 👎 then offers a reason (optional). */
export function VoteBar({label, mine, send, onSent}: VoteBarProps) {
  const {t} = useIntl();
  const [pressed, setPressed] = useState<VoteValue | ''>(mine);
  const [message, setMessage] = useState('');
  const [asking, setAsking] = useState(false);
  const [note, setNote] = useState('');
  const [focusAt, setFocusAt] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (focusAt) input.current?.focus();
  }, [focusAt]);

  async function cast(vote: VoteValue, reason = '') {
    setPressed(vote);
    try {
      const result = await send(vote, reason);
      setMessage(reason ? t('vote.reasonSaved') : vote === 'up' ? t('vote.thanks') : '');
      onSent?.(result, vote);
    } catch (error) {
      setMessage(t('vote.failed', {message: explorerErrorText(error, t)}));
    }
    const ask = vote === 'down' && !reason;
    setAsking(ask);
    if (ask) setFocusAt((n) => n + 1);
  }

  return (
    <div className="fb">
      <span className="fb-q">{label}</span>
      <button className="fb-btn up" type="button" aria-pressed={pressed === 'up'} onClick={() => void cast('up')}>
        {t('vote.up')}
      </button>
      <button className="fb-btn down" type="button" aria-pressed={pressed === 'down'} onClick={() => void cast('down')}>
        {t('vote.down')}
      </button>
      <span className="fb-msg" role="status">
        {message}
      </span>
      <div className={'fb-why' + (asking ? '' : ' hidden')}>
        {REASON_KEYS.map((key) => (
          <button key={key} className="fb-chip" type="button" onClick={() => void cast('down', t(key))}>
            {t(key)}
          </button>
        ))}
        <span className="fb-note">
          <input
            type="text"
            ref={input}
            maxLength={300}
            placeholder={t('vote.notePlaceholder')}
            aria-label={t('vote.noteLabel')}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                void cast('down', note.trim() || t('vote.emptyNote'));
              }
            }}
          />
          <button
            className="fb-send"
            type="button"
            onClick={() => {
              if (note.trim()) void cast('down', note.trim());
            }}
          >
            {t('vote.send')}
          </button>
        </span>
      </div>
    </div>
  );
}

interface AnswerVoteProps {
  answer: Tally | null;
  mine: VoteValue | '';
  send: SendVote;
}

/** "Bu cevap işinize yaradı mı?": enough 👎 retire a kept answer (Requirement 10, 13). */
export function AnswerVote({answer, mine, send}: AnswerVoteProps) {
  const {t} = useIntl();
  const [after, setAfter] = useState('');
  const a = answer ?? {up: 0, down: 0};
  return (
    <section className="answer-fb">
      <div>
        <b>{t('vote.answer.title')}</b>
        {a.up + a.down ? (
          <div className="faint">{t('vote.answer.past', {count: a.up + a.down, up: a.up, down: a.down})}</div>
        ) : null}
      </div>
      <VoteBar
        label=""
        mine={mine}
        send={send}
        onSent={(result, vote) =>
          setAfter(result.forgotten ? t('vote.answer.forgotten') : vote === 'down' ? t('vote.answer.noted') : '')
        }
      />
      <div className="fb-after" role="status">
        {after}
      </div>
    </section>
  );
}
