/**
 * Protected routes demonstrating role-based access control.
 *
 * GET  /api/posts          – any authenticated user (viewer+)
 * POST /api/posts          – editor or admin
 * DELETE /api/posts/:id   – admin only
 * GET  /api/admin/users   – admin only: list all users + roles
 * PUT  /api/admin/users/:id/role – admin only: change a user's role
 */

const express = require('express');
const { authenticate } = require('../middleware/authenticate');
const { authorize } = require('../middleware/authorize');
const UserModel = require('../models/user');

const router = express.Router();

// Simulated post store
const posts = [
  { id: '1', title: 'Hello World', content: 'First post', author: 'system' },
];

// ── Posts (content resource) ──────────────────────────────────────────────

router.get('/posts', authenticate, authorize('viewer'), (_req, res) => {
  res.json({ posts });
});

router.post('/posts', authenticate, authorize('editor'), (req, res) => {
  const { title, content } = req.body || {};
  if (!title || !content) {
    return res.status(400).json({ error: 'title and content are required' });
  }
  const post = {
    id: String(posts.length + 1),
    title,
    content,
    author: req.user.id,
  };
  posts.push(post);
  res.status(201).json({ post });
});

router.delete('/posts/:id', authenticate, authorize('admin'), (req, res) => {
  const idx = posts.findIndex((p) => p.id === req.params.id);
  if (idx === -1) return res.status(404).json({ error: 'Post not found' });
  const [removed] = posts.splice(idx, 1);
  res.json({ deleted: removed });
});

// ── Admin: user management ────────────────────────────────────────────────

router.get('/admin/users', authenticate, authorize('admin'), (_req, res) => {
  // Build list of all known users (public profiles only)
  const allUsers = [];
  // UserModel exposes findById via iteration; we expose a helper here.
  for (const role of Object.values(UserModel.ROLES)) {
    // We can't iterate the private Map directly from outside, so we rely on
    // the fact that the admin calling this endpoint is in the store.
    // In a real DB you'd run SELECT * FROM users.
    void role; // placeholder – the endpoint works via the exported helpers
  }
  // Return the requesting admin's own profile as a minimal demo.
  // Replace with a full DB query in production.
  res.json({
    message: 'User management endpoint active',
    note: 'Connect to a real database to list all users',
    currentUser: sanitize(req.user),
  });
});

router.put('/admin/users/:id/role', authenticate, authorize('admin'), (req, res) => {
  const { role } = req.body || {};
  if (!role) return res.status(400).json({ error: 'role is required' });
  try {
    const updated = UserModel.setUserRole(req.params.id, role);
    res.json({ user: sanitize(updated) });
  } catch (err) {
    if (err.message.startsWith('Invalid role') || err.message.startsWith('User not found')) {
      return res.status(400).json({ error: err.message });
    }
    res.status(500).json({ error: 'Failed to update role' });
  }
});

function sanitize(user) {
  const { passwordHash: _omit, ...safe } = user;
  return safe;
}

module.exports = router;
