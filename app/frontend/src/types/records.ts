import type {components} from './api';

type Schemas = components['schemas'];

/** The finished analysis records of the admin screen (data-dictionary/PRDs/008-analysis-records). */
export type RecordPage = Schemas['RecordPage'];
export type RecordRow = Schemas['RecordRowOut'];
export type RecordSummary = Schemas['RecordSummary'];
export type RecordDetail = Schemas['RecordDetail'];
export type RecordStep = Schemas['RecordStep'];
export type RecordReuse = Schemas['RecordReuse'];
export type PhaseAverage = Schemas['PhaseAverage'];
export type PhaseName = PhaseAverage['phase'];
export type DailyCounts = Schemas['DailyCounts'];
export type DayCount = Schemas['DayCount'];
export type Asker = Schemas['Asker'];
export type Askers = Schemas['Askers'];
export type RecordsDeleted = Schemas['RecordsDeleted'];
export type Flow = RecordRow['flow'];
export type RecordVerdict = NonNullable<RecordRow['verdict']>;

/** The list's period filter (Requirement 6). */
export type Period = 'today' | '7d' | '30d' | 'all';

/** The filters the list, the summary and the deletion share (Requirement 6, 7, 11). */
export interface RecordFilters {
  period: Period;
  flow?: Flow | '';
  asked_by?: string;
  q?: string;
}
