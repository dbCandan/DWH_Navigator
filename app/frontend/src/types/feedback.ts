import type {components} from './api';

type Schemas = components['schemas'];

/** Votes on answers and their tables (data-dictionary/PRDs/006-answer-feedback). */
export type VoteIn = Schemas['VoteIn'];
export type VoteRecorded = Schemas['VoteRecorded'];
export type Tally = Schemas['Tally'];
export type AnswerFeedback = Schemas['AnswerFeedback'];
export type EndorsedTable = Schemas['EndorsedTable'];
export type VoteValue = VoteIn['vote'];
