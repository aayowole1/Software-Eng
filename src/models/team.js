/**
 * Team model for membership and roster management.
 *
 * In production this would be backed by a database. For now we use an
 * in-memory store so the system is runnable without external dependencies.
 *
 * A team has a name, optional description, and a set of members stored
 * in the separate membership model.
 */

const teams = new Map();

/**
 * Find a team by id.
 * @param {string} id
 * @returns {object|undefined}
 */
function findById(id) {
  return teams.get(id);
}

/**
 * Return all teams as an array.
 * @returns {object[]}
 */
function listAll() {
  return Array.from(teams.values());
}

/**
 * Create a new team.
 * @param {string} name        - Unique team name
 * @param {string} description - Optional description
 * @param {string} createdBy   - User id of the creator
 * @returns {object} The created team record
 */
function createTeam(name, description, createdBy) {
  for (const t of teams.values()) {
    if (t.name === name) {
      throw new Error(`Team with name "${name}" already exists`);
    }
  }
  const team = {
    id: `team_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    name,
    description: description || '',
    createdBy,
    createdAt: new Date().toISOString(),
  };
  teams.set(team.id, team);
  return team;
}

/**
 * Delete a team by id.
 * @param {string} id
 * @returns {boolean} true if deleted, false if not found
 */
function deleteTeam(id) {
  return teams.delete(id);
}

/**
 * Clear all teams (for testing only).
 */
function _reset() {
  teams.clear();
}

module.exports = {
  findById,
  listAll,
  createTeam,
  deleteTeam,
  _reset,
};
