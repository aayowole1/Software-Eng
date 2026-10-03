# Software-Eng

## SSO and Permissions (1.3)

This project implements **Single Sign-On (SSO)** and **Role-Based Access Control (RBAC)** for a Node.js/Express API.

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
Three roles ordered by privilege level:

| Role | Level | Can read | Can write | Can delete / manage users |
|------|-------|----------|-----------|--------------------------|
| `viewer` | 1 | ✅ | ❌ | ❌ |
| `editor` | 2 | ✅ | ✅ | ❌ |
| `admin`  | 3 | ✅ | ✅ | ✅ |

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
│   └── user.js             # User model, ROLES, hasMinimumRole
└── routes/
    ├── auth.js             # /auth/* endpoints
    └── protected.js        # /api/* endpoints (require auth)

tests/
├── auth.test.js            # Registration, login, /auth/me
└── permissions.test.js     # RBAC logic + protected routes
```

---

## Security Notes
- Passwords are hashed with **bcrypt** (cost factor 10)
- JWTs are signed with **HS256** and have configurable expiry
- The `passwordHash` field is **never** returned in API responses
- Role enforcement happens server-side in middleware — clients cannot self-elevate
