/**
 * Auth routes
 *
 * POST /auth/register      – create a local account (email + password)
 * POST /auth/login         – local login → returns JWT
 * GET  /auth/google        – initiate Google OAuth flow
 * GET  /auth/google/callback – Google OAuth callback → returns JWT
 * GET  /auth/me            – return current user profile (requires auth)
 */

const express = require('express');
const bcrypt = require('bcryptjs');
const { passport } = require('../auth/passport');
const { signToken } = require('../auth/jwt');
const { authenticate } = require('../middleware/authenticate');
const UserModel = require('../models/user');

const router = express.Router();

// ── Local registration ────────────────────────────────────────────────────

router.post('/register', async (req, res) => {
  const { email, password } = req.body || {};
  if (!email || !password) {
    return res.status(400).json({ error: 'email and password are required' });
  }
  if (password.length < 8) {
    return res.status(400).json({ error: 'password must be at least 8 characters' });
  }
  if (UserModel.findByEmail(email)) {
    return res.status(409).json({ error: 'Email already registered' });
  }
  try {
    const passwordHash = await bcrypt.hash(password, 10);
    const user = UserModel.createLocalUser(email, passwordHash);
    const token = signToken(user);
    return res.status(201).json({ token, user: publicProfile(user) });
  } catch (err) {
    return res.status(500).json({ error: 'Registration failed' });
  }
});

// ── Local login ───────────────────────────────────────────────────────────

router.post('/login', (req, res, next) => {
  passport.authenticate('local', { session: false }, (err, user, info) => {
    if (err) return next(err);
    if (!user) {
      return res.status(401).json({ error: (info && info.message) || 'Invalid credentials' });
    }
    const token = signToken(user);
    return res.json({ token, user: publicProfile(user) });
  })(req, res, next);
});

// ── Google OAuth ──────────────────────────────────────────────────────────

router.get(
  '/google',
  passport.authenticate('google', { session: false, scope: ['profile', 'email'] })
);

router.get(
  '/google/callback',
  passport.authenticate('google', { session: false, failureRedirect: '/auth/failure' }),
  (req, res) => {
    const token = signToken(req.user);
    // In a real app you might redirect to a frontend URL with the token as a
    // query param or via a short-lived cookie.
    return res.json({ token, user: publicProfile(req.user) });
  }
);

router.get('/failure', (_req, res) => {
  res.status(401).json({ error: 'OAuth authentication failed' });
});

// ── Current user ──────────────────────────────────────────────────────────

router.get('/me', authenticate, (req, res) => {
  return res.json({ user: publicProfile(req.user) });
});

// ── Helpers ───────────────────────────────────────────────────────────────

function publicProfile(user) {
  const { passwordHash: _omit, ...safe } = user;
  return safe;
}

module.exports = router;
