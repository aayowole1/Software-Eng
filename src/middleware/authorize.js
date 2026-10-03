/**
 * authorize middleware factory
 *
 * Returns a middleware that allows the request only when the authenticated
 * user's role meets or exceeds the required minimum role.
 *
 * Must be used after `authenticate`.
 *
 * Usage:
 *   router.delete('/posts/:id', authenticate, authorize('admin'), handler)
 *   router.put('/posts/:id',    authenticate, authorize('editor'), handler)
 *   router.get('/posts',        authenticate, authorize('viewer'), handler)
 */

const { hasMinimumRole } = require('../models/user');

/**
 * @param {string} requiredRole - Minimum role required ('admin'|'editor'|'viewer')
 * @returns {Function} Express middleware
 */
function authorize(requiredRole) {
  return function (req, res, next) {
    if (!req.user) {
      return res.status(401).json({ error: 'Not authenticated' });
    }
    if (!hasMinimumRole(req.user.role, requiredRole)) {
      return res.status(403).json({
        error: `Insufficient permissions. Required role: ${requiredRole}`,
      });
    }
    next();
  };
}

module.exports = { authorize };
