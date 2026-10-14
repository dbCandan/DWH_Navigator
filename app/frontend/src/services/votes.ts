import {visitorRequest} from '@/lib/apiClient';
import type {VoteIn, VoteRecorded} from '@/types/feedback';

/** A 👍/👎 on a suggested table or on the whole answer (answer-feedback Requirement 1). */
export const VoteService = {
  cast(vote: VoteIn): Promise<VoteRecorded> {
    return visitorRequest<VoteRecorded>('/votes', {method: 'POST', body: JSON.stringify(vote)});
  },
};
