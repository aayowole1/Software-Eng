/**
 * User model with role-based access control (RBAC).
 *
 * In production this would be backed by a database. For now we use an
 * in-memory store so the system is runnable without external dependencies.
 *
 * Roles (ordered by privilege level, highest first):
 *   admin  – full access
 *   editor – read + write access to content
 *   viewer – read-only access
 */

const ROLES = Object.freeze({
  ADMIN: 'admin',
  EDITOR: 'editor',
  VIEWER: 'viewer',
});

// Role hierarchy: a role implicitly has all permissions of lower roles.
const ROLE_HIERARCHY = {
  [ROLES.ADMIN]: 3,
  [ROLES.EDITOR]: 2,
  [ROLES.VIEWER]: 1,
};

// In-memory store keyed by provider + providerId (e.g. "google:12345")
// or by local email for password-based users.
const users = new Map();

/**
 * Find a user by their OAuth provider identity.
 * @param {string} provider  - OAuth provider name (e.g. 'google')
 * @param {string} providerId - Provider-assigned user id
 * @returns {object|undefined}
 */
function findByProvider(provider, providerId) {
  const key = `${provider}:${providerId}`;
  return users.get(key);
}

/**
 * Find a user by their local email address.
 * @param {string} email
 * @returns {object|undefined}
 */
function findByEmail(email) {
  for (const user of users.values()) {
    if (user.email === email) return user;
  }
  return undefined;
}

/**
 * Find a user by their internal id.
 * @param {string} id
 * @returns {object|undefined}
 */
function findById(id) {
  for (const user of users.values()) {
    if (user.id === id) return user;
  }
  return undefined;
}

/**
 * Create or update an OAuth user (upsert).
 * @param {object} profile - OAuth profile object
 * @param {string} provider - Provider name
 * @returns {object} Persisted user record
 */
function upsertOAuthUser({ provider, providerId, email, displayName, photo }) {
  const key = `${provider}:${providerId}`;
  const existing = users.get(key);
  if (existing) {
    existing.displayName = displayName;
    existing.photo = photo;
    return existing;
  }
  const user = {
    id: `usr_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    provider,
    providerId,
    email,
    displayName,
    photo,
    role: ROLES.VIEWER, // default role for new OAuth users
    createdAt: new Date().toISOString(),
  };
  users.set(key, user);
  return user;
}

/**
 * Create a local (email + password hash) user.
 * @param {string} email
 * @param {string} passwordHash - bcrypt hash
 * @param {string} [role]
 * @returns {object}
 */
function createLocalUser(email, passwordHash, role = ROLES.VIEWER) {
  if (findByEmail(email)) {
    throw new Error(`User with email ${email} already exists`);
  }
  const user = {
    id: `usr_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    provider: 'local',
    email,
    passwordHash,
    displayName: email,
    role,
    createdAt: new Date().toISOString(),
  };
  users.set(`local:${email}`, user);
  return user;
}

/**
 * Update the role of a user.
 * @param {string} id - Internal user id
 * @param {string} newRole
 * @returns {object} Updated user
 */
function setUserRole(id, newRole) {
  if (!Object.values(ROLES).includes(newRole)) {
    throw new Error(`Invalid role: ${newRole}`);
  }
  const user = findById(id);
  if (!user) throw new Error(`User not found: ${id}`);
  user.role = newRole;
  return user;
}

/**
 * Return true when `userRole` is at least as privileged as `requiredRole`.
 * @param {string} userRole
 * @param {string} requiredRole
 * @returns {boolean}
 */
function hasMinimumRole(userRole, requiredRole) {
  const userLevel = ROLE_HIERARCHY[userRole] ?? 0;
  const requiredLevel = ROLE_HIERARCHY[requiredRole] ?? Infinity;
  return userLevel >= requiredLevel;
}

/**
 * Clear all users (for testing only).
 */
function _reset() {
  users.clear();
}

module.exports = {
  ROLES,
  ROLE_HIERARCHY,
  findByProvider,
  findByEmail,
  findById,
  upsertOAuthUser,
  createLocalUser,
  setUserRole,
  hasMinimumRole,
  _reset,
};
