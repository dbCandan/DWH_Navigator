/** The reasoning modes an integration's chat model accepts; '' sends none (the model's default). */
export const EFFORTS = [
  ['none', 'ai.editor.effort.none'],
  ['low', 'ai.editor.effort.low'],
  ['medium', 'ai.editor.effort.medium'],
  ['high', 'ai.editor.effort.high'],
  ['', 'ai.editor.effort.omit'],
] as const;

/** The generation role's reasoning: 'inherit' uses the chat model's own setting. */
export const GENERATION_EFFORTS = [['inherit', 'ai.editor.effort.inherit'], ...EFFORTS] as const;

/** The message key that names a reasoning mode; an unknown value is shown as it is. */
export function effortKey(value: string): string | null {
  return GENERATION_EFFORTS.find(([known]) => known === value)?.[1] ?? null;
}

interface RoleValues {
  chat_model: string;
  reasoning_effort: string;
  generation_model: string;
  generation_reasoning_effort: string;
}

/**
 * The model and reasoning the dictionary update calls with: the generation model, or the chat
 * model when none is set; the generation reasoning, or the chat model's when it inherits.
 */
export function generationRole(values: RoleValues): {chat_model: string; reasoning_effort: string} {
  return {
    chat_model: values.generation_model.trim() || values.chat_model.trim(),
    reasoning_effort:
      values.generation_reasoning_effort === 'inherit' ? values.reasoning_effort : values.generation_reasoning_effort,
  };
}
