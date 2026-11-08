import {useEffect, useId, useRef, useState, type KeyboardEvent} from 'react';
import {createPortal} from 'react-dom';
import {useIntl} from '@/contexts/IntlContext';
import {provideConfirmDialog, type ConfirmOptions} from '@/lib/confirm';
import {trapTab} from '@/lib/focusTrap';

interface Ask {
  text: string;
  options: ConfirmOptions;
  answer: (yes: boolean) => void;
}

/**
 * The admin screens' confirmation dialog, in place of the browser's: the question as its title,
 * the explanation below, and the step's own verb on its button ("Sil", "Pasifleştir"). A
 * deleting step has a red button and starts on "Vazgeç"; Esc or a click outside says no.
 */
export function ConfirmHost() {
  const {t} = useIntl();
  const [asks, setAsks] = useState<Ask[]>([]);
  const box = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const bodyId = useId();

  useEffect(
    () =>
      provideConfirmDialog(
        (text, options) => new Promise<boolean>((answer) => setAsks((queue) => [...queue, {text, options, answer}])),
      ),
    [],
  );

  const ask = asks[0];

  useEffect(() => {
    if (!ask) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    box.current?.querySelector<HTMLElement>(ask.options.danger ? '.no' : '.yes')?.focus({preventScroll: true});
    return () => {
      if (opener?.isConnected) opener.focus({preventScroll: true});
    };
  }, [ask]);

  if (!ask) return null;

  const [question, ...rest] = ask.text.split('\n');
  const body = rest.join('\n').trim();
  const reply = (yes: boolean) => {
    ask.answer(yes);
    setAsks((queue) => queue.slice(1));
  };
  const keyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      reply(false);
      return;
    }
    trapTab(event, box.current);
  };

  return createPortal(
    <div
      className="confirm"
      onClick={(event) => {
        if (event.target === event.currentTarget) reply(false);
      }}
    >
      <div
        className={'confirm-box' + (ask.options.danger ? ' danger' : '')}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={body ? bodyId : undefined}
        ref={box}
        onKeyDown={keyDown}
      >
        <h2 id={titleId}>{question}</h2>
        {body ? <p id={bodyId}>{body}</p> : null}
        <div className="confirm-f">
          <button className="btn no" type="button" onClick={() => reply(false)}>
            {ask.options.cancel ?? t('admin.confirm.cancel')}
          </button>
          <button className={'btn yes ' + (ask.options.danger ? 'danger solid' : 'primary')} type="button" onClick={() => reply(true)}>
            {ask.options.action ?? t('admin.confirm.ok')}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
