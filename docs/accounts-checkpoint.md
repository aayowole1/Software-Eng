# Accounts 1.3 checkpoint

Owner: Chau Minh Viet Nguyen. Prepared with Codex assistance on October 8, 2026.
This work extends the team's existing Django Accounts implementation. The
registration, password sign-in, original role system, and original tests were
already present in the supplied `django-conversion` snapshot at
`17835faa170e06c024c1bfa25dcb52be7b374427`.

The changes are on the local branch `chau/accounts-progress`. The original
prototype remains credited to its contributors. Human code review, a live Google
login, and integration into the team's remote repository remain separate steps.

## Changes in this checkpoint

- Prevent superuser demotion through organization role management and profile
  forms; display the effective Admin role and hide the role editor for superusers.
- Add an idempotent migration to create missing profiles for older users without
  overwriting existing member/officer assignments.
- Return a registration form error if a database uniqueness conflict happens
  after validation, instead of an unhandled server error.
- Add optional Google sign-in with server-side token verification, a separate
  provider identity, session nonce checks, and Django CSRF protection.
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
not to a team or production deployment. The Google button is disabled until
the team configures a real client ID.

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
Live Google verification is pending until the team configures its own client.
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
not a real Google login or Google's signing infrastructure. See
`verification-results.txt` for the actual run results.

The original 88 tests passed. The expanded suite passed 125 tests, followed by
five targeted verifier checks after adding a malformed-token regression. Those
runs cover all 126 distinct tests in the final source (four verifier checks
overlap between runs). The suite was not run as one 126-test invocation.

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
   does not link an existing account. State the live-provider test is still pending.
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
