import {useCallback, useEffect, useRef, useState} from 'react';
import {useIntl} from '@/contexts/IntlContext';
import {askCodeText, askErrorText} from '@/lib/analysisErrors';
import type {CosmosEngine} from '@/lib/cosmos/engine';
import {forgetTabAnalysis, rememberTabAnalysis} from '@/lib/tabAnalysis';
import {AnalysisService} from '@/services/analyses';
import type {AnalysisAnswer, AnalysisJob, AnalysisStreamEvent, ServiceStatus} from '@/types/analysis';

/** How a question ended on the page. */
export type AskOutcome =
  | {kind: 'answer'; answer: AnalysisAnswer; analysisId: string}
  | {kind: 'stopped'}
  | {kind: 'failed'; message: string}
  | {kind: 'interrupted'};

type Terminal =
  | {type: 'completed'}
  | {type: 'failed'; code: string}
  | {type: 'cancelled'}
  | {type: 'interrupted'};

interface Job {
  ctrl: AbortController;
  stopped: boolean;
  /** Known once the start request answered (or from the tab's remembered job). */
  id: string | null;
  /** The start request while it is on its way. */
  start: Promise<AnalysisJob> | null;
}

interface Options {
  /** The map, when it is drawn: the voyage shows the progress (Requirement 20). */
  engine: () => CosmosEngine | null;
  /** The latest `GET /status` answer: the voyage reads only when a model is bound. */
  status: () => ServiceStatus | null;
  /** An answer the analyst did not write: read the status again (Requirement 22). */
  onUnavailable: () => void;
}

const TERMINAL = new Set(['completed', 'failed', 'cancelled', 'interrupted']);

class Stopped extends Error {}

/** Resolve after `ms` or as soon as the signal aborts ("Durdur" also ends the radar's wait). */
function radarWait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (ms <= 0 || signal.aborted) return resolve();
    const timer = window.setTimeout(resolve, ms);
    signal.addEventListener(
      'abort',
      () => {
        window.clearTimeout(timer);
        resolve();
      },
      {once: true},
    );
  });
}

/** The start answer, unless the person stops first. */
function untilStopped<T>(promise: Promise<T>, signal: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(new Stopped());
    signal.addEventListener('abort', () => reject(new Stopped()), {once: true});
    promise.then(resolve, reject);
  });
}

/**
 * The job waits behind others: queued with analyses ahead of it. A job accepted into an idle
 * queue is "queued" with nothing ahead only for the moment before it starts.
 */
function waits(state: string, ahead: number | null | undefined): boolean {
  return state === 'queued' && (ahead ?? 0) > 0;
}

function terminalOf(job: AnalysisJob): Terminal | null {
  if (!TERMINAL.has(job.state)) return null;
  if (job.state === 'failed') return {type: 'failed', code: job.error?.code ?? ''};
  return {type: job.state} as Terminal;
}

/**
 * The page's one question at a time (question-analysis Requirement 19, 20): start the job, follow
 * its live events with reconnection, stop it, read the answer. Progress shows only as the map's
 * voyage; a queued job writes "sırada" in the voyage log.
 */
export function useAsk({engine, status, onUnavailable}: Options) {
  const {t} = useIntl();
  const [running, setRunning] = useState(false);
  const [outcome, setOutcome] = useState<AskOutcome | null>(null);
  const current = useRef<Job | null>(null);
  const mounted = useRef(true);
  const latest = useRef({engine, status, onUnavailable, t});
  useEffect(() => {
    latest.current = {engine, status, onUnavailable, t};
  });

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      // Leaving the page stops following, not the analysis: it goes on on the server (Decision 6).
      current.current?.ctrl.abort();
      current.current = null;
    };
  }, []);

  /**
   * Start a question, or follow `resume` (this tab's running job after a reload). The tab
   * remembers the job while it runs and forgets it once it ends or is stopped; leaving the page
   * keeps it, so a reload follows the same job (Decision 26).
   */
  const ask = useCallback(async (text: string, fresh: boolean, resume: AnalysisJob | null = null) => {
    if (current.current) return;
    const {engine: map, status: readStatus} = latest.current;
    const job: Job = {ctrl: new AbortController(), stopped: false, id: resume?.analysis_id ?? null, start: null};
    current.current = job;
    setRunning(true);
    setOutcome(null);
    const cosmos = map();
    const state = readStatus();
    // The radar marks the tables the analysis itself finds: its `tables` events below.
    if (cosmos?.active) cosmos.begin({columns: state?.columns ?? 0});
    // A fast answer (a kept one) still lets the radar finish its turn.
    const radarDone = radarWait(cosmos?.active ? cosmos.radarMs : 0, job.ctrl.signal);
    let ended: AskOutcome;
    try {
      let envelope = resume;
      if (envelope === null) {
        job.start = AnalysisService.start(text, fresh);
        envelope = await untilStopped(job.start, job.ctrl.signal);
      }
      job.id = envelope.analysis_id;
      rememberTabAnalysis(job.id);
      // Assigned from the stream's callback, so held in an object rather than a narrowed local.
      const got: {terminal: Terminal | null} = {terminal: terminalOf(envelope)};
      if (got.terminal === null) {
        if (waits(envelope.state, envelope.ahead)) cosmos?.queued();
        await AnalysisService.follow(
          job.id,
          (event) => {
            let data: AnalysisStreamEvent;
            try {
              data = JSON.parse(event.data) as AnalysisStreamEvent;
            } catch {
              return false;
            }
            if (data.type === 'snapshot' || data.type === 'queued') {
              if (waits(data.type === 'queued' ? 'queued' : data.state, data.ahead)) latest.current.engine()?.queued();
              return false;
            }
            if (data.type === 'tables') {
              latest.current.engine()?.found(data.stage, data.tables);
              return false;
            }
            if (data.type === 'completed') got.terminal = {type: 'completed'};
            else if (data.type === 'failed') got.terminal = {type: 'failed', code: data.code};
            else if (data.type === 'cancelled' || data.type === 'interrupted') got.terminal = {type: data.type};
            return got.terminal !== null;
          },
          job.ctrl.signal,
        );
        if (job.stopped) throw new Stopped();
      }
      const end = got.terminal;
      if (end === null) throw new Stopped();
      if (end.type === 'completed') {
        const full = await AnalysisService.get(job.id, job.ctrl.signal);
        if (!full.result) throw new Error('completed job without an answer');
        ended = {kind: 'answer', answer: full.result, analysisId: job.id};
      } else if (end.type === 'failed') {
        ended = {kind: 'failed', message: askCodeText(end.code, latest.current.t)};
      } else if (end.type === 'cancelled') {
        ended = {kind: 'stopped'};
      } else {
        ended = {kind: 'interrupted'};
      }
      await radarDone;
      if (job.stopped) throw new Stopped();
    } catch (error) {
      ended =
        job.stopped || error instanceof Stopped || (error instanceof DOMException && error.name === 'AbortError')
          ? {kind: 'stopped'}
          : {kind: 'failed', message: askErrorText(error, latest.current.t)};
    }
    if (job.id && (mounted.current || job.stopped)) forgetTabAnalysis(job.id);
    if (current.current === job) current.current = null;
    if (!mounted.current) return;
    if (ended.kind === 'answer') {
      const objects = ended.answer.objects.map((o) => ({key: o.key, name: o.name, score: o.score}));
      latest.current.engine()?.focus(objects, ended.answer.query);
      if (!ended.answer.analyst) latest.current.onUnavailable();
    }
    setOutcome(ended);
    setRunning(false);
    latest.current.engine()?.end();
  }, []);

  /** "Durdur" or Esc: stop the job; before the start answer, stop it as soon as it arrives. */
  const stop = useCallback(() => {
    const job = current.current;
    if (!job || job.stopped) return;
    job.stopped = true;
    job.ctrl.abort();
    const cancel = (id: string) => AnalysisService.cancel(id).catch(() => undefined);
    if (job.id) void cancel(job.id);
    else job.start?.then((started) => cancel(started.analysis_id)).catch(() => undefined);
  }, []);

  const clear = useCallback(() => setOutcome(null), []);

  return {running, outcome, ask, stop, clear};
}
