/**
 * Express application entry point.
 */

require('dotenv').config();

const express = require('express');
const { configurePassport, passport } = require('./auth/passport');
const authRoutes = require('./routes/auth');
const protectedRoutes = require('./routes/protected');
const teamRoutes = require('./routes/teams');

const app = express();

// ── Body parsing ──────────────────────────────────────────────────────────
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// ── Passport initialisation ───────────────────────────────────────────────
configurePassport();
app.use(passport.initialize());

// ── Routes ────────────────────────────────────────────────────────────────
app.use('/auth', authRoutes);
app.use('/api', protectedRoutes);
app.use('/api', teamRoutes);

// ── Health check ──────────────────────────────────────────────────────────
app.get('/health', (_req, res) => res.json({ status: 'ok' }));

// ── Error handler ─────────────────────────────────────────────────────────
// eslint-disable-next-line no-unused-vars
app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(500).json({ error: 'Internal server error' });
});

const PORT = process.env.PORT || 3000;

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
  });
}

module.exports = app;
