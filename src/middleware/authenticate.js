/**
 * authenticate middleware
 *
 * Extracts a Bearer JWT from the Authorization header, verifies it, looks up
 * the corresponding user, and attaches it to `req.user`.
 *
 * Usage:
 *   router.get('/secret', authenticate, handler)
 */

const { verifyToken } = require('../auth/jwt');
const UserModel = require('../models/user');

function authenticate(req, res, next) {
  const authHeader = req.headers['authorization'] || '';
  const [scheme, token] = authHeader.split(' ');

  if (!token || scheme.toLowerCase() !== 'bearer') {
    return res.status(401).json({ error: 'Missing or malformed Authorization header' });
  }

  let payload;
  try {
    payload = verifyToken(token);
  } catch (err) {
    if (err.name === 'TokenExpiredError') {
      return res.status(401).json({ error: 'Token expired' });
    }
    return res.status(401).json({ error: 'Invalid token' });
  }

  const user = UserModel.findById(payload.id);
  if (!user) {
    return res.status(401).json({ error: 'User not found' });
  }

  req.user = user;
  next();
}

module.exports = { authenticate };
