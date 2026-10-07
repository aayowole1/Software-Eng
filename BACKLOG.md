# Product Backlog — PB-01

**Project:** Software-Eng  
**Owner:** Ayomide Ayowole-Obi (AA)  
**WBS Reference:** 1.1 — Requirements and Backlog  
**Last Updated:** 2026-09-29  

---

## Overview

This document is the authoritative product backlog for the Software-Eng project. It captures every user story, its acceptance criteria, priority, status, and the WBS task that delivers it. Stories are ordered by priority (highest first) within each epic.

---

## WBS / Epic Structure

| WBS ID | Epic | Status |
|--------|------|--------|
| 1.1 | Requirements and Backlog | ✅ Done |
| 1.2 | Development Environment Setup | ✅ Done |
| 1.3 | SSO and Permissions | ✅ Done |
| 1.4 | Membership and Roster | ✅ Done |
| 1.9 | AI Drafts and Review Interface | ✅ Done |

---

## Epic 1.3 — SSO and Permissions

### US-01 — Local Registration

> **As a** new user,  
> **I want to** register with an email address and password,  
> **so that** I can create an account without needing a third-party identity provider.

**Priority:** High  
**Status:** ✅ Done (SCRUM-13)  
**WBS:** 1.3  

**Acceptance Criteria:**

- [ ] `POST /auth/register` accepts `{ email, password }` in the request body.
- [ ] Password must be at least 8 characters; a 400 error is returned with a descriptive message if it is shorter.
- [ ] Email must be provided; a 400 error is returned when it is absent.
- [ ] Password is hashed with bcrypt (cost factor ≥ 10) before being stored; the raw password is never persisted.
- [ ] A successful registration returns HTTP 201, a JWT, and the user object.
- [ ] The user object returned never includes `passwordHash`.
- [ ] New users receive the `viewer` role by default.
- [ ] Attempting to register with an already-registered email returns HTTP 409.

---

### US-02 — Local Login

> **As a** registered user,  
> **I want to** log in with my email and password,  
> **so that** I can obtain a JWT token to use the API.

**Priority:** High  
**Status:** ✅ Done (SCRUM-13)  
**WBS:** 1.3  

**Acceptance Criteria:**

- [ ] `POST /auth/login` accepts `{ email, password }`.
- [ ] Returns HTTP 200 with a JWT and user object on valid credentials.
- [ ] Returns HTTP 401 for an unknown email or incorrect password.
- [ ] Returns HTTP 400 when either field is missing.
- [ ] The JWT is signed with HS256 using `JWT_SECRET` and expires according to `JWT_EXPIRES_IN`.

---

### US-03 — Google OAuth 2.0 SSO

> **As a** user,  
> **I want to** sign in with my Google account,  
> **so that** I do not need to manage a separate password.

**Priority:** Medium  
**Status:** ✅ Done (SCRUM-13)  
**WBS:** 1.3  

**Acceptance Criteria:**

- [ ] `GET /auth/google` initiates the Google OAuth 2.0 flow, redirecting the user to Google's consent screen.
- [ ] `GET /auth/google/callback` exchanges the authorisation code for tokens and creates or updates the user record (upsert).
- [ ] On success the user receives a JWT token.
- [ ] Google SSO is optional; the application operates fully without `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` configured.
- [ ] New users created via Google SSO receive the `viewer` role by default.

---

### US-04 — Authenticated User Profile

> **As an** authenticated user,  
> **I want to** fetch my own profile,  
> **so that** I can confirm my identity and role.

**Priority:** Medium  
**Status:** ✅ Done (SCRUM-13)  
**WBS:** 1.3  

**Acceptance Criteria:**

- [ ] `GET /auth/me` returns the current user's profile (id, email, role, displayName, createdAt).
- [ ] Returns HTTP 401 when no valid Bearer token is provided.
- [ ] Returns HTTP 401 when the token is tampered with or expired.
- [ ] `passwordHash` is never present in the response.

---

### US-05 — Role-Based Access Control (RBAC)

> **As a** system administrator,  
> **I want** the API to enforce a three-tier role hierarchy,  
> **so that** users can only perform actions permitted by their role.

**Priority:** High  
**Status:** ✅ Done (SCRUM-13)  
**WBS:** 1.3  

**Acceptance Criteria:**

- [ ] Three roles exist: `viewer` (level 1), `editor` (level 2), `admin` (level 3).
- [ ] Each role implicitly has all permissions of lower-level roles.
- [ ] `GET /api/posts` is accessible to `viewer`, `editor`, and `admin`.
- [ ] `POST /api/posts` is accessible to `editor` and `admin` only; `viewer` receives HTTP 403.
- [ ] `DELETE /api/posts/:id` is accessible to `admin` only; `viewer` and `editor` receive HTTP 403.
- [ ] `GET /api/admin/users` is accessible to `admin` only.
- [ ] All protected routes return HTTP 401 when no or invalid JWT is supplied.

---

### US-06 — Admin Role Promotion

> **As an** admin,  
> **I want to** change any user's system role,  
> **so that** I can grant or revoke elevated privileges.

**Priority:** High  
**Status:** ✅ Done (SCRUM-13)  
**WBS:** 1.3  

**Acceptance Criteria:**

- [ ] `PUT /api/admin/users/:id/role` accepts `{ role }` and updates the target user's system role.
- [ ] Only admins may call this endpoint; non-admins receive HTTP 403.
- [ ] Supplying an invalid role value (not `viewer`, `editor`, or `admin`) returns HTTP 400.
- [ ] Supplying an unknown user id returns HTTP 404.
- [ ] A successful update returns the updated user object (without `passwordHash`).

---

## Epic 1.4 — Membership and Roster

### US-07 — Create a Team

> **As an** editor or admin,  
> **I want to** create a named team,  
> **so that** I can group users for collaboration.

**Priority:** High  
**Status:** ✅ Done (SCRUM-14)  
**WBS:** 1.4  

**Acceptance Criteria:**

- [ ] `POST /api/teams` accepts `{ name, description }` and creates a team.
- [ ] The creator is automatically added to the team with the `owner` team role.
- [ ] `name` is required; omitting it returns HTTP 400.
- [ ] Creating a team with a duplicate name returns HTTP 409.
- [ ] A `viewer` attempting to create a team receives HTTP 403.
- [ ] Returns HTTP 201 with the new team object on success.

---

### US-08 — List All Teams

> **As a** viewer (or above),  
> **I want to** see a list of all teams,  
> **so that** I can discover which teams exist.

**Priority:** Medium  
**Status:** ✅ Done (SCRUM-14)  
**WBS:** 1.4  

**Acceptance Criteria:**

- [ ] `GET /api/teams` returns an array of all teams.
- [ ] Accessible to any authenticated user (`viewer` and above).
- [ ] Returns HTTP 401 when no valid JWT is supplied.

---

### US-09 — View Team Details and Roster

> **As a** viewer (or above),  
> **I want to** view a team's details and its full member roster,  
> **so that** I can see who belongs to a team and their team roles.

**Priority:** High  
**Status:** ✅ Done (SCRUM-14)  
**WBS:** 1.4  

**Acceptance Criteria:**

- [ ] `GET /api/teams/:id` returns the team object and a `roster` array.
- [ ] Each roster entry contains: `userId`, `teamRole`, `joinedAt`, `displayName`, `email`.
- [ ] Returns HTTP 404 for an unknown team id.
- [ ] Accessible to any authenticated user (`viewer` and above).

---

### US-10 — Delete a Team

> **As an** admin,  
> **I want to** delete a team,  
> **so that** I can remove teams that are no longer needed.

**Priority:** Medium  
**Status:** ✅ Done (SCRUM-14)  
**WBS:** 1.4  

**Acceptance Criteria:**

- [ ] `DELETE /api/teams/:id` removes the team and all associated memberships.
- [ ] Returns HTTP 204 on success.
- [ ] Returns HTTP 404 for an unknown team id.
- [ ] Only admins may call this endpoint; non-admins receive HTTP 403.

---

### US-11 — Add a Member to a Team

> **As an** admin,  
> **I want to** add a user to a team with an explicit team role,  
> **so that** I can manage team composition.

**Priority:** High  
**Status:** ✅ Done (SCRUM-14)  
**WBS:** 1.4  

**Acceptance Criteria:**

- [ ] `POST /api/teams/:id/members` accepts `{ userId, teamRole }`.
- [ ] Valid team roles are `owner` and `member`.
- [ ] Returns HTTP 201 with the new membership on success.
- [ ] Returns HTTP 404 when the team or user does not exist.
- [ ] Returns HTTP 409 when the user is already a member of the team.
- [ ] Returns HTTP 400 for an invalid `teamRole` value.
- [ ] Only admins may call this endpoint; non-admins receive HTTP 403.

---

### US-12 — Remove a Member from a Team

> **As an** admin,  
> **I want to** remove a user from a team,  
> **so that** I can keep team membership accurate.

**Priority:** Medium  
**Status:** ✅ Done (SCRUM-14)  
**WBS:** 1.4  

**Acceptance Criteria:**

- [ ] `DELETE /api/teams/:id/members/:userId` removes the user from the team.
- [ ] Returns HTTP 200 on success.
- [ ] Returns HTTP 404 when the team does not exist or the user is not a member of it.
- [ ] Only admins may call this endpoint; non-admins receive HTTP 403.

---

### US-13 — List a User's Teams

> **As a** viewer (or above),  
> **I want to** see all teams a specific user belongs to,  
> **so that** I can understand a user's team memberships.

**Priority:** Low  
**Status:** ✅ Done (SCRUM-14)  
**WBS:** 1.4  

**Acceptance Criteria:**

- [ ] `GET /api/users/:userId/teams` returns an array of team objects the user belongs to.
- [ ] Returns HTTP 404 when the user does not exist.
- [ ] Returns an empty array (not a 404) when the user exists but belongs to no teams.
- [ ] Accessible to any authenticated user (`viewer` and above).

---

## Epic 1.9 — AI Drafts and Review Interface

> **Backlog ID:** PB-05  
> **WBS:** 1.9  
> **Owner:** Jack Pankaj (JP)  
> **Dependencies:** 1.2 (task interface defined in 1.2; connection to completed task module in 1.10)

### US-14 — Request an AI Draft

> **As an** editor or admin,  
> **I want to** submit a prompt and receive an AI-generated draft,  
> **so that** I can quickly produce content for human review.

**Priority:** High  
**Status:** ✅ Done (SCRUM-19)  
**WBS:** 1.9  

**Acceptance Criteria:**

- [ ] `POST /api/drafts` accepts `{ title, prompt }` in the request body.
- [ ] `title` is required; omitting it or sending a blank value returns HTTP 400.
- [ ] `prompt` is required; omitting it or sending a blank value returns HTTP 400.
- [ ] The system generates content from the prompt and stores it as a draft.
- [ ] New drafts have status `pending_review`.
- [ ] The response (HTTP 201) includes the full draft object including generated `content`.
- [ ] A `viewer` attempting to create a draft receives HTTP 403.
- [ ] Returns HTTP 401 when no valid Bearer token is provided.

---

### US-15 — List Drafts

> **As a** viewer (or above),  
> **I want to** see a list of all AI drafts,  
> **so that** I can discover which drafts are awaiting review.

**Priority:** Medium  
**Status:** ✅ Done (SCRUM-19)  
**WBS:** 1.9  

**Acceptance Criteria:**

- [ ] `GET /api/drafts` returns an array of all draft objects.
- [ ] Accessible to any authenticated user (`viewer` and above).
- [ ] Returns an empty array when no drafts exist.
- [ ] Returns HTTP 401 when no valid JWT is supplied.

---

### US-16 — View a Draft

> **As a** viewer (or above),  
> **I want to** read a specific AI draft,  
> **so that** I can review its content before approving or rejecting it.

**Priority:** High  
**Status:** ✅ Done (SCRUM-19)  
**WBS:** 1.9  

**Acceptance Criteria:**

- [ ] `GET /api/drafts/:id` returns the full draft object including generated content.
- [ ] Returns HTTP 404 for an unknown draft id.
- [ ] Accessible to any authenticated user (`viewer` and above).
- [ ] Returns HTTP 401 when no valid JWT is supplied.

---

### US-17 — Review a Draft

> **As an** editor or admin,  
> **I want to** approve, reject, or request revisions on an AI draft,  
> **so that** only suitable content proceeds further.

**Priority:** High  
**Status:** ✅ Done (SCRUM-19)  
**WBS:** 1.9  

**Acceptance Criteria:**

- [ ] `POST /api/drafts/:id/reviews` accepts `{ decision, note? }`.
- [ ] Valid decisions are `approved`, `rejected`, and `revision_requested`.
- [ ] Supplying an invalid decision value returns HTTP 400.
- [ ] Omitting `decision` returns HTTP 400.
- [ ] Returns HTTP 404 for an unknown draft id.
- [ ] A successful review updates the draft's `status`, `reviewedBy`, `reviewNote`, and `reviewedAt`.
- [ ] `note` is optional; when omitted `reviewNote` is `null`.
- [ ] A `viewer` attempting to review receives HTTP 403.
- [ ] Returns HTTP 401 when no valid JWT is supplied.

---

### US-18 — Delete a Draft

> **As an** admin,  
> **I want to** delete an AI draft,  
> **so that** I can remove drafts that are no longer needed.

**Priority:** Low  
**Status:** ✅ Done (SCRUM-19)  
**WBS:** 1.9  

**Acceptance Criteria:**

- [ ] `DELETE /api/drafts/:id` removes the draft.
- [ ] Returns HTTP 204 on success.
- [ ] Returns HTTP 404 for an unknown draft id.
- [ ] Only admins may call this endpoint; non-admins receive HTTP 403.
- [ ] Returns HTTP 401 when no valid JWT is supplied.

---

## Non-Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| NFR-01 | Passwords stored as bcrypt hashes (cost ≥ 10); never returned in API responses | ✅ Done |
| NFR-02 | JWTs signed with HS256; secret loaded from environment variable `JWT_SECRET` | ✅ Done |
| NFR-03 | Role enforcement is server-side; clients cannot self-elevate privileges | ✅ Done |
| NFR-04 | All model changes validated before persistence | ✅ Done |
| NFR-05 | Test coverage ≥ 80% across all source files | ✅ Done (86.49% overall) |
| NFR-06 | Application runs without external services (Google SSO is optional) | ✅ Done |

---

## Definition of Done (Project-Wide)

Every story is considered **Done** when all of the following are true:

1. **Acceptance criteria met** — every bullet in the story's AC section is implemented and verified.
2. **Peer / pair review complete** — at minimum one reviewer has approved the PR.
3. **Tests pass** — `npm test` exits with zero failures (`jest --coverage`).
4. **No open critical / high defects** — no P1 or P2 bugs linked to the story.
5. **Documentation updated** — `README.md` reflects any new endpoints, models, or configuration.
6. **Increment demonstrated** — the feature is exercised in at least one automated test that acts as a living demo.

---

## Backlog Health

| Metric | Value |
|--------|-------|
| Total stories | 18 |
| Stories Done | 18 |
| Stories In Progress | 0 |
| Stories Not Started | 0 |
| Test suites | 5 |
| Total tests | 156 |
| Overall coverage | 94.13% |
