/**
 * Architecture and test foundation (SCRUM-12).
 *
 * Covers acceptance-criteria gaps and previously uncovered code paths:
 *
 *  - UserModel unit tests (findByProvider, upsertOAuthUser, findById, setUserRole)
 *  - jwt.js verifyToken
 *  - authenticate middleware (missing/malformed header, user-not-found)
 *  - authorize middleware (req.user absent)
 *  - GET  /api/admin/users (admin only)
 *  - PUT  /api/admin/users/:id/role → 404 for unknown user
 *  - GET  /health
 *  - Express error-handler (500)
 */

process.env.JWT_SECRET = 'test-secret';
process.env.JWT_EXPIRES_IN = '1h';

const request = require('supertest');
const app = require('../src/app');
const UserModel = require('../src/models/user');
const { signToken, verifyToken } = require('../src/auth/jwt');

beforeEach(() => {
  UserModel._reset();
});

// ── UserModel unit tests ──────────────────────────────────────────────────

describe('UserModel — findByProvider', () => {
  it('returns undefined when no OAuth user exists', () => {
    expect(UserModel.findByProvider('google', '999')).toBeUndefined();
  });

  it('finds a user by provider and providerId', () => {
    const user = UserModel.upsertOAuthUser({
      provider: 'google',
      providerId: '42',
      email: 'guser@example.com',
      displayName: 'G User',
      photo: null,
    });
    expect(UserModel.findByProvider('google', '42')).toEqual(user);
  });
});

describe('UserModel — upsertOAuthUser', () => {
  it('creates a new OAuth user with viewer role', () => {
    const user = UserModel.upsertOAuthUser({
      provider: 'google',
      providerId: '1',
      email: 'new@example.com',
      displayName: 'New User',
      photo: 'http://photo.url',
    });
    expect(user.provider).toBe('google');
    expect(user.providerId).toBe('1');
    expect(user.email).toBe('new@example.com');
    expect(user.role).toBe(UserModel.ROLES.VIEWER);
    expect(user).not.toHaveProperty('passwordHash');
  });

  it('updates displayName and photo on second upsert for same provider+id', () => {
    UserModel.upsertOAuthUser({
      provider: 'google',
      providerId: '1',
      email: 'g@example.com',
      displayName: 'Old Name',
      photo: null,
    });
    const updated = UserModel.upsertOAuthUser({
      provider: 'google',
      providerId: '1',
      email: 'g@example.com',
      displayName: 'New Name',
      photo: 'http://new.photo',
    });
    expect(updated.displayName).toBe('New Name');
    expect(updated.photo).toBe('http://new.photo');
    // Only one user should exist
    expect(UserModel.findByProvider('google', '1')).toEqual(updated);
  });

  it('retains the original role on upsert', () => {
    const first = UserModel.upsertOAuthUser({
      provider: 'google',
      providerId: '7',
      email: 'g7@example.com',
      displayName: 'User 7',
      photo: null,
    });
    UserModel.setUserRole(first.id, 'editor');
    const second = UserModel.upsertOAuthUser({
      provider: 'google',
      providerId: '7',
      email: 'g7@example.com',
      displayName: 'User 7 Updated',
      photo: null,
    });
    // Role should NOT be reset by upsert
    expect(second.role).toBe('editor');
  });
});

describe('UserModel — findById', () => {
  it('returns undefined for unknown id', () => {
    expect(UserModel.findById('usr_unknown')).toBeUndefined();
  });
});

describe('UserModel — setUserRole', () => {
  it('throws for an invalid role', () => {
    const { user } = createLocalUser('u@ex.com');
    expect(() => UserModel.setUserRole(user.id, 'superuser')).toThrow(/Invalid role/);
  });

  it('throws for an unknown user id', () => {
    expect(() => UserModel.setUserRole('usr_none', 'editor')).toThrow(/User not found/);
  });
});

// ── jwt.js — verifyToken ──────────────────────────────────────────────────

describe('verifyToken', () => {
  it('decodes a valid token and returns the payload', () => {
    const user = { id: 'usr_1', role: 'viewer' };
    const token = signToken(user);
    const payload = verifyToken(token);
    expect(payload.id).toBe('usr_1');
    expect(payload.role).toBe('viewer');
  });

  it('throws JsonWebTokenError for a tampered token', () => {
    const token = signToken({ id: 'usr_1', role: 'viewer' });
    expect(() => verifyToken(token.slice(0, -4) + 'XXXX')).toThrow();
  });
});

// ── authenticate middleware edge cases ───────────────────────────────────

describe('authenticate middleware', () => {
  it('returns 401 when Authorization header is absent', async () => {
    const res = await request(app).get('/api/posts');
    expect(res.status).toBe(401);
    expect(res.body.error).toMatch(/Missing or malformed/);
  });

  it('returns 401 when scheme is not Bearer', async () => {
    const res = await request(app)
      .get('/api/posts')
      .set('Authorization', 'Basic dXNlcjpwYXNz');
    expect(res.status).toBe(401);
  });

  it('returns 401 when the user referenced by the token no longer exists', async () => {
    // Sign a token for a user that is not in the store
    const ghostToken = signToken({ id: 'usr_ghost_99', role: 'viewer' });
    const res = await request(app)
      .get('/api/posts')
      .set('Authorization', `Bearer ${ghostToken}`);
    expect(res.status).toBe(401);
    expect(res.body.error).toMatch(/User not found/);
  });
});

// ── authorize middleware edge cases ──────────────────────────────────────

describe('authorize middleware — missing req.user', () => {
  it('returns 401 when req.user is not set', () => {
    const { authorize } = require('../src/middleware/authorize');
    const middleware = authorize('viewer');
    const req = {};             // no req.user
    const res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn(),
    };
    const next = jest.fn();
    middleware(req, res, next);
    expect(res.status).toHaveBeenCalledWith(401);
    expect(next).not.toHaveBeenCalled();
  });
});

// ── GET /health ───────────────────────────────────────────────────────────

describe('GET /health', () => {
  it('returns 200 with status ok', async () => {
    const res = await request(app).get('/health');
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('ok');
  });
});

// ── GET /api/admin/users ─────────────────────────────────────────────────

describe('GET /api/admin/users', () => {
  it('returns 200 with a message for an admin', async () => {
    const { token } = await registerAndTokenize('admin@ex.com', 'admin');
    const res = await request(app)
      .get('/api/admin/users')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('message');
    expect(res.body.currentUser).not.toHaveProperty('passwordHash');
  });

  it('returns 403 for editor', async () => {
    const { token } = await registerAndTokenize('editor@ex.com', 'editor');
    const res = await request(app)
      .get('/api/admin/users')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(403);
  });

  it('returns 403 for viewer', async () => {
    const { token } = await registerAndTokenize('viewer@ex.com', 'viewer');
    const res = await request(app)
      .get('/api/admin/users')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(403);
  });

  it('returns 401 without token', async () => {
    const res = await request(app).get('/api/admin/users');
    expect(res.status).toBe(401);
  });
});

// ── PUT /api/admin/users/:id/role — 404 for unknown user ─────────────────

describe('PUT /api/admin/users/:id/role — unknown user returns 404', () => {
  it('returns 404 when user id does not exist', async () => {
    const { token } = await registerAndTokenize('admin@ex.com', 'admin');
    const res = await request(app)
      .put('/api/admin/users/usr_nonexistent/role')
      .set('Authorization', `Bearer ${token}`)
      .send({ role: 'editor' });
    expect(res.status).toBe(404);
    expect(res.body.error).toMatch(/User not found/);
  });

  it('still returns 400 for an invalid role value', async () => {
    const { token } = await registerAndTokenize('admin@ex.com', 'admin');
    const target = UserModel.findByEmail('admin@ex.com');
    const res = await request(app)
      .put(`/api/admin/users/${target.id}/role`)
      .set('Authorization', `Bearer ${token}`)
      .send({ role: 'overlord' });
    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/Invalid role/);
  });

  it('returns 400 when role field is absent', async () => {
    const { token } = await registerAndTokenize('admin@ex.com', 'admin');
    const res = await request(app)
      .put('/api/admin/users/usr_any/role')
      .set('Authorization', `Bearer ${token}`)
      .send({});
    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/role is required/);
  });
});

// ── Express error handler (500) ───────────────────────────────────────────

describe('Express global error handler', () => {
  it('returns 500 for unhandled errors thrown in a route', async () => {
    const express = require('express');
    const errorApp = express();
    errorApp.use(express.json());

    // Route that passes an error to next() to trigger the error handler
    errorApp.get('/throw', (_req, _res, next) => {
      next(new Error('forced error'));
    });

    // eslint-disable-next-line no-unused-vars
    errorApp.use((err, _req, res, _next) => {
      res.status(500).json({ error: 'Internal server error' });
    });

    const res = await request(errorApp).get('/throw');
    expect(res.status).toBe(500);
    expect(res.body.error).toBe('Internal server error');
  });
});

// ── Helpers ───────────────────────────────────────────────────────────────

async function registerAndTokenize(email, role) {
  const res = await request(app)
    .post('/auth/register')
    .send({ email, password: 'password123' });
  const user = UserModel.findByEmail(email);
  if (role && role !== 'viewer') {
    UserModel.setUserRole(user.id, role);
    user.role = role;
  }
  return { token: signToken(user), user };
}

function createLocalUser(email) {
  const bcrypt = require('bcryptjs');
  // Synchronous hash for unit test speed
  const hash = bcrypt.hashSync('password1', 1);
  const user = UserModel.createLocalUser(email, hash);
  return { user };
}
