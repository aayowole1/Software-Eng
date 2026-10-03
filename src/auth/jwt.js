/**
 * JWT utility functions.
 *
 * Tokens are signed with the HS256 algorithm using the JWT_SECRET
 * environment variable.  The payload contains:
 *   id   – internal user id
 *   role – user's current role
 */

const jwt = require('jsonwebtoken');

const SECRET = process.env.JWT_SECRET || 'default-dev-secret-change-me';
const EXPIRES_IN = process.env.JWT_EXPIRES_IN || '1h';

/**
 * Sign a JWT for the given user.
 * @param {object} user - Must contain `id` and `role`
 * @returns {string} Signed JWT string
 */
function signToken(user) {
  return jwt.sign(
    { id: user.id, role: user.role },
    SECRET,
    { expiresIn: EXPIRES_IN, algorithm: 'HS256' }
  );
}

/**
 * Verify and decode a JWT.
 * @param {string} token
 * @returns {object} Decoded payload
 * @throws {JsonWebTokenError|TokenExpiredError} on invalid/expired token
 */
function verifyToken(token) {
  return jwt.verify(token, SECRET, { algorithms: ['HS256'] });
}

module.exports = { signToken, verifyToken };
