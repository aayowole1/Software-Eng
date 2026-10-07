# AGENTS.md — Software-Eng

This file provides guidance for automated agents (Claude, Copilot, etc.) working in this repository.

## Project overview

Node.js / Express API implementing:
- **SSO** — local email/password + Google OAuth 2.0
- **RBAC** — viewer / editor / admin role hierarchy
- **Team Membership & Roster** — teams with owner/member team roles

All data is stored in in-memory Maps (no external database required).

## Repository layout

```
src/
├── app.js                  # Express app factory + server entry point
├── auth/
│   ├── jwt.js              # signToken / verifyToken (HS256)
│   └── passport.js         # Passport strategies (Local + Google OAuth)
├── middleware/
│   ├── authenticate.js     # Bearer JWT → req.user
│   └── authorize.js        # Role gate factory (requires authenticate first)
├── models/
│   ├── user.js             # User store, ROLES, hasMinimumRole
│   ├── team.js             # Team store
│   └── membership.js       # Membership store, TEAM_ROLES, roster helpers
└── routes/
    ├── auth.js             # /auth/* endpoints
    ├── protected.js        # /api/posts, /api/admin/* endpoints
    └── teams.js            # /api/teams, /api/users/:id/teams endpoints

tests/
├── auth.test.js            # Registration, login, /auth/me
├── permissions.test.js     # RBAC unit tests + protected route integration
└── membership.test.js      # Team model, Membership model, team route integration
```

## Getting started

```bash
npm install
cp .env.example .env   # fill in JWT_SECRET at minimum
npm test               # run Jest with coverage (must pass before any PR)
npm run dev            # nodemon dev server
```

Required env var: `JWT_SECRET`. All others are optional (Google SSO is disabled when `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` are absent).

## Running tests

```bash
npm test               # full suite + coverage report
npx jest --testPathPattern=auth          # single suite
npx jest --verbose                       # detailed test names
```

Coverage threshold: **≥ 80%** across all `src/**/*.js` files.

## Coding conventions

- **No external database** — keep models as in-memory Maps with `_reset()` helpers for test isolation.
- **No framework beyond Express** — avoid adding new runtime dependencies without discussion.
- **Public profiles** — never return `passwordHash` in any API response; strip it in the route handler.
- **Role checks** — always use `authenticate` then `authorize(role)` middleware in that order.
- **Error shapes** — JSON `{ error: "..." }` for 4xx/5xx; `{ token, user }` for auth successes.
- **Test isolation** — call `UserModel._reset()`, `TeamModel._reset()`, `MembershipModel._reset()` in `beforeEach` for every test suite that touches models.

## Branch naming

Follow the pattern: `claude/{JIRA-KEY}/{short-slug}`  
Example: `claude/SCRUM-12/architecture-test-foundation`

## Definition of Done

A PR is ready to merge when:
1. All acceptance criteria in the linked story are met.
2. `npm test` exits with zero failures.
3. Coverage stays at or above 80% overall.
4. No `passwordHash` or raw secrets appear in responses.
5. README and BACKLOG are updated if new endpoints or stories are added.
