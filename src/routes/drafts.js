/**
 * AI draft and review routes (WBS 1.9 — SCRUM-19).
 *
 * Drafts
 * ─────────────────────────────────────────────────────────────────────────
 * POST   /api/drafts              – request an AI draft       (editor+)
 * GET    /api/drafts              – list all drafts            (viewer+)
 * GET    /api/drafts/:id          – get a specific draft       (viewer+)
 * DELETE /api/drafts/:id          – delete a draft             (admin)
 *
 * Reviews
 * ─────────────────────────────────────────────────────────────────────────
 * POST   /api/drafts/:id/reviews  – submit a review decision  (editor+)
 */

const express = require('express');
const { authenticate } = require('../middleware/authenticate');
const { authorize } = require('../middleware/authorize');
const DraftModel = require('../models/draft');

const router = express.Router();

// ── Drafts ────────────────────────────────────────────────────────────────

/**
 * POST /api/drafts
 * Request an AI draft. The body must contain `title` and `prompt`.
 * The system generates content from the prompt and stores it as a draft
 * with status `pending_review`.
 * Requires: editor or admin.
 */
router.post('/drafts', authenticate, authorize('editor'), (req, res) => {
  const { title, prompt } = req.body || {};
  if (!title || typeof title !== 'string' || title.trim() === '') {
    return res.status(400).json({ error: 'title is required' });
  }
  if (!prompt || typeof prompt !== 'string' || prompt.trim() === '') {
    return res.status(400).json({ error: 'prompt is required' });
  }

  const draft = DraftModel.createDraft(title.trim(), prompt.trim(), req.user.id);
  res.status(201).json({ draft });
});

/**
 * GET /api/drafts
 * List all drafts. Requires: viewer+.
 */
router.get('/drafts', authenticate, authorize('viewer'), (_req, res) => {
  const drafts = DraftModel.listAll();
  res.json({ drafts });
});

/**
 * GET /api/drafts/:id
 * Get a specific draft by id. Requires: viewer+.
 */
router.get('/drafts/:id', authenticate, authorize('viewer'), (req, res) => {
  const draft = DraftModel.findById(req.params.id);
  if (!draft) return res.status(404).json({ error: 'Draft not found' });
  res.json({ draft });
});

/**
 * DELETE /api/drafts/:id
 * Delete a draft. Requires: admin.
 */
router.delete('/drafts/:id', authenticate, authorize('admin'), (req, res) => {
  const draft = DraftModel.findById(req.params.id);
  if (!draft) return res.status(404).json({ error: 'Draft not found' });

  DraftModel.deleteDraft(draft.id);
  res.status(204).send();
});

// ── Reviews ───────────────────────────────────────────────────────────────

/**
 * POST /api/drafts/:id/reviews
 * Submit a review decision for a draft.
 * Body: { decision, note? }
 * Valid decisions: 'approved', 'rejected', 'revision_requested'
 * Requires: editor+.
 */
router.post('/drafts/:id/reviews', authenticate, authorize('editor'), (req, res) => {
  const draft = DraftModel.findById(req.params.id);
  if (!draft) return res.status(404).json({ error: 'Draft not found' });

  const { decision, note } = req.body || {};
  if (!decision) return res.status(400).json({ error: 'decision is required' });

  try {
    const updated = DraftModel.reviewDraft(draft.id, decision, req.user.id, note);
    res.json({ draft: updated });
  } catch (err) {
    if (err.message.startsWith('Invalid review decision')) {
      return res.status(400).json({ error: err.message });
    }
    res.status(500).json({ error: 'Failed to submit review' });
  }
});

module.exports = router;
