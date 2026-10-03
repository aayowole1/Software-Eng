/**
 * Passport.js configuration.
 *
 * Strategies configured:
 *   1. google  – OAuth 2.0 / OIDC via passport-google-oauth20
 *   2. local   – email + password (bcrypt) via passport-local
 */

const passport = require('passport');
const GoogleStrategy = require('passport-google-oauth20').Strategy;
const LocalStrategy = require('passport-local').Strategy;
const bcrypt = require('bcryptjs');
const UserModel = require('../models/user');

function configurePassport() {
  // ── Google OAuth 2.0 ──────────────────────────────────────────────────────
  if (process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET) {
    passport.use(
      new GoogleStrategy(
        {
          clientID: process.env.GOOGLE_CLIENT_ID,
          clientSecret: process.env.GOOGLE_CLIENT_SECRET,
          callbackURL: process.env.GOOGLE_CALLBACK_URL || '/auth/google/callback',
          scope: ['profile', 'email'],
        },
        (_accessToken, _refreshToken, profile, done) => {
          try {
            const email =
              profile.emails && profile.emails[0]
                ? profile.emails[0].value
                : null;
            const photo =
              profile.photos && profile.photos[0]
                ? profile.photos[0].value
                : null;

            const user = UserModel.upsertOAuthUser({
              provider: 'google',
              providerId: profile.id,
              email,
              displayName: profile.displayName,
              photo,
            });
            return done(null, user);
          } catch (err) {
            return done(err);
          }
        }
      )
    );
  }

  // ── Local strategy (email + password) ────────────────────────────────────
  passport.use(
    new LocalStrategy(
      { usernameField: 'email', passwordField: 'password' },
      async (email, password, done) => {
        try {
          const user = UserModel.findByEmail(email);
          if (!user) {
            return done(null, false, { message: 'Invalid credentials' });
          }
          if (user.provider !== 'local' || !user.passwordHash) {
            return done(null, false, { message: 'Invalid credentials' });
          }
          const match = await bcrypt.compare(password, user.passwordHash);
          if (!match) {
            return done(null, false, { message: 'Invalid credentials' });
          }
          return done(null, user);
        } catch (err) {
          return done(err);
        }
      }
    )
  );
}

module.exports = { configurePassport, passport };
