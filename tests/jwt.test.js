/**
 * Unit tests for src/auth/jwt.js
 *
 * Covers signToken and verifyToken directly, without going through HTTP routes.
 */

process.env.JWT_SECRET = 'unit-test-secret';
process.env.JWT_EXPIRES_IN = '1h';

const jwt = require('jsonwebtoken');
const { signToken, verifyToken } = require('../src/auth/jwt');

// ── signToken ─────────────────────────────────────────────────────────────

describe('signToken', () => {
  it('returns a string', () => {
    const token = signToken({ id: 'usr_1', role: 'viewer' });
    expect(typeof token).toBe('string');
  });

  it('produces a token that can be decoded with the correct secret', () => {
    const user = { id: 'usr_42', role: 'admin' };
    const token = signToken(user);
    const decoded = jwt.decode(token);
    expect(decoded.id).toBe(user.id);
    expect(decoded.role).toBe(user.role);
  });

  it('encodes id and role in the payload', () => {
    const token = signToken({ id: 'usr_99', role: 'editor' });
    const payload = verifyToken(token);
    expect(payload.id).toBe('usr_99');
    expect(payload.role).toBe('editor');
  });

  it('includes an expiry (exp) claim', () => {
    const token = signToken({ id: 'usr_1', role: 'viewer' });
    const decoded = jwt.decode(token);
    expect(decoded).toHaveProperty('exp');
    expect(decoded.exp).toBeGreaterThan(Math.floor(Date.now() / 1000));
  });

  it('uses HS256 algorithm', () => {
    const token = signToken({ id: 'usr_1', role: 'viewer' });
    const header = JSON.parse(
      Buffer.from(token.split('.')[0], 'base64url').toString()
    );
    expect(header.alg).toBe('HS256');
  });

  it('generates different tokens for different users', () => {
    const t1 = signToken({ id: 'usr_1', role: 'viewer' });
    const t2 = signToken({ id: 'usr_2', role: 'viewer' });
    expect(t1).not.toBe(t2);
  });
});

// ── verifyToken ───────────────────────────────────────────────────────────

describe('verifyToken', () => {
  it('returns the decoded payload for a valid token', () => {
    const user = { id: 'usr_5', role: 'admin' };
    const token = signToken(user);
    const payload = verifyToken(token);
    expect(payload.id).toBe(user.id);
    expect(payload.role).toBe(user.role);
  });

  it('throws JsonWebTokenError for a tampered token', () => {
    const token = signToken({ id: 'usr_1', role: 'viewer' });
    const tampered = token.slice(0, -5) + 'XXXXX';
    expect(() => verifyToken(tampered)).toThrow(jwt.JsonWebTokenError);
  });

  it('throws JsonWebTokenError for a token signed with a different secret', () => {
    const wrongSecretToken = jwt.sign(
      { id: 'usr_1', role: 'viewer' },
      'wrong-secret',
      { algorithm: 'HS256' }
    );
    expect(() => verifyToken(wrongSecretToken)).toThrow(jwt.JsonWebTokenError);
  });

  it('throws TokenExpiredError for an expired token', () => {
    const expiredToken = jwt.sign(
      { id: 'usr_1', role: 'viewer' },
      process.env.JWT_SECRET,
      { expiresIn: -1, algorithm: 'HS256' }
    );
    expect(() => verifyToken(expiredToken)).toThrow(jwt.TokenExpiredError);
  });

  it('throws JsonWebTokenError for a completely invalid string', () => {
    expect(() => verifyToken('not-a-token')).toThrow(jwt.JsonWebTokenError);
  });

  it('throws JsonWebTokenError for an empty string', () => {
    expect(() => verifyToken('')).toThrow();
  });
});
