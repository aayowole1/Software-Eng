# Accounts 1.3 checkpoint

Owner: Chau Minh Viet Nguyen. Prepared with Codex assistance on October 8, 2026.
This work extends the team's existing Django Accounts implementation. The
registration, password sign-in, original role system, and original tests were
already present in the supplied `django-conversion` snapshot at
`17835faa170e06c024c1bfa25dcb52be7b374427`.

The changes are on the local branch `chau/accounts-progress`. The original
prototype remains credited to its contributors. Human code review and integration
into the team's remote repository remain separate steps. A limited live Google
check has verified the existing-account protection; first-time and returning
Google account sign-in remain pending.

## Changes in this checkpoint

- Prevent superuser demotion through organization role management and profile
  forms; display the effective Admin role and hide the role editor for superusers.
- Add an idempotent migration to create missing profiles for older users without
  overwriting existing member/officer assignments.
- Return a registration form error if a database uniqueness conflict happens
  after validation, instead of an unhandled server error.
- Add optional Google sign-in with server-side token verification, a separate
  provider identity, session nonce checks, and Django CSRF protection.
- Apply Google's local-development referrer policy only to Google-enabled HTTP
  login responses on `localhost` or `127.0.0.1`; preserve the existing policy for
  HTTPS, remote hosts, and disabled Google sign-in. Add eight header regressions.
- Add regression tests and setup documentation; correct the README's Django
  version to the version already pinned by the team, 5.2.17.

## How authentication works

Local sign-in still accepts the username or email and checks Django's stored
password hash. New local and Google accounts start as applicants. The existing
server-side role decorators control protected pages and actions; hiding a button
alone is not authorization.

Google's browser library returns an ID token to a JavaScript callback. The
callback submits it to OrgFlow using a same-origin form with a Django CSRF token.
The server verifies the token using `google-auth` and the configured client ID,
checks the session nonce, then looks up the immutable Google subject (`sub`).
New identities receive an applicant account with an unusable local password.

An email match does not link a Google account to an existing password account.
Existing users must sign in with their existing credentials; an authenticated
account-linking workflow is future work. Google does not control every third-party
email address used for a Google account, so an email claim alone must not grant
access to an existing OrgFlow account.

## Local setup

Use Python 3.12 and a running MongoDB server. In PowerShell, from this checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env to match your MongoDB URI and database name.
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Do not overwrite an existing `.env`. Environment variables take precedence over
values in `.env`. Keep development data separate from shared/team databases.
The local verification environment used an isolated MongoDB at
`mongodb://127.0.0.1:27028` and database `orgflow_chau_checkpoint`.

The prepared demo is currently at `http://localhost:8000/accounts/login/` on
Chau's computer. Synthetic demo usernames are `demo_admin`, `demo_member`,
`demo_officer`, and `demo_root`; their development-only password is
`OrgFlow-Demo!2026`. These credentials belong only to the isolated local demo,
not to a team or production deployment. Google sign-in is now enabled in this
local demo using a configured Google client. A fresh checkout still needs its
own client configuration.

For Docker, follow the main README. Its `MONGODB_URI=mongodb://mongo:27017`
environment setting overrides a local `.env` URI. The project folder is mounted
inside the container, so an optional root `.env` also provides `GOOGLE_CLIENT_ID`.
Rebuild after changing Python requirements, and run migrations before use.

## Configure Google sign-in

1. In Google Cloud, configure the application's branding and audience, then
   create an OAuth client of type **Web application**.
2. Add `http://localhost` and `http://localhost:8000` to the authorized JavaScript
   origins for local testing. Add any required test users in Google Cloud.
3. Put the public client ID in `.env` as `GOOGLE_CLIENT_ID=...`. No Google client
   secret is required for this ID-token flow. Never paste private secrets into
   source code or a report.
4. Restart the app and open `http://localhost:8000/accounts/login/`. This flow
   uses the Google JavaScript callback, so it does not need a Google redirect URI.
5. Perform a real first-time and returning login. Check applicant status, sign
   out, and confirm an existing password account is not automatically linked.

When the client ID is empty, the Google button is hidden and the Google endpoint
is disabled. The code and mocked tests can be checked without Google credentials.
On October 8, 2026, a Google Cloud test project and Web application client were
created after the user's explicit policy and OAuth credential approval. The
client is in testing mode with the two localhost origins listed above. Its public
client ID is stored only in the ignored local `.env`, and the app was restarted.
No client ID, private account email, or project credentials are recorded here.

A live Google callback passed server-side token verification and session checks,
then returned the intended error because the verified email already belonged to
a local account. This demonstrates that a real Google token was accepted and
the existing password account was protected from automatic linking. It does not
demonstrate a successful Google account sign-in. A screenshot is retained locally
outside the repository. First-time account creation and returning sign-in await
a Google account whose email is not already registered locally.

Public deployment also needs a production security/configuration review; the
inherited settings are for development.

## Automated checks

Run these against an isolated development MongoDB instance. Django creates a
separate test database; do not point tests at a shared service without checking
its database permissions and naming.

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test accounts --verbosity 2
.\.venv\Scripts\python.exe manage.py test --verbosity 2
```

The new role and upgrade tests are in `accounts/test_account_safety.py`.
Google tests are in `accounts/test_google_auth.py`. Provider responses are
mocked: those tests exercise our acceptance/rejection logic and verifier wiring,
not a real Google login or Google's signing infrastructure. The limited live
provider check is recorded separately above. See `verification-results.txt` for
the actual run results.

The original 88 tests passed. The expanded suite passed 125 tests, followed by
five targeted verifier checks after adding a malformed-token regression. The
latest targeted run passed eight new header checks and the same five verifier
checks: 13 tests in 0.019 seconds, with 2.588 seconds of wall time and no database
setup. These runs cover the 134 distinct tests currently declared in the source
(88 original, eight account-safety, and 38 Google tests), with overlapping verifier
checks. No single 134-test full-suite run has been performed. The latest targeted
output was confirmed by the execution tool; a raw log was not saved.

## Chau's review and demonstration

On October 8, 2026, Chau reported completing these manual checks in the local
Django demo:

- Create an account and approve it using a superuser account.
- Complete the requested login checks: username and email sign-in, and rejection
  of an incorrect password.
- Complete the requested permission checks: an ordinary member cannot access
  admin user management, and an admin can change an ordinary user's role.

These results are based on Chau's confirmations in this chat; screenshots of his
run have not been supplied. They establish reported manual verification of those
flows, not personal review of every feature or code path. The remaining review
and demonstration checklist is:

1. Explain the before/after behavior of the superuser-role bug and show its
   regression test. Explain why a superuser has Admin authority even if an old
   profile contains a lower role.
2. Submit a duplicate username and mismatched sign-up passwords and explain the
   feedback; these are separate from the completed login checks.
3. Confirm a superuser has no role editor. Review the regression test showing
   that the server rejects a crafted demotion request.
4. Explain why migrations use historical models and preserve existing roles.
5. Explain Google token verification, CSRF, the nonce, and why an email match
   does not link an existing account. Explain the live existing-account protection
   result and complete first-time and returning Google sign-in when a suitable
   account is available.
6. Record actual observations and screenshots, then update Section 9 of the team
   report with the work you can explain and have personally reviewed.

## Limits and next work

Case-insensitive username/email duplicate checks remain application-level checks.
Handling `IntegrityError` does not create a database uniqueness guarantee for
canonicalized usernames or email. A separate schema/data-cleanup design is needed
before claiming concurrent duplicate-account creation is fully prevented.

The current MongoDB configuration is standalone; this change does not assume
multi-document transactions. Task creation, delegation, status, committee task
views, counts, and overdue handling (Chau's WBS 1.6) remain future work. Existing
committee CRUD from the teammate baseline is not evidence that 1.6 is finished.
Docker startup has not been verified on this machine.

## References

- [Google ID-token verification and account linking](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)
- [Google Identity Services setup](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)
- [Django authentication backends](https://docs.djangoproject.com/en/5.2/topics/auth/customizing/)
- [MongoDB Django transaction requirements](https://www.mongodb.com/docs/languages/python/django-mongodb/v5.2/interact-data/transactions/)
