# Software-Eng

This project implements **Single Sign-On (SSO)**, **Role-Based Access Control (RBAC)**, and **Team Membership & Roster** management for a Node.js/Express API.

## Project Backlog

The full product backlog (user stories, acceptance criteria, priorities, and status) is maintained in **[BACKLOG.md](BACKLOG.md)** (PB-01).

| WBS ID | Deliverable | Status |
|--------|-------------|--------|
| 1.1 | Requirements and Backlog | ✅ Done |
| 1.2 | Development Environment Setup | ✅ Done |
| 1.3 | SSO and Permissions | ✅ Done |
| 1.4 | Membership and Roster | ✅ Done |
| 1.9 | AI Drafts and Review Interface | ✅ Done |

---

## Features

### Authentication (SSO)
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/auth/register` | Register with email + password |
| `POST` | `/auth/login` | Login with email + password → JWT |
| `GET` | `/auth/google` | Initiate Google OAuth 2.0 SSO |
| `GET` | `/auth/google/callback` | Google OAuth callback → JWT |
| `GET` | `/auth/me` | Get current user profile *(requires auth)* |

All authenticated routes use **Bearer JWT** tokens in the `Authorization` header.

### Roles and Permissions (RBAC)
Three system roles ordered by privilege level:

| Role | Level | Can read | Can write | Can delete / manage users | Can manage teams |
|------|-------|----------|-----------|--------------------------|-----------------|
| `viewer` | 1 | ✅ | ❌ | ❌ | ❌ |
| `editor` | 2 | ✅ | ✅ | ❌ | create only |
| `admin`  | 3 | ✅ | ✅ | ✅ | ✅ |

New users start with the `viewer` role. An `admin` can promote any user via:
```
PUT /api/admin/users/:id/role   { "role": "editor" }
```

### Protected Routes
| Method | Endpoint | Minimum Role |
|--------|----------|-------------|
| `GET` | `/api/posts` | `viewer` |
| `POST` | `/api/posts` | `editor` |
| `DELETE` | `/api/posts/:id` | `admin` |
| `GET` | `/api/admin/users` | `admin` |
| `PUT` | `/api/admin/users/:id/role` | `admin` |

### Membership and Roster (1.4)

Teams are groups of users. Every user in a team has a **team role**: `owner` (the creator) or `member`.

#### Team Roles

| Team Role | Assigned when |
|-----------|---------------|
| `owner`   | Automatically on team creation |
| `member`  | When added by an admin |

#### Team & Roster Routes

| Method | Endpoint | Min System Role | Description |
|--------|----------|----------------|-------------|
| `POST` | `/api/teams` | `editor` | Create a team; creator becomes `owner` |
| `GET` | `/api/teams` | `viewer` | List all teams |
| `GET` | `/api/teams/:id` | `viewer` | Get team details + full roster |
| `DELETE` | `/api/teams/:id` | `admin` | Delete team and its memberships |
| `POST` | `/api/teams/:id/members` | `admin` | Add a user to a team |
| `DELETE` | `/api/teams/:id/members/:userId` | `admin` | Remove a user from a team |
| `GET` | `/api/users/:userId/teams` | `viewer` | List all teams a user belongs to |

#### Example: Create a team
```http
POST /api/teams
Authorization: Bearer <token>
Content-Type: application/json

{ "name": "Dev Team", "description": "Backend developers" }
```

#### Example: Add a member
```http
POST /api/teams/:teamId/members
Authorization: Bearer <admin-token>
Content-Type: application/json

{ "userId": "usr_abc123", "teamRole": "member" }
```

#### Example: View roster
```http
GET /api/teams/:teamId
Authorization: Bearer <token>
```
Response:
```json
{
  "team": { "id": "...", "name": "Dev Team", "description": "Backend developers", "createdBy": "...", "createdAt": "..." },
  "roster": [
    { "userId": "...", "teamRole": "owner", "joinedAt": "...", "displayName": "alice@ex.com", "email": "alice@ex.com" },
    { "userId": "...", "teamRole": "member", "joinedAt": "...", "displayName": "bob@ex.com", "email": "bob@ex.com" }
  ]
}
```

---

### AI Drafts and Review Interface (1.9)

Editors and admins can request AI-generated drafts by providing a prompt. Drafts start with `pending_review` status and can be reviewed (approved, rejected, or revision requested) by editors or admins.

#### Draft Statuses

| Status | Meaning |
|--------|---------|
| `pending_review` | Draft created; awaiting reviewer decision |
| `approved` | Reviewer accepted the draft |
| `rejected` | Reviewer rejected the draft |
| `revision_requested` | Reviewer asked for changes |

#### Draft Routes

| Method | Endpoint | Min System Role | Description |
|--------|----------|----------------|-------------|
| `POST` | `/api/drafts` | `editor` | Request an AI draft; body: `{ title, prompt }` |
| `GET` | `/api/drafts` | `viewer` | List all drafts |
| `GET` | `/api/drafts/:id` | `viewer` | Get a specific draft |
| `POST` | `/api/drafts/:id/reviews` | `editor` | Submit a review decision |
| `DELETE` | `/api/drafts/:id` | `admin` | Delete a draft |

#### Example: Request an AI draft
```http
POST /api/drafts
Authorization: Bearer <editor-token>
Content-Type: application/json

{ "title": "Intro to Node.js", "prompt": "Write a beginner's introduction to Node.js" }
```
Response (HTTP 201):
```json
{
  "draft": {
    "id": "draft_...",
    "title": "Intro to Node.js",
    "prompt": "Write a beginner's introduction to Node.js",
    "content": "[AI-generated draft]\n\n...",
    "status": "pending_review",
    "createdBy": "usr_...",
    "createdAt": "...",
    "reviewedBy": null,
    "reviewNote": null,
    "reviewedAt": null
  }
}
```

#### Example: Submit a review
```http
POST /api/drafts/:draftId/reviews
Authorization: Bearer <editor-token>
Content-Type: application/json

{ "decision": "approved", "note": "Looks great!" }
```

---

## Getting Started

### Prerequisites
- Node.js 18+

### Installation
```bash
npm install
cp .env.example .env
# Edit .env with your secrets
```

### Running
```bash
npm start        # production
npm run dev      # development (nodemon)
```

### Testing
```bash
npm test         # runs Jest with coverage
```

---

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Description |
|----------|-------------|
| `JWT_SECRET` | Secret key for signing JWTs (**required**) |
| `JWT_EXPIRES_IN` | Token lifetime, e.g. `1h`, `7d` (default: `1h`) |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID (for SSO) |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret (for SSO) |
| `GOOGLE_CALLBACK_URL` | OAuth callback URL (default: `http://localhost:3000/auth/google/callback`) |
| `PORT` | Server port (default: `3000`) |

> **Google SSO** is optional — the application works without it (local email/password auth is always available). To enable it, create credentials at [console.cloud.google.com](https://console.cloud.google.com) and add `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` to `.env`.

---

## Architecture

```
src/
├── app.js                  # Express app & entry point
├── auth/
│   ├── jwt.js              # signToken / verifyToken helpers
│   └── passport.js         # Passport strategies (Google OAuth, Local)
├── middleware/
│   ├── authenticate.js     # JWT Bearer token verification
│   └── authorize.js        # Role-based access control gate
├── models/
│   ├── user.js             # User model, ROLES, hasMinimumRole
│   ├── team.js             # Team model (create, list, delete)
│   ├── membership.js       # Membership model, TEAM_ROLES, roster helpers
│   └── draft.js            # Draft model, DRAFT_STATUSES, REVIEW_DECISIONS
└── routes/
    ├── auth.js             # /auth/* endpoints
    ├── protected.js        # /api/posts and /api/admin/* endpoints
    ├── teams.js            # /api/teams and /api/users/:id/teams endpoints
    └── drafts.js           # /api/drafts endpoints (AI drafts & reviews)

tests/
├── auth.test.js            # Registration, login, /auth/me
├── permissions.test.js     # RBAC logic + protected routes
├── membership.test.js      # Team model, Membership model, all team routes
└── drafts.test.js          # Draft model, all draft & review routes
```

---

## Security Notes
- Passwords are hashed with **bcrypt** (cost factor 10)
- JWTs are signed with **HS256** and have configurable expiry
- The `passwordHash` field is **never** returned in API responses
- Role enforcement happens server-side in middleware — clients cannot self-elevate
- Team membership management requires `admin` system role
