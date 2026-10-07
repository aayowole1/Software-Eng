/**
 * Unit tests for src/models/user.js
 *
 * Covers every exported function directly:
 *   findByProvider, findByEmail, findById,
 *   upsertOAuthUser, createLocalUser,
 *   setUserRole, hasMinimumRole (role-related),
 *   ROLES / ROLE_HIERARCHY constants, _reset.
 */

const UserModel = require('../src/models/user');
const {
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
} = UserModel;

beforeEach(() => {
  _reset();
});

// ── ROLES constant ────────────────────────────────────────────────────────

describe('ROLES', () => {
  it('exports ADMIN, EDITOR, and VIEWER values', () => {
    expect(ROLES.ADMIN).toBe('admin');
    expect(ROLES.EDITOR).toBe('editor');
    expect(ROLES.VIEWER).toBe('viewer');
  });

  it('is frozen (immutable)', () => {
    expect(Object.isFrozen(ROLES)).toBe(true);
  });
});

// ── ROLE_HIERARCHY ────────────────────────────────────────────────────────

describe('ROLE_HIERARCHY', () => {
  it('admin has the highest numeric level', () => {
    expect(ROLE_HIERARCHY['admin']).toBeGreaterThan(ROLE_HIERARCHY['editor']);
    expect(ROLE_HIERARCHY['admin']).toBeGreaterThan(ROLE_HIERARCHY['viewer']);
  });

  it('editor is ranked above viewer', () => {
    expect(ROLE_HIERARCHY['editor']).toBeGreaterThan(ROLE_HIERARCHY['viewer']);
  });

  it('viewer has the lowest level', () => {
    expect(ROLE_HIERARCHY['viewer']).toBeGreaterThanOrEqual(1);
  });
});

// ── createLocalUser ───────────────────────────────────────────────────────

describe('createLocalUser', () => {
  it('creates a user with the given email and password hash', () => {
    const user = createLocalUser('alice@example.com', 'hashed_pw');
    expect(user.email).toBe('alice@example.com');
    expect(user.passwordHash).toBe('hashed_pw');
    expect(user.provider).toBe('local');
  });

  it('defaults the role to viewer', () => {
    const user = createLocalUser('alice@example.com', 'hashed_pw');
    expect(user.role).toBe(ROLES.VIEWER);
  });

  it('accepts an explicit role', () => {
    const user = createLocalUser('admin@example.com', 'hashed_pw', ROLES.ADMIN);
    expect(user.role).toBe(ROLES.ADMIN);
  });

  it('assigns a unique id starting with usr_', () => {
    const user = createLocalUser('alice@example.com', 'hashed_pw');
    expect(user.id).toMatch(/^usr_/);
  });

  it('throws when the email is already registered', () => {
    createLocalUser('alice@example.com', 'hashed_pw');
    expect(() => createLocalUser('alice@example.com', 'other_hash')).toThrow(
      /already exists/
    );
  });

  it('sets displayName to the email', () => {
    const user = createLocalUser('alice@example.com', 'hashed_pw');
    expect(user.displayName).toBe('alice@example.com');
  });
});

// ── upsertOAuthUser ───────────────────────────────────────────────────────

describe('upsertOAuthUser', () => {
  const profile = {
    provider: 'google',
    providerId: 'gid_123',
    email: 'bob@example.com',
    displayName: 'Bob Smith',
    photo: 'https://example.com/photo.jpg',
  };

  it('creates a new OAuth user on first call', () => {
    const user = upsertOAuthUser(profile);
    expect(user.provider).toBe('google');
    expect(user.providerId).toBe('gid_123');
    expect(user.email).toBe('bob@example.com');
    expect(user.displayName).toBe('Bob Smith');
    expect(user.photo).toBe('https://example.com/photo.jpg');
  });

  it('assigns the default viewer role to new OAuth users', () => {
    const user = upsertOAuthUser(profile);
    expect(user.role).toBe(ROLES.VIEWER);
  });

  it('assigns a unique id starting with usr_', () => {
    const user = upsertOAuthUser(profile);
    expect(user.id).toMatch(/^usr_/);
  });

  it('updates displayName and photo on subsequent calls (upsert)', () => {
    upsertOAuthUser(profile);
    const updated = upsertOAuthUser({
      ...profile,
      displayName: 'Bobby Smith',
      photo: 'https://example.com/new-photo.jpg',
    });
    expect(updated.displayName).toBe('Bobby Smith');
    expect(updated.photo).toBe('https://example.com/new-photo.jpg');
    expect(updated.email).toBe(profile.email); // email unchanged
  });

  it('does not create duplicate entries on upsert', () => {
    upsertOAuthUser(profile);
    upsertOAuthUser({ ...profile, displayName: 'Updated Name' });
    // Only one user keyed by provider:providerId
    expect(findByProvider('google', 'gid_123')).toBeDefined();
  });

  it('preserves role across upsert updates', () => {
    const user = upsertOAuthUser(profile);
    setUserRole(user.id, ROLES.EDITOR);
    const updated = upsertOAuthUser({ ...profile, displayName: 'New Name' });
    // Role should not be reset on upsert
    expect(updated.role).toBe(ROLES.EDITOR);
  });
});

// ── findByProvider ────────────────────────────────────────────────────────

describe('findByProvider', () => {
  it('returns the user matching provider + providerId', () => {
    const created = upsertOAuthUser({
      provider: 'google',
      providerId: 'gid_abc',
      email: 'carol@example.com',
      displayName: 'Carol',
      photo: null,
    });
    const found = findByProvider('google', 'gid_abc');
    expect(found).toEqual(created);
  });

  it('returns undefined for an unknown provider', () => {
    expect(findByProvider('github', 'gid_abc')).toBeUndefined();
  });

  it('returns undefined for an unknown providerId', () => {
    upsertOAuthUser({
      provider: 'google',
      providerId: 'gid_abc',
      email: 'carol@example.com',
      displayName: 'Carol',
      photo: null,
    });
    expect(findByProvider('google', 'gid_xyz')).toBeUndefined();
  });
});

// ── findByEmail ───────────────────────────────────────────────────────────

describe('findByEmail', () => {
  it('returns a local user by email', () => {
    const created = createLocalUser('dave@example.com', 'hash');
    expect(findByEmail('dave@example.com')).toEqual(created);
  });

  it('returns an OAuth user by email', () => {
    const created = upsertOAuthUser({
      provider: 'google',
      providerId: 'gid_dave',
      email: 'dave@example.com',
      displayName: 'Dave',
      photo: null,
    });
    expect(findByEmail('dave@example.com')).toEqual(created);
  });

  it('returns undefined for an unknown email', () => {
    expect(findByEmail('nobody@example.com')).toBeUndefined();
  });
});

// ── findById ──────────────────────────────────────────────────────────────

describe('findById', () => {
  it('returns a user matching the internal id', () => {
    const created = createLocalUser('eve@example.com', 'hash');
    expect(findById(created.id)).toEqual(created);
  });

  it('returns an OAuth user by internal id', () => {
    const created = upsertOAuthUser({
      provider: 'google',
      providerId: 'gid_eve',
      email: 'eve@example.com',
      displayName: 'Eve',
      photo: null,
    });
    expect(findById(created.id)).toEqual(created);
  });

  it('returns undefined for an unknown id', () => {
    expect(findById('usr_nonexistent')).toBeUndefined();
  });
});

// ── setUserRole ───────────────────────────────────────────────────────────

describe('setUserRole', () => {
  it('updates the user role and returns the updated user', () => {
    const user = createLocalUser('frank@example.com', 'hash');
    const updated = setUserRole(user.id, ROLES.ADMIN);
    expect(updated.role).toBe(ROLES.ADMIN);
    // Verify it persisted
    expect(findById(user.id).role).toBe(ROLES.ADMIN);
  });

  it('throws for an invalid role string', () => {
    const user = createLocalUser('frank@example.com', 'hash');
    expect(() => setUserRole(user.id, 'superuser')).toThrow(/Invalid role/);
  });

  it('throws when the user id does not exist', () => {
    expect(() => setUserRole('usr_nonexistent', ROLES.ADMIN)).toThrow(
      /User not found/
    );
  });

  it('accepts all valid ROLES values', () => {
    const user = createLocalUser('greta@example.com', 'hash');
    for (const role of Object.values(ROLES)) {
      expect(() => setUserRole(user.id, role)).not.toThrow();
    }
    expect(findById(user.id).role).toBe(ROLES.VIEWER); // last set
  });
});

// ── hasMinimumRole ────────────────────────────────────────────────────────

describe('hasMinimumRole', () => {
  it('admin satisfies admin, editor, and viewer', () => {
    expect(hasMinimumRole('admin', 'admin')).toBe(true);
    expect(hasMinimumRole('admin', 'editor')).toBe(true);
    expect(hasMinimumRole('admin', 'viewer')).toBe(true);
  });

  it('editor satisfies editor and viewer but not admin', () => {
    expect(hasMinimumRole('editor', 'editor')).toBe(true);
    expect(hasMinimumRole('editor', 'viewer')).toBe(true);
    expect(hasMinimumRole('editor', 'admin')).toBe(false);
  });

  it('viewer satisfies only viewer', () => {
    expect(hasMinimumRole('viewer', 'viewer')).toBe(true);
    expect(hasMinimumRole('viewer', 'editor')).toBe(false);
    expect(hasMinimumRole('viewer', 'admin')).toBe(false);
  });

  it('unknown userRole does not satisfy any requirement', () => {
    expect(hasMinimumRole('unknown', 'viewer')).toBe(false);
    expect(hasMinimumRole('unknown', 'editor')).toBe(false);
    expect(hasMinimumRole('unknown', 'admin')).toBe(false);
  });

  it('unknown requiredRole cannot be satisfied', () => {
    expect(hasMinimumRole('admin', 'superadmin')).toBe(false);
  });
});

// ── _reset ────────────────────────────────────────────────────────────────

describe('_reset', () => {
  it('clears all users from the store', () => {
    createLocalUser('h@example.com', 'hash');
    _reset();
    expect(findByEmail('h@example.com')).toBeUndefined();
  });
});
