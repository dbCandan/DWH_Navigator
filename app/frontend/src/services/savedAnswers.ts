import {apiRequest} from '@/lib/apiClient';
import type {SavedAnswersRemoved, SavedAnswersSummary} from '@/types/analysis';

/**
 * The kept answers' summary and deletion (question-analysis Requirement 15); the Bakım page reads
 * them (search-settings Requirement 16).
 */
export const SavedAnswersService = {
  summary(): Promise<SavedAnswersSummary> {
    return apiRequest<SavedAnswersSummary>('/saved-answers/summary');
  },
  clear(): Promise<SavedAnswersRemoved> {
    return apiRequest<SavedAnswersRemoved>('/saved-answers', {method: 'DELETE'});
  },
};
