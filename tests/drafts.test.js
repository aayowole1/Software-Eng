/**
 * Tests for AI drafts and review interface (SCRUM-19, WBS 1.9).
 *
 * Covers:
 *  - DraftModel unit tests
 *  - POST   /api/drafts
 *  - GET    /api/drafts
 *  - GET    /api/drafts/:id
 *  - DELETE /api/drafts/:id
 *  - POST   /api/drafts/:id/reviews
 */

process.env.JWT_SECRET = 'test-secret';
process.env.JWT_EXPIRES_IN = '1h';

const request = require('supertest');
const app = require('../src/app');
const UserModel = require('../src/models/user');
const DraftModel = require('../src/models/draft');
const { signToken } = require('../src/auth/jwt');

// ── Helpers ───────────────────────────────────────────────────────────────

async function registerUser(email, password, role) {
  await request(app).post('/auth/register').send({ email, password });
  const user = UserModel.findByEmail(email);
  if (role && role !== UserModel.ROLES.VIEWER) {
    UserModel.setUserRole(user.id, role);
    user.role = role;
  }
  return { token: signToken(user), user };
}

beforeEach(() => {
  UserModel._reset();
  DraftModel._reset();
});

// ── DraftModel unit tests ─────────────────────────────────────────────────

describe('DraftModel', () => {
  it('creates a draft with pending_review status', () => {
    const draft = DraftModel.createDraft('My Title', 'Write about X', 'user1');
    expect(draft.title).toBe('My Title');
    expect(draft.prompt).toBe('Write about X');
    expect(draft.status).toBe('pending_review');
    expect(draft.createdBy).toBe('user1');
    expect(draft.content).toBeDefined();
    expect(draft.reviewedBy).toBeNull();
    expect(draft.reviewNote).toBeNull();
    expect(draft.reviewedAt).toBeNull();
  });

  it('generates content from the prompt', () => {
    const draft = DraftModel.createDraft('Title', 'Explain quantum computing', 'user1');
    expect(draft.content).toContain('Explain quantum computing');
  });

  it('findById returns the correct draft', () => {
    const draft = DraftModel.createDraft('T', 'P', 'user1');
    expect(DraftModel.findById(draft.id)).toEqual(draft);
  });

  it('findById returns undefined for unknown id', () => {
    expect(DraftModel.findById('nonexistent')).toBeUndefined();
  });

  it('listAll returns all created drafts', () => {
    DraftModel.createDraft('T1', 'P1', 'user1');
    DraftModel.createDraft('T2', 'P2', 'user1');
    expect(DraftModel.listAll()).toHaveLength(2);
  });

  it('listAll returns empty array when no drafts exist', () => {
    expect(DraftModel.listAll()).toEqual([]);
  });

  it('reviewDraft approves a draft', () => {
    const draft = DraftModel.createDraft('T', 'P', 'user1');
    const updated = DraftModel.reviewDraft(draft.id, 'approved', 'reviewer1', 'Looks good');
    expect(updated.status).toBe('approved');
    expect(updated.reviewedBy).toBe('reviewer1');
    expect(updated.reviewNote).toBe('Looks good');
    expect(updated.reviewedAt).toBeDefined();
  });

  it('reviewDraft rejects a draft', () => {
    const draft = DraftModel.createDraft('T', 'P', 'user1');
    const updated = DraftModel.reviewDraft(draft.id, 'rejected', 'reviewer1', 'Not suitable');
    expect(updated.status).toBe('rejected');
  });

  it('reviewDraft marks a draft as revision_requested', () => {
    const draft = DraftModel.createDraft('T', 'P', 'user1');
    const updated = DraftModel.reviewDraft(draft.id, 'revision_requested', 'reviewer1', 'Please revise');
    expect(updated.status).toBe('revision_requested');
  });

  it('reviewDraft stores null note when none provided', () => {
    const draft = DraftModel.createDraft('T', 'P', 'user1');
    const updated = DraftModel.reviewDraft(draft.id, 'approved', 'reviewer1');
    expect(updated.reviewNote).toBeNull();
  });

  it('reviewDraft throws for invalid decision', () => {
    const draft = DraftModel.createDraft('T', 'P', 'user1');
    expect(() => DraftModel.reviewDraft(draft.id, 'maybe', 'reviewer1')).toThrow(/Invalid review decision/);
  });

  it('reviewDraft throws for unknown draft id', () => {
    expect(() => DraftModel.reviewDraft('nonexistent', 'approved', 'reviewer1')).toThrow(/Draft not found/);
  });

  it('deleteDraft removes the draft and returns true', () => {
    const draft = DraftModel.createDraft('T', 'P', 'user1');
    expect(DraftModel.deleteDraft(draft.id)).toBe(true);
    expect(DraftModel.findById(draft.id)).toBeUndefined();
  });

  it('deleteDraft returns false for unknown id', () => {
    expect(DraftModel.deleteDraft('nonexistent')).toBe(false);
  });

  it('_reset clears all drafts', () => {
    DraftModel.createDraft('T', 'P', 'user1');
    DraftModel._reset();
    expect(DraftModel.listAll()).toHaveLength(0);
  });

  it('DRAFT_STATUSES contains expected values', () => {
    expect(DraftModel.DRAFT_STATUSES.PENDING_REVIEW).toBe('pending_review');
    expect(DraftModel.DRAFT_STATUSES.APPROVED).toBe('approved');
    expect(DraftModel.DRAFT_STATUSES.REJECTED).toBe('rejected');
    expect(DraftModel.DRAFT_STATUSES.REVISION_REQUESTED).toBe('revision_requested');
  });

  it('REVIEW_DECISIONS contains expected values', () => {
    expect(DraftModel.REVIEW_DECISIONS.APPROVED).toBe('approved');
    expect(DraftModel.REVIEW_DECISIONS.REJECTED).toBe('rejected');
    expect(DraftModel.REVIEW_DECISIONS.REVISION_REQUESTED).toBe('revision_requested');
  });
});

// ── POST /api/drafts ──────────────────────────────────────────────────────

describe('POST /api/drafts', () => {
  it('editor can request an AI draft', async () => {
    const { token, user } = await registerUser('ed@ex.com', 'password1', 'editor');
    const res = await request(app)
      .post('/api/drafts')
      .set('Authorization', `Bearer ${token}`)
      .send({ title: 'My Draft', prompt: 'Write about Node.js' });

    expect(res.status).toBe(201);
    expect(res.body.draft.title).toBe('My Draft');
    expect(res.body.draft.prompt).toBe('Write about Node.js');
    expect(res.body.draft.status).toBe('pending_review');
    expect(res.body.draft.createdBy).toBe(user.id);
    expect(res.body.draft.content).toBeDefined();
    expect(res.body.draft.reviewedBy).toBeNull();
  });

  it('admin can request an AI draft', async () => {
    const { token } = await registerUser('admin@ex.com', 'password1', 'admin');
    const res = await request(app)
      .post('/api/drafts')
      .set('Authorization', `Bearer ${token}`)
      .send({ title: 'Admin Draft', prompt: 'Write about security' });

    expect(res.status).toBe(201);
    expect(res.body.draft.title).toBe('Admin Draft');
  });

  it('returns 403 for viewer', async () => {
    const { token } = await registerUser('viewer@ex.com', 'password1', 'viewer');
    const res = await request(app)
      .post('/api/drafts')
      .set('Authorization', `Bearer ${token}`)
      .send({ title: 'Viewer Draft', prompt: 'Should fail' });

    expect(res.status).toBe(403);
  });

  it('returns 401 without a token', async () => {
    const res = await request(app)
      .post('/api/drafts')
      .send({ title: 'No Auth', prompt: 'No auth' });

    expect(res.status).toBe(401);
  });

  it('returns 400 when title is missing', async () => {
    const { token } = await registerUser('ed@ex.com', 'password1', 'editor');
    const res = await request(app)
      .post('/api/drafts')
      .set('Authorization', `Bearer ${token}`)
      .send({ prompt: 'Missing title' });

    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/title is required/);
  });

  it('returns 400 when title is blank', async () => {
    const { token } = await registerUser('ed@ex.com', 'password1', 'editor');
    const res = await request(app)
      .post('/api/drafts')
      .set('Authorization', `Bearer ${token}`)
      .send({ title: '   ', prompt: 'Blank title' });

    expect(res.status).toBe(400);
  });

  it('returns 400 when prompt is missing', async () => {
    const { token } = await registerUser('ed@ex.com', 'password1', 'editor');
    const res = await request(app)
      .post('/api/drafts')
      .set('Authorization', `Bearer ${token}`)
      .send({ title: 'Title only' });

    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/prompt is required/);
  });

  it('returns 400 when prompt is blank', async () => {
    const { token } = await registerUser('ed@ex.com', 'password1', 'editor');
    const res = await request(app)
      .post('/api/drafts')
      .set('Authorization', `Bearer ${token}`)
      .send({ title: 'Good Title', prompt: '   ' });

    expect(res.status).toBe(400);
  });

  it('strips whitespace from title and prompt', async () => {
    const { token } = await registerUser('ed@ex.com', 'password1', 'editor');
    const res = await request(app)
      .post('/api/drafts')
      .set('Authorization', `Bearer ${token}`)
      .send({ title: '  Trimmed Title  ', prompt: '  Trimmed prompt  ' });

    expect(res.status).toBe(201);
    expect(res.body.draft.title).toBe('Trimmed Title');
    expect(res.body.draft.prompt).toBe('Trimmed prompt');
  });
});

// ── GET /api/drafts ───────────────────────────────────────────────────────

describe('GET /api/drafts', () => {
  it('viewer can list drafts', async () => {
    const { token: edToken } = await registerUser('ed@ex.com', 'password1', 'editor');
    await request(app)
      .post('/api/drafts')
      .set('Authorization', `Bearer ${edToken}`)
      .send({ title: 'Draft A', prompt: 'Prompt A' });
    await request(app)
      .post('/api/drafts')
      .set('Authorization', `Bearer ${edToken}`)
      .send({ title: 'Draft B', prompt: 'Prompt B' });

    const { token: vwToken } = await registerUser('viewer@ex.com', 'password1', 'viewer');
    const res = await request(app)
      .get('/api/drafts')
      .set('Authorization', `Bearer ${vwToken}`);

    expect(res.status).toBe(200);
    expect(res.body.drafts).toHaveLength(2);
  });

  it('returns empty array when no drafts exist', async () => {
    const { token } = await registerUser('viewer@ex.com', 'password1', 'viewer');
    const res = await request(app)
      .get('/api/drafts')
      .set('Authorization', `Bearer ${token}`);

    expect(res.status).toBe(200);
    expect(res.body.drafts).toEqual([]);
  });

  it('returns 401 without a token', async () => {
    const res = await request(app).get('/api/drafts');
    expect(res.status).toBe(401);
  });
});

// ── GET /api/drafts/:id ───────────────────────────────────────────────────

describe('GET /api/drafts/:id', () => {
  let edToken, draftId;

  beforeEach(async () => {
    const ed = await registerUser('ed@ex.com', 'password1', 'editor');
    edToken = ed.token;
    const createRes = await request(app)
      .post('/api/drafts')
      .set('Authorization', `Bearer ${edToken}`)
      .send({ title: 'Test Draft', prompt: 'Test prompt' });
    draftId = createRes.body.draft.id;
  });

  it('viewer can get a specific draft', async () => {
    const { token: vwToken } = await registerUser('viewer@ex.com', 'password1', 'viewer');
    const res = await request(app)
      .get(`/api/drafts/${draftId}`)
      .set('Authorization', `Bearer ${vwToken}`);

    expect(res.status).toBe(200);
    expect(res.body.draft.id).toBe(draftId);
    expect(res.body.draft.title).toBe('Test Draft');
  });

  it('returns 404 for unknown draft id', async () => {
    const res = await request(app)
      .get('/api/drafts/nonexistent')
      .set('Authorization', `Bearer ${edToken}`);

    expect(res.status).toBe(404);
    expect(res.body.error).toMatch(/Draft not found/);
  });

  it('returns 401 without a token', async () => {
    const res = await request(app).get(`/api/drafts/${draftId}`);
    expect(res.status).toBe(401);
  });
});

// ── DELETE /api/drafts/:id ────────────────────────────────────────────────

describe('DELETE /api/drafts/:id', () => {
  let adminToken, edToken, draftId;

  beforeEach(async () => {
    const adm = await registerUser('admin@ex.com', 'password1', 'admin');
    adminToken = adm.token;
    const ed = await registerUser('ed@ex.com', 'password1', 'editor');
    edToken = ed.token;

    const createRes = await request(app)
      .post('/api/drafts')
      .set('Authorization', `Bearer ${edToken}`)
      .send({ title: 'Temp Draft', prompt: 'Temp prompt' });
    draftId = createRes.body.draft.id;
  });

  it('admin can delete a draft', async () => {
    const res = await request(app)
      .delete(`/api/drafts/${draftId}`)
      .set('Authorization', `Bearer ${adminToken}`);

    expect(res.status).toBe(204);

    // Draft should no longer be retrievable
    const getRes = await request(app)
      .get(`/api/drafts/${draftId}`)
      .set('Authorization', `Bearer ${adminToken}`);
    expect(getRes.status).toBe(404);
  });

  it('returns 403 for editor', async () => {
    const res = await request(app)
      .delete(`/api/drafts/${draftId}`)
      .set('Authorization', `Bearer ${edToken}`);

    expect(res.status).toBe(403);
  });

  it('returns 404 for unknown draft id', async () => {
    const res = await request(app)
      .delete('/api/drafts/nonexistent')
      .set('Authorization', `Bearer ${adminToken}`);

    expect(res.status).toBe(404);
    expect(res.body.error).toMatch(/Draft not found/);
  });

  it('returns 401 without a token', async () => {
    const res = await request(app).delete(`/api/drafts/${draftId}`);
    expect(res.status).toBe(401);
  });
});

// ── POST /api/drafts/:id/reviews ──────────────────────────────────────────

describe('POST /api/drafts/:id/reviews', () => {
  let edToken, adminToken, viewerToken, reviewerUser, draftId;

  beforeEach(async () => {
    const adm = await registerUser('admin@ex.com', 'password1', 'admin');
    adminToken = adm.token;
    const ed = await registerUser('ed@ex.com', 'password1', 'editor');
    edToken = ed.token;
    const reviewer = await registerUser('reviewer@ex.com', 'password1', 'editor');
    reviewerUser = reviewer.user;
    const vw = await registerUser('viewer@ex.com', 'password1', 'viewer');
    viewerToken = vw.token;

    const createRes = await request(app)
      .post('/api/drafts')
      .set('Authorization', `Bearer ${edToken}`)
      .send({ title: 'Review Me', prompt: 'Generate something' });
    draftId = createRes.body.draft.id;
  });

  it('editor can approve a draft', async () => {
    const res = await request(app)
      .post(`/api/drafts/${draftId}/reviews`)
      .set('Authorization', `Bearer ${edToken}`)
      .send({ decision: 'approved', note: 'Great draft!' });

    expect(res.status).toBe(200);
    expect(res.body.draft.status).toBe('approved');
    expect(res.body.draft.reviewNote).toBe('Great draft!');
    expect(res.body.draft.reviewedBy).toBeDefined();
    expect(res.body.draft.reviewedAt).toBeDefined();
  });

  it('editor can reject a draft', async () => {
    const res = await request(app)
      .post(`/api/drafts/${draftId}/reviews`)
      .set('Authorization', `Bearer ${edToken}`)
      .send({ decision: 'rejected', note: 'Not suitable' });

    expect(res.status).toBe(200);
    expect(res.body.draft.status).toBe('rejected');
    expect(res.body.draft.reviewNote).toBe('Not suitable');
  });

  it('editor can request revision', async () => {
    const res = await request(app)
      .post(`/api/drafts/${draftId}/reviews`)
      .set('Authorization', `Bearer ${edToken}`)
      .send({ decision: 'revision_requested', note: 'Please expand section 2' });

    expect(res.status).toBe(200);
    expect(res.body.draft.status).toBe('revision_requested');
  });

  it('admin can review a draft', async () => {
    const res = await request(app)
      .post(`/api/drafts/${draftId}/reviews`)
      .set('Authorization', `Bearer ${adminToken}`)
      .send({ decision: 'approved' });

    expect(res.status).toBe(200);
    expect(res.body.draft.status).toBe('approved');
    expect(res.body.draft.reviewNote).toBeNull();
  });

  it('review records the reviewer user id', async () => {
    const res = await request(app)
      .post(`/api/drafts/${draftId}/reviews`)
      .set('Authorization', `Bearer ${edToken}`)
      .send({ decision: 'approved' });

    expect(res.status).toBe(200);
    expect(res.body.draft.reviewedBy).toBeDefined();
  });

  it('returns 403 for viewer', async () => {
    const res = await request(app)
      .post(`/api/drafts/${draftId}/reviews`)
      .set('Authorization', `Bearer ${viewerToken}`)
      .send({ decision: 'approved' });

    expect(res.status).toBe(403);
  });

  it('returns 401 without a token', async () => {
    const res = await request(app)
      .post(`/api/drafts/${draftId}/reviews`)
      .send({ decision: 'approved' });

    expect(res.status).toBe(401);
  });

  it('returns 400 when decision is missing', async () => {
    const res = await request(app)
      .post(`/api/drafts/${draftId}/reviews`)
      .set('Authorization', `Bearer ${edToken}`)
      .send({});

    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/decision is required/);
  });

  it('returns 400 for invalid decision value', async () => {
    const res = await request(app)
      .post(`/api/drafts/${draftId}/reviews`)
      .set('Authorization', `Bearer ${edToken}`)
      .send({ decision: 'maybe' });

    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/Invalid review decision/);
  });

  it('returns 404 for unknown draft id', async () => {
    const res = await request(app)
      .post('/api/drafts/nonexistent/reviews')
      .set('Authorization', `Bearer ${edToken}`)
      .send({ decision: 'approved' });

    expect(res.status).toBe(404);
    expect(res.body.error).toMatch(/Draft not found/);
  });
});
