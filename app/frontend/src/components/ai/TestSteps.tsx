import {useIntl} from '@/contexts/IntlContext';
import {formatDuration} from '@/lib/format';
import type {LlmTestStep} from '@/types/llm';

/** A connection test's steps with ✓/✗, the detail and the time (admin.html AI.steps). */
export function TestSteps({steps}: {steps: readonly LlmTestStep[]}) {
  const {t} = useIntl();
  return (
    <ul className="tests">
      {steps.map((step, index) => (
        <li key={index}>
          <span className={step.ok ? 'ok' : 'no'}>{step.ok ? t('ai.test.ok') : t('ai.test.failed')}</span>
          <b>{step.name}</b>
          <span className="d">{step.detail}</span>
          <span className="ms">{formatDuration(step.ms, t)}</span>
        </li>
      ))}
    </ul>
  );
}

