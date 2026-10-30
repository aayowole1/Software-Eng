#!/bin/sh
# Disposable project, isolated volume/database; never targets an existing stack.
set -eu
cd "$(dirname "$0")/.."
export COMPOSE_PROJECT_NAME=orgflow_smoke_${GITHUB_RUN_ID:-$$}
export ORGFLOW_IMAGE_TAG=smoke-${GITHUB_RUN_ID:-$$}
export ORGFLOW_ENV_FILE=/dev/null
export ORGFLOW_WEB_PORT=18080
mkdir -p deploy/ci
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -keyout deploy/ci/key.pem -out deploy/ci/cert.pem -subj '/CN=localhost' -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1' 2>/dev/null
cat > deploy/ci/nginx.conf <<'EOF'
server {
    listen 443 ssl;
    server_name localhost;
    access_log off;
    ssl_certificate /etc/nginx/test-cert.pem;
    ssl_certificate_key /etc/nginx/test-key.pem;
    location / {
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_pass http://web:8000;
    }
}
EOF
# All values below are disposable test configuration, not deployment secrets.
export DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')"
export DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
export MONGODB_NAME=orgflow_deployment_smoke
export MONGODB_URI=mongodb://mongo:27017
export DJANGO_EMAIL_POLICY=smtp
export EMAIL_HOST=smtp
export EMAIL_PORT=8026
export EMAIL_USE_TLS=false
export EMAIL_USE_SSL=false
export EMAIL_HOST_USER=''
export EMAIL_HOST_PASSWORD=''
export DJANGO_ALLOW_INSECURE_SMTP=true
export DEFAULT_FROM_EMAIL='OrgFlow <smoke@example.invalid>'
export DJANGO_TRUST_PROXY_HEADERS=true
export DJANGO_HSTS_INCLUDE_SUBDOMAINS=true
export DJANGO_HSTS_PRELOAD=true
export GOOGLE_CLIENT_ID=''
export OPENAI_API_KEY=''
export DEEPGRAM_API_KEY=''
dc() { docker compose --env-file /dev/null -f compose.production.yml -f deploy/ci-compose.yml "$@"; }
trap 'dc logs --no-color 2>&1 | python -c '\''import re,sys; print(re.sub(r"/accounts/reset/[^\s\"<>]+", "/accounts/reset/[redacted]", sys.stdin.read()))'\'' > deploy/ci/container-logs.txt; dc down --volumes --remove-orphans' EXIT
dc build
dc up -d --wait mongo smtp
dc run --rm release
dc run --rm --no-deps web python manage.py check --deploy --fail-level WARNING
dc run --rm --no-deps web sh -c 'python manage.py shell < deploy/smoke_seed.py' > deploy/ci/seed-output.txt
python -c 'import json; from pathlib import Path; text=Path("deploy/ci/seed-output.txt").read_text(); Path("deploy/ci/fixtures.json").write_text(next(line.removeprefix("SMOKE_FIXTURE=") for line in text.splitlines() if line.startswith("SMOKE_FIXTURE=")))'
dc up -d --wait web proxy
dc exec -T web python -c 'import os; from pathlib import Path; assert os.getuid()!=0; assert not os.access("/app/manage.py",os.W_OK); assert not list(Path("/app").rglob(".env*")); assert not Path("/app/deploy/ci/key.pem").exists(); print("Non-root, immutable application and credential-free image: passed")' > deploy/ci/image-safety.txt
python deploy/smoke_http.py --ca deploy/ci/cert.pem --fixtures deploy/ci/fixtures.json > deploy/ci/https-initial.json
python deploy/smoke_email.py --base https://localhost:18443 --ca deploy/ci/cert.pem --capture http://localhost:18025/messages > deploy/ci/smtp-result.json
# Record DB unavailability truthfully; liveness must survive while readiness fails.
dc stop mongo
python -c 'import urllib.request,urllib.error,ssl; c=ssl.create_default_context(cafile="deploy/ci/cert.pem"); assert urllib.request.urlopen("https://localhost:18443/health/",context=c).status==200
try: urllib.request.urlopen("https://localhost:18443/health/ready/",context=c,timeout=15)
except urllib.error.HTTPError as e: assert e.code==503
else: raise AssertionError("Readiness must fail without MongoDB")
print("Liveness200/readiness503 during stopped DB: passed")' > deploy/ci/readiness.txt
dc start mongo
dc up -d --wait mongo
# Only the fixed disposable database is dropped/restored. No team volume is used.
start=$(date +%s)
dc exec -T mongo mongodump --db orgflow_deployment_smoke --archive=/tmp/smoke.archive > deploy/ci/backup.txt 2>&1
dc exec -T mongo mongosh --quiet --eval 'db.getSiblingDB("orgflow_deployment_smoke").dropDatabase()' >> deploy/ci/backup.txt
dc exec -T mongo mongorestore --archive=/tmp/smoke.archive >> deploy/ci/backup.txt 2>&1
dc restart web
dc up -d --wait web
python deploy/smoke_http.py --ca deploy/ci/cert.pem --fixtures deploy/ci/fixtures.json --phase restored > deploy/ci/https-restored.json
dc exec -T web python manage.py shell -c 'from tasks.models import Task; from accounts.models import Profile; from django.contrib.auth import get_user_model; t=Task.objects.get(title="Synthetic deployment claim"); assert t.status=="done" and t.version==2 and len(t.history)==3; assert Task.objects.filter(origin_key__startswith="meeting:").count()==1; assert get_user_model().objects.count()==4; print("Restored task state, CAS version, audit, import uniqueness and accounts: passed")' > deploy/ci/restore-data.txt
end=$(date +%s)
echo "Backup/drop/restore/restart/HTTPS smoke elapsed seconds: $((end-start))" >> deploy/ci/restore-data.txt
test $((end-start)) -lt 1800
echo 'Container deployment smoke passed.'
