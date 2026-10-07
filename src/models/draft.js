/**
 * Draft model — stores AI-generated content drafts awaiting human review.
 *
 * A draft moves through the following status lifecycle:
 *   pending_review  → approved
 *   pending_review  → rejected
 *   pending_review  → revision_requested → pending_review (re-submitted)
 *
 * All data is stored in an in-memory Map (no external database required).
 */

const DRAFT_STATUSES = Object.freeze({
  PENDING_REVIEW: 'pending_review',
  APPROVED: 'approved',
  REJECTED: 'rejected',
  REVISION_REQUESTED: 'revision_requested',
});

const REVIEW_DECISIONS = Object.freeze({
  APPROVED: 'approved',
  REJECTED: 'rejected',
  REVISION_REQUESTED: 'revision_requested',
});

// In-memory store keyed by draft id
const drafts = new Map();

/**
 * Simulate AI content generation from a prompt.
 * In a production system this would call a real AI API.
 * @param {string} prompt
 * @returns {string} Generated content
 */
function generateContent(prompt) {
  return `[AI-generated draft]\n\nPrompt: ${prompt}\n\nThis is a simulated AI response to the provided prompt. In a production system this content would be produced by a language model.`;
}

/**
 * Create a new AI draft.
 * @param {string} title    - Human-readable title for the draft
 * @param {string} prompt   - The prompt submitted for AI generation
 * @param {string} createdBy - User id of the requester
 * @returns {object} The created draft record
 */
function createDraft(title, prompt, createdBy) {
  const draft = {
    id: `draft_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    title,
    prompt,
    content: generateContent(prompt),
    status: DRAFT_STATUSES.PENDING_REVIEW,
    createdBy,
    createdAt: new Date().toISOString(),
    reviewedBy: null,
    reviewNote: null,
    reviewedAt: null,
  };
  drafts.set(draft.id, draft);
  return draft;
}

/**
 * Find a draft by id.
 * @param {string} id
 * @returns {object|undefined}
 */
function findById(id) {
  return drafts.get(id);
}

/**
 * Return all drafts as an array.
 * @returns {object[]}
 */
function listAll() {
  return Array.from(drafts.values());
}

/**
 * Apply a review decision to a draft.
 * @param {string} id         - Draft id
 * @param {string} decision   - One of the REVIEW_DECISIONS values
 * @param {string} reviewedBy - User id of the reviewer
 * @param {string} [note]     - Optional reviewer note
 * @returns {object} Updated draft record
 */
function reviewDraft(id, decision, reviewedBy, note) {
  if (!Object.values(REVIEW_DECISIONS).includes(decision)) {
    throw new Error(`Invalid review decision: ${decision}`);
  }
  const draft = drafts.get(id);
  if (!draft) throw new Error(`Draft not found: ${id}`);

  draft.status = decision;
  draft.reviewedBy = reviewedBy;
  draft.reviewNote = note || null;
  draft.reviewedAt = new Date().toISOString();
  return draft;
}

/**
 * Delete a draft by id.
 * @param {string} id
 * @returns {boolean} true if deleted, false if not found
 */
function deleteDraft(id) {
  return drafts.delete(id);
}

/**
 * Clear all drafts (for testing only).
 */
function _reset() {
  drafts.clear();
}

module.exports = {
  DRAFT_STATUSES,
  REVIEW_DECISIONS,
  createDraft,
  findById,
  listAll,
  reviewDraft,
  deleteDraft,
  _reset,
};
