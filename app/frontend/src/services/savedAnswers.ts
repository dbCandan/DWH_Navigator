import {apiRequest} from '@/lib/apiClient';

/*
 * The kept answers' summary and deletion belong to question-analysis Requirement 15
 * (`GET /saved-answers/summary`, `DELETE /saved-answers`); search-settings Requirement 16 reads
 * them on the Bakım page. The recorded OpenAPI contract does not carry these endpoints yet, so
 * the smallest response projection stands beside the service (rules/31) until the backend
 * exports them; the generated types then replace these two interfaces.
 */

/** `GET /saved-answers/summary`: how many answers are kept and usable, and the newest one. */
export interface SavedAnswersSummary {
  total: number;
  usable: number;
  newest_at: string | null;
}

/** `DELETE /saved-answers`: how many answers were deleted. */
export interface SavedAnswersCleared {
  removed: number;
}

export const SavedAnswersService = {
  summary(): Promise<SavedAnswersSummary> {
    return apiRequest<SavedAnswersSummary>('/saved-answers/summary');
  },
  clear(): Promise<SavedAnswersCleared> {
    return apiRequest<SavedAnswersCleared>('/saved-answers', {method: 'DELETE'});
  },
};
