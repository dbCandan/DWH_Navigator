import type {components} from './api';

type Schemas = components['schemas'];

/** Question analysis jobs, their answers and live events (data-dictionary/PRDs/004-question-analysis). */
export type AnalysisJob = Schemas['AnalysisJob'];
export type AnalysisJobWithResult = Schemas['AnalysisJobWithResult'];
export type AnalysisState = AnalysisJob['state'];
export type AnalysisAnswer = Schemas['AnalysisAnswer'];
export type AnswerObject = Schemas['AnswerObject'];
export type AnswerColumn = Schemas['AnswerColumn'];
export type AnswerNote = Schemas['AnswerNote'];
export type AnswerReuse = Schemas['AnswerReuse'];
export type AnalysisStreamEvent = Schemas['AnalysisStreamEvent'];
export type Verdict = AnalysisAnswer['verdict'];

/** `GET /status`: the dictionary, the model and the shortlist the engine serves with. */
export type ServiceStatus = Schemas['StatusOut'];

/** `GET /saved-answers/summary` and `DELETE /saved-answers` (Requirement 15). */
export type SavedAnswersSummary = Schemas['SavedAnswerSummaryOut'];
export type SavedAnswersRemoved = Schemas['SavedAnswersRemoved'];
