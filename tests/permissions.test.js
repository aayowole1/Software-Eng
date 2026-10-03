/**
 * Tests for role-based permissions middleware and protected routes.
 */

process.env.JWT_SECRET = 'test-secret';
process.env.JWT_EXPIRES_IN = '1h';

const request = require('supertest');
const app = require('../src/app');
const UserModel = require('../src/models/user');
const { signToken } = require('../src/auth/jwt');
const { hasMinimumRole, ROLES } = require('../src/models/user');

// Helper: register a user and get their token, then optionally elevate role
async function registerUser(email, password, role) {
  const res = await request(app)
    .post('/auth/register')
    .send({ email, password });

  const user = UserModel.findByEmail(email);
  if (role && role !== ROLES.VIEWER) {
    UserModel.setUserRole(user.id, role);
    user.role = role;
  }
  // Re-sign token with updated role
  return { token: signToken(user), user };
}

beforeEach(() => {
  UserModel._reset();
});

// ── hasMinimumRole unit tests ─────────────────────────────────────────────

describe('hasMinimumRole', () => {
  it('admin satisfies admin requirement', () => {
    expect(hasMinimumRole('admin', 'admin')).toBe(true);
  });
  it('admin satisfies editor requirement', () => {
    expect(hasMinimumRole('admin', 'editor')).toBe(true);
  });
  it('admin satisfies viewer requirement', () => {
    expect(hasMinimumRole('admin', 'viewer')).toBe(true);
  });
  it('editor satisfies editor requirement', () => {
    expect(hasMinimumRole('editor', 'editor')).toBe(true);
  });
  it('editor satisfies viewer requirement', () => {
    expect(hasMinimumRole('editor', 'viewer')).toBe(true);
  });
  it('editor does NOT satisfy admin requirement', () => {
    expect(hasMinimumRole('editor', 'admin')).toBe(false);
  });
  it('viewer satisfies viewer requirement', () => {
    expect(hasMinimumRole('viewer', 'viewer')).toBe(true);
  });
  it('viewer does NOT satisfy editor requirement', () => {
    expect(hasMinimumRole('viewer', 'editor')).toBe(false);
  });
  it('viewer does NOT satisfy admin requirement', () => {
    expect(hasMinimumRole('viewer', 'admin')).toBe(false);
  });
  it('unknown role does NOT satisfy any requirement', () => {
    expect(hasMinimumRole('unknown', 'viewer')).toBe(false);
  });
});

// ── GET /api/posts ─────────────────────────────────────────────────────────

describe('GET /api/posts (viewer+)', () => {
  it('allows viewer', async () => {
    const { token } = await registerUser('viewer@ex.com', 'password1', 'viewer');
    const res = await request(app)
      .get('/api/posts')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('posts');
  });

  it('allows editor', async () => {
    const { token } = await registerUser('editor@ex.com', 'password1', 'editor');
    const res = await request(app)
      .get('/api/posts')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(200);
  });

  it('allows admin', async () => {
    const { token } = await registerUser('admin@ex.com', 'password1', 'admin');
    const res = await request(app)
      .get('/api/posts')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(200);
  });

  it('returns 401 without token', async () => {
    const res = await request(app).get('/api/posts');
    expect(res.status).toBe(401);
  });
});

// ── POST /api/posts ────────────────────────────────────────────────────────

describe('POST /api/posts (editor+)', () => {
  it('allows editor to create a post', async () => {
    const { token } = await registerUser('editor@ex.com', 'password1', 'editor');
    const res = await request(app)
      .post('/api/posts')
      .set('Authorization', `Bearer ${token}`)
      .send({ title: 'My Post', content: 'Hello!' });
    expect(res.status).toBe(201);
    expect(res.body.post.title).toBe('My Post');
  });

  it('allows admin to create a post', async () => {
    const { token } = await registerUser('admin@ex.com', 'password1', 'admin');
    const res = await request(app)
      .post('/api/posts')
      .set('Authorization', `Bearer ${token}`)
      .send({ title: 'Admin Post', content: 'From admin' });
    expect(res.status).toBe(201);
  });

  it('returns 403 for viewer', async () => {
    const { token } = await registerUser('viewer@ex.com', 'password1', 'viewer');
    const res = await request(app)
      .post('/api/posts')
      .set('Authorization', `Bearer ${token}`)
      .send({ title: 'Viewer Post', content: 'Should fail' });
    expect(res.status).toBe(403);
  });

  it('returns 400 when title or content is missing', async () => {
    const { token } = await registerUser('editor@ex.com', 'password1', 'editor');
    const res = await request(app)
      .post('/api/posts')
      .set('Authorization', `Bearer ${token}`)
      .send({ title: 'No content' });
    expect(res.status).toBe(400);
  });
});

// ── DELETE /api/posts/:id ─────────────────────────────────────────────────

describe('DELETE /api/posts/:id (admin only)', () => {
  it('allows admin to delete a post', async () => {
    const { token } = await registerUser('admin@ex.com', 'password1', 'admin');
    const res = await request(app)
      .delete('/api/posts/1')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('deleted');
  });

  it('returns 403 for editor', async () => {
    const { token } = await registerUser('editor@ex.com', 'password1', 'editor');
    const res = await request(app)
      .delete('/api/posts/1')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(403);
  });

  it('returns 403 for viewer', async () => {
    const { token } = await registerUser('viewer@ex.com', 'password1', 'viewer');
    const res = await request(app)
      .delete('/api/posts/1')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(403);
  });

  it('returns 404 when post does not exist', async () => {
    const { token } = await registerUser('admin@ex.com', 'password1', 'admin');
    const res = await request(app)
      .delete('/api/posts/9999')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(404);
  });
});

// ── PUT /api/admin/users/:id/role ─────────────────────────────────────────

describe('PUT /api/admin/users/:id/role (admin only)', () => {
  it('allows admin to change a user role', async () => {
    const { token } = await registerUser('admin@ex.com', 'password1', 'admin');
    const { user: target } = await registerUser('target@ex.com', 'password1', 'viewer');

    const res = await request(app)
      .put(`/api/admin/users/${target.id}/role`)
      .set('Authorization', `Bearer ${token}`)
      .send({ role: 'editor' });

    expect(res.status).toBe(200);
    expect(res.body.user.role).toBe('editor');
  });

  it('returns 400 for invalid role', async () => {
    const { token } = await registerUser('admin@ex.com', 'password1', 'admin');
    const { user: target } = await registerUser('target@ex.com', 'password1', 'viewer');

    const res = await request(app)
      .put(`/api/admin/users/${target.id}/role`)
      .set('Authorization', `Bearer ${token}`)
      .send({ role: 'superuser' });

    expect(res.status).toBe(400);
  });

  it('returns 403 for non-admin', async () => {
    const { token } = await registerUser('editor@ex.com', 'password1', 'editor');
    const { user: target } = await registerUser('target@ex.com', 'password1', 'viewer');

    const res = await request(app)
      .put(`/api/admin/users/${target.id}/role`)
      .set('Authorization', `Bearer ${token}`)
      .send({ role: 'editor' });

    expect(res.status).toBe(403);
  });
});

// ── Token expiry / tampering ───────────────────────────────────────────────

describe('JWT security', () => {
  it('rejects a tampered token', async () => {
    const { token } = await registerUser('user@ex.com', 'password1', 'viewer');
    const tampered = token.slice(0, -5) + 'XXXXX';
    const res = await request(app)
      .get('/api/posts')
      .set('Authorization', `Bearer ${tampered}`);
    expect(res.status).toBe(401);
  });

  it('rejects an expired token', async () => {
    const user = UserModel.findByEmail('user@ex.com') ||
      (await registerUser('user2@ex.com', 'password1')).user;
    const jwt = require('jsonwebtoken');
    const expiredToken = jwt.sign(
      { id: user.id, role: user.role },
      process.env.JWT_SECRET,
      { expiresIn: -1 }
    );
    const res = await request(app)
      .get('/api/posts')
      .set('Authorization', `Bearer ${expiredToken}`);
    expect(res.status).toBe(401);
    expect(res.body.error).toMatch(/expired/i);
  });
});
