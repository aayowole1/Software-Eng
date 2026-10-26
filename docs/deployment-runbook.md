# Production deployment and recovery runbook

This path targets the team's existing Docker/VM environment. It is separate from
the development Compose setup and does not establish that the team's VM has
actually been deployed or checked. The production-container CI smoke uses an
isolated database and a private test certificate; it is not public TLS, live
provider verification or the course performance benchmark.

Use Docker Engine with the Compose plugin **2.24 or newer** on the target Linux
VM. The optional `env_file.required` syntax requires that Compose generation.
Run these commands from the repository root on the VM. Use a release-specific,
previously verified image tag and retain the preceding image's tag/digest.

## Configuration and transport boundary

Copy `.env.production.example` to `.env.production` privately, fill it in, and
restrict that file to the deployment operator. Both image-context and Git ignore
rules exclude real `.env` variants. Production disables python-dotenv file
loading; Compose injects the configured values at runtime. Do not retain a
resolved Compose configuration dump because it contains environment secrets.

Required values are `DJANGO_SECRET_KEY` (a new random secret, at least 50
characters), explicit comma-separated `DJANGO_ALLOWED_HOSTS`, the intended
`MONGODB_NAME`, and email policy. `MONGODB_URI` defaults only in Compose to the
private `mongo` service; the production settings module itself requires an
explicit URI. Host entries do not accept wildcards, schemes, ports or leading-dot
subdomain shorthand. If cross-origin CSRF access is needed, supply exact HTTPS
origins in `DJANGO_CSRF_TRUSTED_ORIGINS`.

The web service publishes only `127.0.0.1:${ORGFLOW_WEB_PORT:-8000}`. An
operator-managed TLS proxy on the **same VM** must route the public HTTPS origin
to that loopback port, preserve the original Host, and strip/overwrite incoming
forwarding headers. Only after that boundary is configured should
`DJANGO_TRUST_PROXY_HEADERS=true` be set; it trusts precisely
`X-Forwarded-Proto: https`. Otherwise forwarding headers are not trusted and
ordinary HTTP requests redirect to HTTPS. A proxy on another machine needs a
separately reviewed private network arrangement; exposing the app port publicly
is not the configuration provided here.

Set real DNS, a valid public certificate, renewal, firewall policy and proxy
request limits at the target host. HSTS defaults to 3,600 seconds. Enable
`DJANGO_HSTS_INCLUDE_SUBDOMAINS` or `DJANGO_HSTS_PRELOAD` only after confirming the
corresponding domain-wide HTTPS policy; CI opts in only for its disposable test
host. With those options false, Django's deployment check reports W005/W021 for
operator review rather than silently claiming those policies are established.

The included MongoDB has **no published port** and is attached only to an
internal Compose network. Web has a separate network for provider egress. This
private single-host database configuration does not configure external database
authentication, TLS, managed backups or replica-set high availability. If the
team uses an external MongoDB service, configure its authentication/TLS and
firewall policy through the connection URI before releasing; do not publish the
private MongoDB service as a substitute.

## Build and explicit release

Use a new immutable release tag in `.env.production` as `ORGFLOW_IMAGE_TAG`.
Never rebuild or replace a retained previous-release tag. Record the built image
ID/digest; the source tag alone is not a dependency lock or an image receipt.

```sh
docker compose --env-file .env.production -f compose.production.yml config --quiet
docker compose --env-file .env.production -f compose.production.yml build
docker compose --env-file .env.production -f compose.production.yml up -d --wait mongo
```

For an upgrade, stop all existing writers (`web` and `cleanup`) and take the
pre-release backup below **before migrating**. Run one explicit release job:

```sh
docker compose --env-file .env.production -f compose.production.yml stop web cleanup
docker compose --env-file .env.production -f compose.production.yml run --rm release
docker compose --env-file .env.production -f compose.production.yml run --rm --no-deps web python manage.py check --deploy --fail-level ERROR
docker compose --env-file .env.production -f compose.production.yml up -d --wait web cleanup
```

The release job performs migrations followed by `collectstatic`. It must run
once, with other writers stopped. Web startup never runs migrations. Static
assets are generated into the shared `static_data` volume by non-root UID 10001;
web mounts that volume read-only and WhiteNoise serves the manifest assets.
Application source is root-owned and the web container filesystem is read-only.
Do not add a source bind mount or weaken volume ownership to make startup pass.
Do not start web when the release job fails; investigate its safe error first.

After release, inspect the intended HTTPS origin, sign-in, Tasks permissions,
static assets and email behavior. `/health/` is liveness only.
`/health/ready/` pings the configured database within a bounded timeout and returns
503 with no connection details when unavailable. Both health paths permit
internal HTTP checks; they do not establish end-to-end TLS or application-data
correctness. The image health check supplies an explicit configured Host.

## Backup and rollback

Keep the previous immutable image and a matching pre-migration database backup
as one release pair. A backup without a successful restore check is not a
verified recovery plan. Store archives outside the application image and web
container, restrict their access, and protect copies held off the VM.

With writers stopped and MongoDB running, replace `<database>` with the exact
configured application database and use a release-specific host filename:

```sh
docker compose --env-file .env.production -f compose.production.yml exec -T mongo mongodump --db '<database>' --archive=/tmp/orgflow-before-release.archive.gz --gzip
docker compose --env-file .env.production -f compose.production.yml cp mongo:/tmp/orgflow-before-release.archive.gz /private/backups/<release>.archive.gz
```

These commands address the included private MongoDB. External authenticated
services require their own approved backup/restore mechanism; do not copy
connection secrets into shell history or evidence logs. Record the image
digest, source revision, database name, archive identifier and restore outcome.

If rollback is necessary, stop web/cleanup, select the **matching previous
image tag** in configuration without rebuilding it, and restore its matching
backup. Match the clean-database recovery rehearsed in CI: first verify the
archive is readable and the exact configured database name is correct, with all
writers stopped. The following operator step deletes that entire named database
before restore, including collections introduced by newer migrations. It is
destructive; retain the verified backup outside MongoDB and do not run it merely
to demonstrate recovery on the team database. `mongorestore --drop` alone only
drops collections represented in the archive, leaving newer collections behind
([MongoDB restore reference](https://www.mongodb.com/docs/database-tools/mongorestore/)).

```sh
docker compose --env-file .env.production -f compose.production.yml cp /private/backups/<previous-release>.archive.gz mongo:/tmp/orgflow-restore.archive.gz
docker compose --env-file .env.production -f compose.production.yml exec -T mongo mongosh --quiet --eval "db.getSiblingDB('<database>').dropDatabase()"
docker compose --env-file .env.production -f compose.production.yml exec -T mongo mongorestore --archive=/tmp/orgflow-restore.archive.gz --gzip --nsInclude '<database>.*' --stopOnError
docker compose --env-file .env.production -f compose.production.yml run --rm --no-deps release python manage.py collectstatic --noinput
docker compose --env-file .env.production -f compose.production.yml up -d --wait web cleanup
```

Do not start web or cleanup after any failed restore. Regenerate static files
from that previous image and check readiness plus the
same scoped HTTPS/account/task checks again. Rolling back code alone against a
newer incompatible database is not the rollback procedure. Do not run
`down --volumes` against the team's retained deployment data.

## Email, recordings and remaining owner checks

Production defaults to `DJANGO_EMAIL_POLICY=smtp` and refuses missing SMTP host
or sender configuration. SMTP uses TLS by default; SSL is an alternative, not an
additional simultaneous mode. Username/password must be configured together if
authentication is needed. `DJANGO_ALLOW_INSECURE_SMTP=true` permits only an
explicit staging exception, such as CI's private synthetic capture sink. It is
not a real-email delivery verification.

`DJANGO_EMAIL_POLICY=disabled` explicitly disables delivery, including password
reset mail. Console email is not the production fallback. If real delivery is
disabled or unverified, record the pending owner task and do not describe
password recovery as operational. The owner must verify the real sender, secure
SMTP service, delivered reset link, expiry and one-time use at the intended
HTTPS origin before enabling that claim.

Keep **one synchronous Gunicorn worker, one thread and one web replica**. In the
combined integration preview, meeting recordings live in a process-local map; additional processes or threads do not
share recording state safely. Worker restarts lose active recordings, abandoned
sessions have no durable cleanup protocol, and `/tmp` is a 64 MiB tmpfs. This
deployment path does not add multi-worker recording coordination, durable audio
storage or a memory-budget guarantee for the recording map. Complete or stop
recording before planned restarts; a shared/durable recording design remains
the meeting owner's scaling task.

Google/OpenAI/Deepgram checks remain with their respective owners; the user
explicitly left credential-dependent live checks pending. Use approved server-side credentials and synthetic notes/audio when
those owners run them; never infer a live-provider pass from mocked tests or CI's
empty provider keys. Team VM access, public TLS, real SMTP delivery, host backup
retention, monitored operations and human/team acceptance still need their own
receipts. A bounded CI read-latency sample is not the 25-user/10-minute NFR
benchmark or proof of a production recovery-time target.
