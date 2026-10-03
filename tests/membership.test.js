/**
 * Tests for membership and roster routes (SCRUM-14).
 *
 * Covers:
 *  - Team model unit tests
 *  - Membership model unit tests
 *  - POST   /api/teams
 *  - GET    /api/teams
 *  - GET    /api/teams/:id  (roster)
 *  - DELETE /api/teams/:id
 *  - POST   /api/teams/:id/members
 *  - DELETE /api/teams/:id/members/:userId
 *  - GET    /api/users/:userId/teams
 */

process.env.JWT_SECRET = 'test-secret';
process.env.JWT_EXPIRES_IN = '1h';

const request = require('supertest');
const app = require('../src/app');
const UserModel = require('../src/models/user');
const TeamModel = require('../src/models/team');
const MembershipModel = require('../src/models/membership');
const { signToken } = require('../src/auth/jwt');

// ── Helpers ───────────────────────────────────────────────────────────────

async function registerUser(email, password, role) {
  const res = await request(app)
    .post('/auth/register')
    .send({ email, password });
  const user = UserModel.findByEmail(email);
  if (role && role !== UserModel.ROLES.VIEWER) {
    UserModel.setUserRole(user.id, role);
    user.role = role;
  }
  return { token: signToken(user), user };
}

beforeEach(() => {
  UserModel._reset();
  TeamModel._reset();
  MembershipModel._reset();
});

// ── TeamModel unit tests ──────────────────────────────────────────────────

describe('TeamModel', () => {
  it('creates a team and retrieves it by id', () => {
    const team = TeamModel.createTeam('Alpha', 'First team', 'user1');
    expect(team.name).toBe('Alpha');
    expect(team.description).toBe('First team');
    expect(team.createdBy).toBe('user1');
    expect(TeamModel.findById(team.id)).toEqual(team);
  });

  it('throws when a duplicate team name is used', () => {
    TeamModel.createTeam('Alpha', '', 'user1');
    expect(() => TeamModel.createTeam('Alpha', '', 'user2')).toThrow(/already exists/);
  });

  it('listAll returns all created teams', () => {
    TeamModel.createTeam('Alpha', '', 'user1');
    TeamModel.createTeam('Beta', '', 'user1');
    expect(TeamModel.listAll()).toHaveLength(2);
  });

  it('deleteTeam removes the team', () => {
    const team = TeamModel.createTeam('Alpha', '', 'user1');
    expect(TeamModel.deleteTeam(team.id)).toBe(true);
    expect(TeamModel.findById(team.id)).toBeUndefined();
  });

  it('deleteTeam returns false for unknown id', () => {
    expect(TeamModel.deleteTeam('nonexistent')).toBe(false);
  });
});

// ── MembershipModel unit tests ────────────────────────────────────────────

describe('MembershipModel', () => {
  const TEAM_ID = 'team_1';
  const USER_A = 'user_a';
  const USER_B = 'user_b';

  it('adds a member and retrieves the membership', () => {
    const m = MembershipModel.addMember(TEAM_ID, USER_A, 'owner');
    expect(m.teamId).toBe(TEAM_ID);
    expect(m.userId).toBe(USER_A);
    expect(m.teamRole).toBe('owner');
    expect(MembershipModel.getMembership(TEAM_ID, USER_A)).toEqual(m);
  });

  it('defaults teamRole to member', () => {
    const m = MembershipModel.addMember(TEAM_ID, USER_A);
    expect(m.teamRole).toBe('member');
  });

  it('throws for invalid teamRole', () => {
    expect(() => MembershipModel.addMember(TEAM_ID, USER_A, 'superuser')).toThrow(/Invalid team role/);
  });

  it('throws when adding a duplicate member', () => {
    MembershipModel.addMember(TEAM_ID, USER_A, 'member');
    expect(() => MembershipModel.addMember(TEAM_ID, USER_A, 'member')).toThrow(/already a member/);
  });

  it('removeMember returns true and clears the record', () => {
    MembershipModel.addMember(TEAM_ID, USER_A);
    expect(MembershipModel.removeMember(TEAM_ID, USER_A)).toBe(true);
    expect(MembershipModel.getMembership(TEAM_ID, USER_A)).toBeUndefined();
  });

  it('removeMember returns false when membership does not exist', () => {
    expect(MembershipModel.removeMember(TEAM_ID, 'unknown')).toBe(false);
  });

  it('getRoster returns all members of a team', () => {
    MembershipModel.addMember(TEAM_ID, USER_A, 'owner');
    MembershipModel.addMember(TEAM_ID, USER_B, 'member');
    const roster = MembershipModel.getRoster(TEAM_ID);
    expect(roster).toHaveLength(2);
    expect(roster.map((m) => m.userId)).toContain(USER_A);
    expect(roster.map((m) => m.userId)).toContain(USER_B);
  });

  it('getUserMemberships returns all teams a user belongs to', () => {
    MembershipModel.addMember('team_1', USER_A, 'owner');
    MembershipModel.addMember('team_2', USER_A, 'member');
    MembershipModel.addMember('team_1', USER_B, 'member');
    expect(MembershipModel.getUserMemberships(USER_A)).toHaveLength(2);
    expect(MembershipModel.getUserMemberships(USER_B)).toHaveLength(1);
  });

  it('removeTeamMemberships clears all members of a team', () => {
    MembershipModel.addMember(TEAM_ID, USER_A, 'owner');
    MembershipModel.addMember(TEAM_ID, USER_B, 'member');
    MembershipModel.removeTeamMemberships(TEAM_ID);
    expect(MembershipModel.getRoster(TEAM_ID)).toHaveLength(0);
  });
});

// ── POST /api/teams ───────────────────────────────────────────────────────

describe('POST /api/teams', () => {
  it('editor can create a team and becomes its owner', async () => {
    const { token, user } = await registerUser('ed@ex.com', 'password1', 'editor');
    const res = await request(app)
      .post('/api/teams')
      .set('Authorization', `Bearer ${token}`)
      .send({ name: 'Dev Team', description: 'Developers' });

    expect(res.status).toBe(201);
    expect(res.body.team.name).toBe('Dev Team');
    expect(res.body.team.createdBy).toBe(user.id);
    expect(res.body.membership.teamRole).toBe('owner');
    expect(res.body.membership.userId).toBe(user.id);
  });

  it('admin can create a team', async () => {
    const { token } = await registerUser('admin@ex.com', 'password1', 'admin');
    const res = await request(app)
      .post('/api/teams')
      .set('Authorization', `Bearer ${token}`)
      .send({ name: 'Ops Team' });

    expect(res.status).toBe(201);
    expect(res.body.team.name).toBe('Ops Team');
    expect(res.body.team.description).toBe('');
  });

  it('returns 403 for viewer', async () => {
    const { token } = await registerUser('viewer@ex.com', 'password1', 'viewer');
    const res = await request(app)
      .post('/api/teams')
      .set('Authorization', `Bearer ${token}`)
      .send({ name: 'Should Fail' });

    expect(res.status).toBe(403);
  });

  it('returns 401 without a token', async () => {
    const res = await request(app).post('/api/teams').send({ name: 'No Auth' });
    expect(res.status).toBe(401);
  });

  it('returns 400 when name is missing', async () => {
    const { token } = await registerUser('ed@ex.com', 'password1', 'editor');
    const res = await request(app)
      .post('/api/teams')
      .set('Authorization', `Bearer ${token}`)
      .send({ description: 'No name' });

    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/name is required/);
  });

  it('returns 400 when name is an empty string', async () => {
    const { token } = await registerUser('ed@ex.com', 'password1', 'editor');
    const res = await request(app)
      .post('/api/teams')
      .set('Authorization', `Bearer ${token}`)
      .send({ name: '   ' });

    expect(res.status).toBe(400);
  });

  it('returns 409 when team name already exists', async () => {
    const { token } = await registerUser('ed@ex.com', 'password1', 'editor');
    await request(app)
      .post('/api/teams')
      .set('Authorization', `Bearer ${token}`)
      .send({ name: 'Duplicate' });

    const res = await request(app)
      .post('/api/teams')
      .set('Authorization', `Bearer ${token}`)
      .send({ name: 'Duplicate' });

    expect(res.status).toBe(409);
  });
});

// ── GET /api/teams ────────────────────────────────────────────────────────

describe('GET /api/teams', () => {
  it('viewer can list teams', async () => {
    const { token: edToken } = await registerUser('ed@ex.com', 'password1', 'editor');
    // Create some teams
    await request(app)
      .post('/api/teams')
      .set('Authorization', `Bearer ${edToken}`)
      .send({ name: 'Alpha' });
    await request(app)
      .post('/api/teams')
      .set('Authorization', `Bearer ${edToken}`)
      .send({ name: 'Beta' });

    const { token: vwToken } = await registerUser('viewer@ex.com', 'password1', 'viewer');
    const res = await request(app)
      .get('/api/teams')
      .set('Authorization', `Bearer ${vwToken}`);

    expect(res.status).toBe(200);
    expect(res.body.teams).toHaveLength(2);
  });

  it('returns an empty array when no teams exist', async () => {
    const { token } = await registerUser('viewer@ex.com', 'password1', 'viewer');
    const res = await request(app)
      .get('/api/teams')
      .set('Authorization', `Bearer ${token}`);

    expect(res.status).toBe(200);
    expect(res.body.teams).toEqual([]);
  });

  it('returns 401 without a token', async () => {
    const res = await request(app).get('/api/teams');
    expect(res.status).toBe(401);
  });
});

// ── GET /api/teams/:id ────────────────────────────────────────────────────

describe('GET /api/teams/:id (roster)', () => {
  let edToken, adminToken, teamId, editorUser, memberUser;

  beforeEach(async () => {
    const ed = await registerUser('ed@ex.com', 'password1', 'editor');
    edToken = ed.token;
    editorUser = ed.user;
    const adm = await registerUser('admin@ex.com', 'password1', 'admin');
    adminToken = adm.token;
    const member = await registerUser('member@ex.com', 'password1', 'viewer');
    memberUser = member.user;

    // Create a team (editor becomes owner)
    const createRes = await request(app)
      .post('/api/teams')
      .set('Authorization', `Bearer ${edToken}`)
      .send({ name: 'Dev Team' });
    teamId = createRes.body.team.id;

    // Admin adds the viewer as a team member
    await request(app)
      .post(`/api/teams/${teamId}/members`)
      .set('Authorization', `Bearer ${adminToken}`)
      .send({ userId: memberUser.id });
  });

  it('returns team details and roster', async () => {
    const res = await request(app)
      .get(`/api/teams/${teamId}`)
      .set('Authorization', `Bearer ${edToken}`);

    expect(res.status).toBe(200);
    expect(res.body.team.name).toBe('Dev Team');
    expect(res.body.roster).toHaveLength(2);
    const roles = res.body.roster.map((r) => r.teamRole);
    expect(roles).toContain('owner');
    expect(roles).toContain('member');
  });

  it('includes user display names and emails in roster', async () => {
    const res = await request(app)
      .get(`/api/teams/${teamId}`)
      .set('Authorization', `Bearer ${edToken}`);

    const ownerEntry = res.body.roster.find((r) => r.userId === editorUser.id);
    expect(ownerEntry.email).toBe('ed@ex.com');
    expect(ownerEntry.displayName).toBeDefined();
  });

  it('returns 404 for unknown team id', async () => {
    const res = await request(app)
      .get('/api/teams/nonexistent')
      .set('Authorization', `Bearer ${edToken}`);

    expect(res.status).toBe(404);
  });

  it('returns 401 without a token', async () => {
    const res = await request(app).get(`/api/teams/${teamId}`);
    expect(res.status).toBe(401);
  });
});

// ── DELETE /api/teams/:id ─────────────────────────────────────────────────

describe('DELETE /api/teams/:id', () => {
  let adminToken, edToken, teamId;

  beforeEach(async () => {
    const adm = await registerUser('admin@ex.com', 'password1', 'admin');
    adminToken = adm.token;
    const ed = await registerUser('ed@ex.com', 'password1', 'editor');
    edToken = ed.token;

    const createRes = await request(app)
      .post('/api/teams')
      .set('Authorization', `Bearer ${edToken}`)
      .send({ name: 'Temp Team' });
    teamId = createRes.body.team.id;
  });

  it('admin can delete a team', async () => {
    const res = await request(app)
      .delete(`/api/teams/${teamId}`)
      .set('Authorization', `Bearer ${adminToken}`);

    expect(res.status).toBe(200);
    expect(res.body.deleted.name).toBe('Temp Team');

    // Verify the team is gone
    const getRes = await request(app)
      .get(`/api/teams/${teamId}`)
      .set('Authorization', `Bearer ${adminToken}`);
    expect(getRes.status).toBe(404);
  });

  it('deleting a team also removes its memberships', async () => {
    await request(app)
      .delete(`/api/teams/${teamId}`)
      .set('Authorization', `Bearer ${adminToken}`);

    expect(MembershipModel.getRoster(teamId)).toHaveLength(0);
  });

  it('returns 403 for editor', async () => {
    const res = await request(app)
      .delete(`/api/teams/${teamId}`)
      .set('Authorization', `Bearer ${edToken}`);

    expect(res.status).toBe(403);
  });

  it('returns 404 for unknown team id', async () => {
    const res = await request(app)
      .delete('/api/teams/nonexistent')
      .set('Authorization', `Bearer ${adminToken}`);

    expect(res.status).toBe(404);
  });
});

// ── POST /api/teams/:id/members ───────────────────────────────────────────

describe('POST /api/teams/:id/members', () => {
  let adminToken, edToken, teamId, targetUserId;

  beforeEach(async () => {
    const adm = await registerUser('admin@ex.com', 'password1', 'admin');
    adminToken = adm.token;
    const ed = await registerUser('ed@ex.com', 'password1', 'editor');
    edToken = ed.token;
    const target = await registerUser('target@ex.com', 'password1', 'viewer');
    targetUserId = target.user.id;

    const createRes = await request(app)
      .post('/api/teams')
      .set('Authorization', `Bearer ${edToken}`)
      .send({ name: 'Dev Team' });
    teamId = createRes.body.team.id;
  });

  it('admin can add a member', async () => {
    const res = await request(app)
      .post(`/api/teams/${teamId}/members`)
      .set('Authorization', `Bearer ${adminToken}`)
      .send({ userId: targetUserId });

    expect(res.status).toBe(201);
    expect(res.body.membership.userId).toBe(targetUserId);
    expect(res.body.membership.teamRole).toBe('member');
  });

  it('admin can add a member with an explicit teamRole', async () => {
    const res = await request(app)
      .post(`/api/teams/${teamId}/members`)
      .set('Authorization', `Bearer ${adminToken}`)
      .send({ userId: targetUserId, teamRole: 'owner' });

    expect(res.status).toBe(201);
    expect(res.body.membership.teamRole).toBe('owner');
  });

  it('returns 403 for editor', async () => {
    const res = await request(app)
      .post(`/api/teams/${teamId}/members`)
      .set('Authorization', `Bearer ${edToken}`)
      .send({ userId: targetUserId });

    expect(res.status).toBe(403);
  });

  it('returns 400 when userId is missing', async () => {
    const res = await request(app)
      .post(`/api/teams/${teamId}/members`)
      .set('Authorization', `Bearer ${adminToken}`)
      .send({});

    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/userId is required/);
  });

  it('returns 400 for invalid teamRole', async () => {
    const res = await request(app)
      .post(`/api/teams/${teamId}/members`)
      .set('Authorization', `Bearer ${adminToken}`)
      .send({ userId: targetUserId, teamRole: 'superadmin' });

    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/Invalid team role/);
  });

  it('returns 404 when team does not exist', async () => {
    const res = await request(app)
      .post('/api/teams/nonexistent/members')
      .set('Authorization', `Bearer ${adminToken}`)
      .send({ userId: targetUserId });

    expect(res.status).toBe(404);
  });

  it('returns 404 when user does not exist', async () => {
    const res = await request(app)
      .post(`/api/teams/${teamId}/members`)
      .set('Authorization', `Bearer ${adminToken}`)
      .send({ userId: 'usr_nonexistent' });

    expect(res.status).toBe(404);
  });

  it('returns 409 when user is already a member', async () => {
    await request(app)
      .post(`/api/teams/${teamId}/members`)
      .set('Authorization', `Bearer ${adminToken}`)
      .send({ userId: targetUserId });

    const res = await request(app)
      .post(`/api/teams/${teamId}/members`)
      .set('Authorization', `Bearer ${adminToken}`)
      .send({ userId: targetUserId });

    expect(res.status).toBe(409);
  });
});

// ── DELETE /api/teams/:id/members/:userId ─────────────────────────────────

describe('DELETE /api/teams/:id/members/:userId', () => {
  let adminToken, edToken, teamId, targetUserId;

  beforeEach(async () => {
    const adm = await registerUser('admin@ex.com', 'password1', 'admin');
    adminToken = adm.token;
    const ed = await registerUser('ed@ex.com', 'password1', 'editor');
    edToken = ed.token;
    const target = await registerUser('target@ex.com', 'password1', 'viewer');
    targetUserId = target.user.id;

    const createRes = await request(app)
      .post('/api/teams')
      .set('Authorization', `Bearer ${edToken}`)
      .send({ name: 'Dev Team' });
    teamId = createRes.body.team.id;

    // Add target as member
    await request(app)
      .post(`/api/teams/${teamId}/members`)
      .set('Authorization', `Bearer ${adminToken}`)
      .send({ userId: targetUserId });
  });

  it('admin can remove a member', async () => {
    const res = await request(app)
      .delete(`/api/teams/${teamId}/members/${targetUserId}`)
      .set('Authorization', `Bearer ${adminToken}`);

    expect(res.status).toBe(200);
    expect(res.body.userId).toBe(targetUserId);
  });

  it('returns 403 for editor', async () => {
    const res = await request(app)
      .delete(`/api/teams/${teamId}/members/${targetUserId}`)
      .set('Authorization', `Bearer ${edToken}`);

    expect(res.status).toBe(403);
  });

  it('returns 404 when team does not exist', async () => {
    const res = await request(app)
      .delete(`/api/teams/nonexistent/members/${targetUserId}`)
      .set('Authorization', `Bearer ${adminToken}`);

    expect(res.status).toBe(404);
  });

  it('returns 404 when membership does not exist', async () => {
    const res = await request(app)
      .delete(`/api/teams/${teamId}/members/usr_notamember`)
      .set('Authorization', `Bearer ${adminToken}`);

    expect(res.status).toBe(404);
  });
});

// ── GET /api/users/:userId/teams ──────────────────────────────────────────

describe('GET /api/users/:userId/teams', () => {
  let adminToken, viewerToken, editorUser, viewerUser, teamId1, teamId2;

  beforeEach(async () => {
    const adm = await registerUser('admin@ex.com', 'password1', 'admin');
    adminToken = adm.token;
    const ed = await registerUser('ed@ex.com', 'password1', 'editor');
    editorUser = ed.user;
    const vw = await registerUser('viewer@ex.com', 'password1', 'viewer');
    viewerUser = vw.user;
    viewerToken = vw.token;

    const res1 = await request(app)
      .post('/api/teams')
      .set('Authorization', `Bearer ${ed.token}`)
      .send({ name: 'Team Alpha' });
    teamId1 = res1.body.team.id;

    const res2 = await request(app)
      .post('/api/teams')
      .set('Authorization', `Bearer ${ed.token}`)
      .send({ name: 'Team Beta' });
    teamId2 = res2.body.team.id;

    // Add viewer to both teams
    await request(app)
      .post(`/api/teams/${teamId1}/members`)
      .set('Authorization', `Bearer ${adminToken}`)
      .send({ userId: viewerUser.id });
    await request(app)
      .post(`/api/teams/${teamId2}/members`)
      .set('Authorization', `Bearer ${adminToken}`)
      .send({ userId: viewerUser.id });
  });

  it('viewer can list their own teams', async () => {
    const res = await request(app)
      .get(`/api/users/${viewerUser.id}/teams`)
      .set('Authorization', `Bearer ${viewerToken}`);

    expect(res.status).toBe(200);
    expect(res.body.userId).toBe(viewerUser.id);
    expect(res.body.teams).toHaveLength(2);
    const names = res.body.teams.map((t) => t.teamName);
    expect(names).toContain('Team Alpha');
    expect(names).toContain('Team Beta');
  });

  it('admin can list teams for any user', async () => {
    const res = await request(app)
      .get(`/api/users/${editorUser.id}/teams`)
      .set('Authorization', `Bearer ${adminToken}`);

    expect(res.status).toBe(200);
    // Editor is owner of both teams
    expect(res.body.teams).toHaveLength(2);
  });

  it('returns empty list for user not in any team', async () => {
    const { user: loner } = await registerUser('loner@ex.com', 'password1', 'viewer');
    const res = await request(app)
      .get(`/api/users/${loner.id}/teams`)
      .set('Authorization', `Bearer ${adminToken}`);

    expect(res.status).toBe(200);
    expect(res.body.teams).toEqual([]);
  });

  it('returns 404 for unknown userId', async () => {
    const res = await request(app)
      .get('/api/users/usr_nonexistent/teams')
      .set('Authorization', `Bearer ${adminToken}`);

    expect(res.status).toBe(404);
  });

  it('returns 401 without a token', async () => {
    const res = await request(app).get(`/api/users/${viewerUser.id}/teams`);
    expect(res.status).toBe(401);
  });
});
