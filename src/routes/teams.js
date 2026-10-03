/**
 * Team and membership routes.
 *
 * Teams
 * ─────────────────────────────────────────────────────────────────────────
 * POST   /api/teams                       – create a team          (editor+)
 * GET    /api/teams                       – list all teams          (viewer+)
 * GET    /api/teams/:id                   – get team + roster       (viewer+)
 * DELETE /api/teams/:id                   – delete a team           (admin)
 *
 * Membership
 * ─────────────────────────────────────────────────────────────────────────
 * POST   /api/teams/:id/members           – add member to team      (admin)
 * DELETE /api/teams/:id/members/:userId   – remove member from team (admin)
 * GET    /api/users/:userId/teams         – list teams for a user   (viewer+)
 */

const express = require('express');
const { authenticate } = require('../middleware/authenticate');
const { authorize } = require('../middleware/authorize');
const TeamModel = require('../models/team');
const MembershipModel = require('../models/membership');
const UserModel = require('../models/user');

const router = express.Router();

// ── Teams ─────────────────────────────────────────────────────────────────

/**
 * POST /api/teams
 * Create a new team. The authenticated user becomes the team owner.
 * Requires: editor or admin role.
 */
router.post('/teams', authenticate, authorize('editor'), (req, res) => {
  const { name, description } = req.body || {};
  if (!name || typeof name !== 'string' || name.trim() === '') {
    return res.status(400).json({ error: 'name is required' });
  }
  try {
    const team = TeamModel.createTeam(name.trim(), description, req.user.id);
    // Automatically add creator as owner
    const membership = MembershipModel.addMember(team.id, req.user.id, MembershipModel.TEAM_ROLES.OWNER);
    res.status(201).json({ team, membership });
  } catch (err) {
    if (err.message.startsWith('Team with name')) {
      return res.status(409).json({ error: err.message });
    }
    res.status(500).json({ error: 'Failed to create team' });
  }
});

/**
 * GET /api/teams
 * List all teams. Requires: viewer+.
 */
router.get('/teams', authenticate, authorize('viewer'), (_req, res) => {
  const teams = TeamModel.listAll();
  res.json({ teams });
});

/**
 * GET /api/teams/:id
 * Get a team's details along with its full roster.
 * Each roster entry includes the user's public profile + teamRole.
 * Requires: viewer+.
 */
router.get('/teams/:id', authenticate, authorize('viewer'), (req, res) => {
  const team = TeamModel.findById(req.params.id);
  if (!team) return res.status(404).json({ error: 'Team not found' });

  const roster = MembershipModel.getRoster(team.id).map((m) => {
    const user = UserModel.findById(m.userId);
    return {
      userId: m.userId,
      teamRole: m.teamRole,
      joinedAt: m.joinedAt,
      displayName: user ? user.displayName : null,
      email: user ? user.email : null,
    };
  });

  res.json({ team, roster });
});

/**
 * DELETE /api/teams/:id
 * Delete a team and all its memberships. Requires: admin.
 */
router.delete('/teams/:id', authenticate, authorize('admin'), (req, res) => {
  const team = TeamModel.findById(req.params.id);
  if (!team) return res.status(404).json({ error: 'Team not found' });

  MembershipModel.removeTeamMemberships(team.id);
  TeamModel.deleteTeam(team.id);
  res.json({ deleted: team });
});

// ── Membership ────────────────────────────────────────────────────────────

/**
 * POST /api/teams/:id/members
 * Add a user to a team.
 * Body: { userId, teamRole? }
 * Requires: admin.
 */
router.post('/teams/:id/members', authenticate, authorize('admin'), (req, res) => {
  const team = TeamModel.findById(req.params.id);
  if (!team) return res.status(404).json({ error: 'Team not found' });

  const { userId, teamRole } = req.body || {};
  if (!userId) return res.status(400).json({ error: 'userId is required' });

  const user = UserModel.findById(userId);
  if (!user) return res.status(404).json({ error: 'User not found' });

  try {
    const membership = MembershipModel.addMember(team.id, userId, teamRole);
    res.status(201).json({ membership });
  } catch (err) {
    if (err.message.startsWith('User') && err.message.includes('already a member')) {
      return res.status(409).json({ error: err.message });
    }
    if (err.message.startsWith('Invalid team role')) {
      return res.status(400).json({ error: err.message });
    }
    res.status(500).json({ error: 'Failed to add member' });
  }
});

/**
 * DELETE /api/teams/:id/members/:userId
 * Remove a user from a team. Requires: admin.
 */
router.delete('/teams/:id/members/:userId', authenticate, authorize('admin'), (req, res) => {
  const team = TeamModel.findById(req.params.id);
  if (!team) return res.status(404).json({ error: 'Team not found' });

  const removed = MembershipModel.removeMember(team.id, req.params.userId);
  if (!removed) return res.status(404).json({ error: 'Membership not found' });

  res.json({ message: 'Member removed', teamId: team.id, userId: req.params.userId });
});

// ── User team listing ─────────────────────────────────────────────────────

/**
 * GET /api/users/:userId/teams
 * List all teams a specific user belongs to.
 * Requires: viewer+.
 */
router.get('/users/:userId/teams', authenticate, authorize('viewer'), (req, res) => {
  const user = UserModel.findById(req.params.userId);
  if (!user) return res.status(404).json({ error: 'User not found' });

  const memberships = MembershipModel.getUserMemberships(req.params.userId);
  const result = memberships.map((m) => {
    const team = TeamModel.findById(m.teamId);
    return { ...m, teamName: team ? team.name : null };
  });

  res.json({ userId: req.params.userId, teams: result });
});

module.exports = router;
