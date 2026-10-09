import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from './apiClient';
import {clearAuth, writeSession} from './authStorage';
import {followEventStream, readEventStream, type StreamEvent} from './eventStream';
import type {AuthenticatedUser} from '@/types/auth';

const encoder = new TextEncoder();

function body(...chunks: string[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>): Promise<StreamEvent[]> {
  const events: StreamEvent[] = [];
  for await (const event of readEventStream(stream)) events.push(event);
  return events;
}

const stream = (...chunks: string[]) =>
  new Response(body(...chunks), {status: 200, headers: {'Content-Type': 'text/event-stream'}});

describe('event stream reader', () => {
  it('reads ids, names and data across chunk boundaries and line endings', async () => {
    const events = await collect(
      body('id: 3\nda', 'ta: {"type":"snapshot"}\n\n', ': canlı\r\n\r\n', 'id: 4\r\nevent: step\r\ndata: a\r\ndata: b\r\r', 'data: tail'),
    );
    expect(events).toEqual([
      {id: '3', event: 'message', data: '{"type":"snapshot"}'},
      {id: '4', event: 'step', data: 'a\nb'},
    ]);
  });

  it('keeps a multi-byte character split between chunks', async () => {
    const bytes = encoder.encode('data: işlem\n\n');
    const split = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, 8));
        controller.enqueue(bytes.slice(8));
        controller.close();
      },
    });
    expect((await collect(split))[0].data).toBe('işlem');
  });
});

describe('following a live stream (question-analysis Requirement 10 and 20)', () => {
  beforeEach(() => writeSession('token', {username: 'u', tenant_id: 't'} as AuthenticatedUser));
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
  });

  it('reconnects with the last event id after 1, 2, 4 … seconds, at most 30, until the last event', async () => {
    const waits: number[] = [];
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(stream('id: 1\ndata: {"type":"snapshot"}\n\n', 'id: 2\ndata: {"type":"started"}\n\n'))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(new Response('', {status: 502}))
      .mockResolvedValueOnce(stream('id: 3\ndata: {"type":"completed"}\n\n'));
    const seen: string[] = [];
    const outcome = await followEventStream('/analyses/a1/events', {
      onEvent: (event) => {
        seen.push(event.data);
        return (JSON.parse(event.data) as {type: string}).type === 'completed';
      },
      wait: async (ms) => {
        waits.push(ms);
      },
    });
    expect(outcome).toBe('completed');
    expect(seen).toHaveLength(3);
    expect(waits).toEqual([1000, 2000, 4000]);
    const headers = fetchMock.mock.calls.map(([, init]) => new Headers(init?.headers));
    expect(headers[0].get('Last-Event-ID')).toBeNull();
    expect(headers[1].get('Last-Event-ID')).toBe('2');
    expect(headers[3].get('Last-Event-ID')).toBe('2');
    for (const header of headers) {
      expect(header.get('Authorization')).toBe('Bearer token');
      expect(header.get('Accept')).toBe('text/event-stream');
    }
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/dwhnavigator/v1/analyses/a1/events');
  });

  it('caps the delay at 30 seconds', async () => {
    const waits: number[] = [];
    const controller = new AbortController();
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
    await followEventStream('/analyses/a1/events', {
      onEvent: () => false,
      signal: controller.signal,
      wait: async (ms) => {
        waits.push(ms);
        if (waits.length === 7) controller.abort();
      },
    });
    expect(waits).toEqual([1000, 2000, 4000, 8000, 16000, 30000, 30000]);
  });

  it('stops on an answer a retry cannot fix', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({detail: {code: 'analysis_not_found', message: 'Analiz bulunamadı.'}}), {status: 404}),
    );
    await expect(followEventStream('/analyses/x/events', {onEvent: () => false, wait: async () => undefined})).rejects.toEqual(
      expect.objectContaining({status: 404, code: 'analysis_not_found'}),
    );
  });

  it('stops quietly when aborted', async () => {
    const controller = new AbortController();
    controller.abort();
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    await expect(followEventStream('/analyses/x/events', {onEvent: () => false, signal: controller.signal})).resolves.toBe(
      'aborted',
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('ends with the session when the token cannot be renewed', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('{}', {status: 401, headers: {'WWW-Authenticate': 'Bearer'}}))
      .mockResolvedValueOnce(new Response('{}', {status: 401}));
    const failure = await followEventStream('/analyses/x/events', {onEvent: () => false, wait: async () => undefined}).catch(
      (error: unknown) => error,
    );
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({sessionExpired: true});
  });
});
