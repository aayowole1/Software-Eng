/**
 * Unit tests for src/auth/passport.js
 *
 * Tests the configurePassport function and the local strategy behaviour
 * by calling the strategy callback directly (without making HTTP requests).
 */

process.env.JWT_SECRET = 'unit-test-secret';

const bcrypt = require('bcryptjs');

// ── Helpers ───────────────────────────────────────────────────────────────

/**
 * Authenticate via the passport local strategy without an HTTP request.
 * Returns the arguments that would be passed to `done`.
 */
async function runLocalStrategy(passport, email, password) {
  return new Promise((resolve) => {
    const req = {
      body: { email, password },
      logIn: jest.fn(),
    };
    const strategy = passport._strategy('local');
    strategy.success = (user) => resolve([null, user]);
    strategy.fail = (info) => resolve([null, false, info]);
    strategy.error = (err) => resolve([err]);
    strategy.authenticate(req, {});
  });
}

// ── configurePassport ─────────────────────────────────────────────────────

describe('configurePassport', () => {
  beforeEach(() => {
    jest.resetModules();
  });

  it('executes without throwing', () => {
    const { configurePassport } = require('../src/auth/passport');
    expect(() => configurePassport()).not.toThrow();
  });

  it('returns undefined (no explicit return value)', () => {
    const { configurePassport } = require('../src/auth/passport');
    expect(configurePassport()).toBeUndefined();
  });

  it('exports the passport instance', () => {
    const { passport } = require('../src/auth/passport');
    expect(passport).toBeDefined();
    expect(typeof passport.use).toBe('function');
    expect(typeof passport.authenticate).toBe('function');
  });
});

// ── Local strategy callback ───────────────────────────────────────────────

describe('Local strategy callback', () => {
  let passport;
  let UserModel;

  beforeEach(() => {
    jest.resetModules();
    // Re-require after module reset so passport and UserModel share state
    const passportModule = require('../src/auth/passport');
    passport = passportModule.passport;
    UserModel = require('../src/models/user');
    UserModel._reset();
    passportModule.configurePassport();
  });

  it('calls done(null, user) when credentials are correct', async () => {
    const password = 'secure_pass_1';
    const hash = await bcrypt.hash(password, 10);
    UserModel.createLocalUser('test@example.com', hash);

    const result = await runLocalStrategy(passport, 'test@example.com', password);

    expect(result[0]).toBeNull();
    expect(result[1]).toMatchObject({ email: 'test@example.com' });
  });

  it('calls done(null, false) with Invalid credentials for wrong password', async () => {
    const hash = await bcrypt.hash('correct_password', 10);
    UserModel.createLocalUser('test@example.com', hash);

    const result = await runLocalStrategy(passport, 'test@example.com', 'wrong_password');

    expect(result[0]).toBeNull();
    expect(result[1]).toBe(false);
    expect(result[2]).toMatchObject({ message: 'Invalid credentials' });
  });

  it('calls done(null, false) with Invalid credentials for unknown email', async () => {
    const result = await runLocalStrategy(passport, 'nobody@example.com', 'any_password');

    expect(result[0]).toBeNull();
    expect(result[1]).toBe(false);
    expect(result[2]).toMatchObject({ message: 'Invalid credentials' });
  });

  it('calls done(null, false) for an OAuth user (no local passwordHash)', async () => {
    UserModel.upsertOAuthUser({
      provider: 'google',
      providerId: 'gid_oauth',
      email: 'oauth@example.com',
      displayName: 'OAuth User',
      photo: null,
    });

    const result = await runLocalStrategy(passport, 'oauth@example.com', 'any_password');

    expect(result[0]).toBeNull();
    expect(result[1]).toBe(false);
    expect(result[2]).toMatchObject({ message: 'Invalid credentials' });
  });
});

// ── Google OAuth strategy configuration ───────────────────────────────────

describe('Google OAuth strategy configuration', () => {
  beforeEach(() => {
    jest.resetModules();
    delete process.env.GOOGLE_CLIENT_ID;
    delete process.env.GOOGLE_CLIENT_SECRET;
  });

  afterEach(() => {
    delete process.env.GOOGLE_CLIENT_ID;
    delete process.env.GOOGLE_CLIENT_SECRET;
  });

  it('is NOT registered when GOOGLE_CLIENT_ID/SECRET are absent', () => {
    const { configurePassport, passport } = require('../src/auth/passport');
    configurePassport();

    expect(passport._strategy('google')).toBeUndefined();
  });

  it('IS registered when GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set', () => {
    process.env.GOOGLE_CLIENT_ID = 'test-client-id';
    process.env.GOOGLE_CLIENT_SECRET = 'test-client-secret';

    const { configurePassport, passport } = require('../src/auth/passport');
    configurePassport();

    expect(passport._strategy('google')).toBeDefined();
  });
});
