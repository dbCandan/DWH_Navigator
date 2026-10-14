import {ApiError, apiFetch, visitorFetch} from '@/lib/apiClient';

/** One server-sent event: its `id:` (when it carried one), `event:` name and joined `data:`. */
export interface StreamEvent {
  id: string | null;
  event: string;
  data: string;
}

/**
 * Minimal `text/event-stream` reader for a `fetch` response body. `EventSource` cannot send the
 * `Authorization` header, so live streams are read from `fetch` instead (user-accounts
 * Requirement 12).
 *
 * Comment lines such as the `: canlı` keep-alive and `retry:` fields are ignored. CRLF, CR and LF
 * line endings and chunk boundaries anywhere (inside a line or a multi-byte character) are
 * handled. A trailing event without its closing blank line is dropped, as a browser does.
 */
export async function* readEventStream(body: ReadableStream<Uint8Array>): AsyncGenerator<StreamEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let data: string[] = [];
  let id: string | null = null;
  let event = '';
  let pendingCarriageReturn = false;
  let finished = false;
  try {
    for (;;) {
      const {value, done} = await reader.read();
      if (done) {
        finished = true;
        return;
      }
      let text = decoder.decode(value, {stream: true});
      if (pendingCarriageReturn && text.startsWith('\n')) text = text.slice(1);
      pendingCarriageReturn = text.endsWith('\r');
      buffer += text;
      const lines = buffer.split(/\r\n|\r|\n/);
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        if (line === '') {
          if (data.length > 0) yield {id, event: event || 'message', data: data.join('\n')};
          data = [];
          id = null;
          event = '';
          continue;
        }
        if (line.startsWith(':')) continue;
        const colon = line.indexOf(':');
        const field = colon === -1 ? line : line.slice(0, colon);
        let content = colon === -1 ? '' : line.slice(colon + 1);
        if (content.startsWith(' ')) content = content.slice(1);
        if (field === 'data') data.push(content);
        else if (field === 'id' && !content.includes('\0')) id = content;
        else if (field === 'event') event = content;
      }
    }
  } finally {
    // The consumer stopped early or the read failed: stop the body so the connection closes.
    if (!finished) await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

export interface FollowOptions {
  /** Called for every event; return `true` for the stream's last (terminal) event. */
  onEvent: (event: StreamEvent) => boolean | void;
  signal?: AbortSignal;
  /** First reconnection delay; it doubles after every failed attempt. */
  initialDelayMs?: number;
  /** Longest reconnection delay. */
  maxDelayMs?: number;
  /** Waits between attempts; tests replace it. */
  wait?: (ms: number, signal?: AbortSignal) => Promise<void>;
  /** A main-screen stream: opened as the visitor of the device id (003-anonymous-visitor). */
  visitor?: boolean;
}

export type FollowOutcome = 'completed' | 'aborted';

function defaultWait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(timer);
        resolve();
      },
      {once: true},
    );
  });
}

/** A lost connection or a passing server failure: worth another attempt. */
function retryable(error: unknown): boolean {
  if (error instanceof ApiError) return !error.sessionExpired && (error.status >= 500 || error.status === 0);
  return error instanceof TypeError || (error instanceof DOMException && error.name !== 'AbortError');
}

/**
 * Follow a live event stream until its terminal event or until `signal` aborts.
 *
 * The stream opens with `GET` through the shared client, so the access token travels in the
 * `Authorization` header and an expired token is renewed silently before the request is repeated;
 * the server closes a stream when the token that opened it expires (user-accounts Requirement 12).
 * When the connection ends or drops before the terminal event, the stream is reopened after 1, 2,
 * 4 … at most 30 seconds with the id of the last event received in `Last-Event-ID`
 * (question-analysis Requirement 10 and 20); a connection that delivered events resets the delay.
 * An error answer that a retry cannot fix (401 after a failed renewal, 403, 404, 429) rejects with
 * that `ApiError`.
 */
export async function followEventStream(path: string, options: FollowOptions): Promise<FollowOutcome> {
  const {onEvent, signal} = options;
  const initial = options.initialDelayMs ?? 1000;
  const longest = options.maxDelayMs ?? 30000;
  const wait = options.wait ?? defaultWait;
  let lastEventId: string | null = null;
  let delay = initial;
  while (!signal?.aborted) {
    let received = false;
    try {
      const headers: Record<string, string> = {Accept: 'text/event-stream'};
      if (lastEventId !== null) headers['Last-Event-ID'] = lastEventId;
      const fetcher = options.visitor ? visitorFetch : apiFetch;
      const response = await fetcher(path, {headers, signal, cache: 'no-store'});
      if (response.body === null) throw new TypeError('empty event stream');
      for await (const event of readEventStream(response.body)) {
        received = true;
        if (event.id !== null) lastEventId = event.id;
        if (onEvent(event) === true) return 'completed';
      }
    } catch (error) {
      if (signal?.aborted) break;
      if (!retryable(error)) throw error;
    }
    if (received) delay = initial;
    await wait(delay, signal);
    delay = Math.min(longest, delay * 2);
  }
  return 'aborted';
}
