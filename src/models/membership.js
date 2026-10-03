/**
 * Membership model — links users to teams with a team-level role.
 *
 * Team roles:
 *   owner  – created the team; can manage membership and delete the team
 *   member – regular participant in the team
 *
 * System-level RBAC (admin / editor / viewer) is independent of team roles
 * and is enforced separately via the authorize middleware.
 */

const TEAM_ROLES = Object.freeze({
  OWNER: 'owner',
  MEMBER: 'member',
});

// memberships is a Map keyed by `${teamId}:${userId}` → membership record
const memberships = new Map();

/**
 * Add a user to a team.
 * @param {string} teamId
 * @param {string} userId
 * @param {string} [teamRole] - 'owner' or 'member' (default: 'member')
 * @returns {object} The created membership record
 */
function addMember(teamId, userId, teamRole = TEAM_ROLES.MEMBER) {
  if (!Object.values(TEAM_ROLES).includes(teamRole)) {
    throw new Error(`Invalid team role: ${teamRole}`);
  }
  const key = `${teamId}:${userId}`;
  if (memberships.has(key)) {
    throw new Error(`User ${userId} is already a member of team ${teamId}`);
  }
  const membership = {
    teamId,
    userId,
    teamRole,
    joinedAt: new Date().toISOString(),
  };
  memberships.set(key, membership);
  return membership;
}

/**
 * Remove a user from a team.
 * @param {string} teamId
 * @param {string} userId
 * @returns {boolean} true if removed, false if membership not found
 */
function removeMember(teamId, userId) {
  return memberships.delete(`${teamId}:${userId}`);
}

/**
 * Get a single membership record.
 * @param {string} teamId
 * @param {string} userId
 * @returns {object|undefined}
 */
function getMembership(teamId, userId) {
  return memberships.get(`${teamId}:${userId}`);
}

/**
 * List all memberships for a given team (the roster).
 * @param {string} teamId
 * @returns {object[]}
 */
function getRoster(teamId) {
  const result = [];
  for (const m of memberships.values()) {
    if (m.teamId === teamId) result.push(m);
  }
  return result;
}

/**
 * List all teams a user belongs to.
 * @param {string} userId
 * @returns {object[]}
 */
function getUserMemberships(userId) {
  const result = [];
  for (const m of memberships.values()) {
    if (m.userId === userId) result.push(m);
  }
  return result;
}

/**
 * Remove all memberships belonging to a team (used when deleting a team).
 * @param {string} teamId
 */
function removeTeamMemberships(teamId) {
  for (const [key, m] of memberships.entries()) {
    if (m.teamId === teamId) memberships.delete(key);
  }
}

/**
 * Clear all memberships (for testing only).
 */
function _reset() {
  memberships.clear();
}

module.exports = {
  TEAM_ROLES,
  addMember,
  removeMember,
  getMembership,
  getRoster,
  getUserMemberships,
  removeTeamMemberships,
  _reset,
};
