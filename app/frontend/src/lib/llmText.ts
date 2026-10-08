import {ApiError, isUnreachable} from '@/lib/apiClient';
import type {LlmTestStep} from '@/types/llm';

type Translate = (key: string, values?: Record<string, string | number>) => string;

/**
 * The text of a failed AI page request, where the source showed its error message. The
 * llm-connection codes carry the PRD's fixed Turkish texts (Requirement 2-4, 21), which never
 * echo a key or a server's answer, so they are shown as the server words them; an unreachable
 * server reads "Sunucuya ulaşılamadı" and anything else "Beklenmeyen yanıt (HTTP n)", as the
 * source's request helper wrote them.
 */
export function llmErrorText(error: unknown, t: Translate): string {
  if (isUnreachable(error)) return t('admin.unreachable.title');
  if (error instanceof ApiError) {
    if (error.code?.startsWith('llm_')) return error.message;
    return t('ai.error.unexpected', {status: error.status});
  }
  return t('ai.error.unexpectedPlain');
}

/** True when another integration holds the chat role (409; Requirement 4). */
export function isRoleTaken(error: unknown): error is ApiError {
  return error instanceof ApiError && error.code === 'llm_chat_role_taken';
}

/** A test result as notice lines: "✓ Sunucu: …" (admin.html AI.test). */
export function stepLines(steps: readonly LlmTestStep[], t: Translate): string[] {
  return steps.map((step) => t(step.ok ? 'ai.test.lineOk' : 'ai.test.lineFailed', {name: step.name, detail: step.detail}));
}
