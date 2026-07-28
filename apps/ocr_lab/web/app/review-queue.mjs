/**
 * Return only review cases that have not been persisted by the API.
 *
 * Keeping this as a pure function makes reload/resume behavior testable without
 * mounting the full dashboard.
 */
export function pendingReviewCases(cases, lineReviews) {
  const reviewed = lineReviews ?? {};
  return (cases ?? []).filter((item) => !reviewed[item.caseId]);
}

/**
 * Resume from the first pending case after a reload.
 *
 * The queue contains only pending cases, therefore position zero is always the
 * next unverified crop even when hundreds of earlier cases are complete.
 */
export function resumePendingReview(cases, lineReviews) {
  const pending = pendingReviewCases(cases, lineReviews);
  return {
    pending,
    index: 0,
    active: pending[0] ?? null,
  };
}
