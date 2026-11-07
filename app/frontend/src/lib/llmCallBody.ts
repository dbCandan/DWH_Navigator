/** What the LLM log page shows of a logged body: the messages and the reply, and the raw JSON. */

export interface ChatMessage {
  role: string;
  content: string;
}

function parsed(body: string): unknown {
  try {
    return JSON.parse(body) as unknown;
  } catch {
    return null;
  }
}

/** JSON indented for reading; a body that is not JSON (cut, or an error page) stays as it is. */
export function prettyJson(body: string): string {
  const value = parsed(body);
  return value === null ? body : JSON.stringify(value, null, 2);
}

/** The chat messages of a request body; empty when the body cannot be read. */
export function requestMessages(body: string): ChatMessage[] {
  const messages = (parsed(body) as {messages?: unknown} | null)?.messages;
  if (!Array.isArray(messages)) return [];
  return messages.flatMap((item: {role?: unknown; content?: unknown}) =>
    typeof item?.content === 'string' ? [{role: String(item.role ?? ''), content: item.content}] : [],
  );
}

/** The model's text in a response body, indented when it is JSON; null when there is none. */
export function replyText(body: string): string | null {
  const choices = (parsed(body) as {choices?: unknown} | null)?.choices;
  if (!Array.isArray(choices)) return null;
  const content = (choices[0] as {message?: {content?: unknown}} | undefined)?.message?.content;
  return typeof content === 'string' ? prettyJson(content) : null;
}
