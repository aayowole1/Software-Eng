/**
 * Unit tests for the authenticate and authorize middleware.
 *
 * Tests the middleware functions directly using lightweight mock
 * req/res/next objects so no HTTP server is needed.
 */

process.env.JWT_SECRET = 'unit-test-secret';
process.env.JWT_EXPIRES_IN = '1h';

const jwt = require('jsonwebtoken');
const { authenticate } = require('../src/middleware/authenticate');
const { authorize } = require('../src/middleware/authorize');
const { signToken } = require('../src/auth/jwt');
const UserModel = require('../src/models/user');

// ── Helpers ───────────────────────────────────────────────────────────────

function makeRes() {
  const res = {};
  res.status = jest.fn().mockReturnValue(res);
  res.json = jest.fn().mockReturnValue(res);
  return res;
}

function makeReq(overrides = {}) {
  return {
    headers: {},
    ...overrides,
  };
}

beforeEach(() => {
  UserModel._reset();
});

// ── authenticate ──────────────────────────────────────────────────────────

describe('authenticate middleware', () => {
  it('calls next() and sets req.user when a valid token is provided', () => {
    const user = UserModel.createLocalUser('alice@example.com', 'hash');
    const token = signToken(user);
    const req = makeReq({ headers: { authorization: `Bearer ${token}` } });
    const res = makeRes();
    const next = jest.fn();

    authenticate(req, res, next);

    expect(next).toHaveBeenCalledTimes(1);
    expect(req.user).toBeDefined();
    expect(req.user.id).toBe(user.id);
  });

  it('returns 401 when Authorization header is missing', () => {
    const req = makeReq();
    const res = makeRes();
    const next = jest.fn();

    authenticate(req, res, next);

    expect(res.status).toHaveBeenCalledWith(401);
    expect(res.json).toHaveBeenCalledWith(
      expect.objectContaining({ error: expect.stringMatching(/Missing or malformed/i) })
    );
    expect(next).not.toHaveBeenCalled();
  });

  it('returns 401 when the scheme is not Bearer', () => {
    const req = makeReq({ headers: { authorization: 'Basic abc123' } });
    const res = makeRes();
    const next = jest.fn();

    authenticate(req, res, next);

    expect(res.status).toHaveBeenCalledWith(401);
    expect(next).not.toHaveBeenCalled();
  });

  it('returns 401 when the token is invalid', () => {
    const req = makeReq({ headers: { authorization: 'Bearer not-a-real-token' } });
    const res = makeRes();
    const next = jest.fn();

    authenticate(req, res, next);

    expect(res.status).toHaveBeenCalledWith(401);
    expect(res.json).toHaveBeenCalledWith(
      expect.objectContaining({ error: 'Invalid token' })
    );
    expect(next).not.toHaveBeenCalled();
  });

  it('returns 401 with "Token expired" when the token is expired', () => {
    const expiredToken = jwt.sign(
      { id: 'usr_x', role: 'viewer' },
      process.env.JWT_SECRET,
      { expiresIn: -1, algorithm: 'HS256' }
    );
    const req = makeReq({ headers: { authorization: `Bearer ${expiredToken}` } });
    const res = makeRes();
    const next = jest.fn();

    authenticate(req, res, next);

    expect(res.status).toHaveBeenCalledWith(401);
    expect(res.json).toHaveBeenCalledWith(
      expect.objectContaining({ error: 'Token expired' })
    );
    expect(next).not.toHaveBeenCalled();
  });

  it('returns 401 when the token payload references a non-existent user', () => {
    // Sign a token for a user id that is NOT in the store
    const ghostToken = jwt.sign(
      { id: 'usr_ghost_id', role: 'viewer' },
      process.env.JWT_SECRET,
      { algorithm: 'HS256' }
    );
    const req = makeReq({ headers: { authorization: `Bearer ${ghostToken}` } });
    const res = makeRes();
    const next = jest.fn();

    authenticate(req, res, next);

    expect(res.status).toHaveBeenCalledWith(401);
    expect(res.json).toHaveBeenCalledWith(
      expect.objectContaining({ error: 'User not found' })
    );
    expect(next).not.toHaveBeenCalled();
  });
});

// ── authorize ─────────────────────────────────────────────────────────────

describe('authorize middleware factory', () => {
  it('calls next() when the user meets the required role', () => {
    const req = makeReq({ user: { role: 'admin' } });
    const res = makeRes();
    const next = jest.fn();

    authorize('viewer')(req, res, next);

    expect(next).toHaveBeenCalledTimes(1);
    expect(res.status).not.toHaveBeenCalled();
  });

  it('calls next() when the user role exactly matches the required role', () => {
    const req = makeReq({ user: { role: 'editor' } });
    const res = makeRes();
    const next = jest.fn();

    authorize('editor')(req, res, next);

    expect(next).toHaveBeenCalledTimes(1);
  });

  it('returns 403 when the user role is below the required role', () => {
    const req = makeReq({ user: { role: 'viewer' } });
    const res = makeRes();
    const next = jest.fn();

    authorize('editor')(req, res, next);

    expect(res.status).toHaveBeenCalledWith(403);
    expect(res.json).toHaveBeenCalledWith(
      expect.objectContaining({ error: expect.stringMatching(/Insufficient permissions/i) })
    );
    expect(next).not.toHaveBeenCalled();
  });

  it('returns 403 when viewer tries to access an admin-only resource', () => {
    const req = makeReq({ user: { role: 'viewer' } });
    const res = makeRes();
    const next = jest.fn();

    authorize('admin')(req, res, next);

    expect(res.status).toHaveBeenCalledWith(403);
    expect(next).not.toHaveBeenCalled();
  });

  it('returns 401 when req.user is not set', () => {
    const req = makeReq(); // no user property
    const res = makeRes();
    const next = jest.fn();

    authorize('viewer')(req, res, next);

    expect(res.status).toHaveBeenCalledWith(401);
    expect(res.json).toHaveBeenCalledWith(
      expect.objectContaining({ error: 'Not authenticated' })
    );
    expect(next).not.toHaveBeenCalled();
  });

  it('returns 401 when req.user is explicitly null', () => {
    const req = makeReq({ user: null });
    const res = makeRes();
    const next = jest.fn();

    authorize('viewer')(req, res, next);

    expect(res.status).toHaveBeenCalledWith(401);
    expect(next).not.toHaveBeenCalled();
  });

  it('includes the required role in the 403 error message', () => {
    const req = makeReq({ user: { role: 'viewer' } });
    const res = makeRes();
    const next = jest.fn();

    authorize('admin')(req, res, next);

    const errorBody = res.json.mock.calls[0][0];
    expect(errorBody.error).toContain('admin');
  });

  it('returns a reusable middleware function', () => {
    const middleware = authorize('editor');
    expect(typeof middleware).toBe('function');
  });
});
