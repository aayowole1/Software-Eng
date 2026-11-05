# Local page-response benchmark (SCRUM-80)

The user selected local validation. This procedure measures authenticated HTML
responses on the Windows local host; it does not certify deployment-host latency,
browser rendering/asset load, live Google/AI/STT calls or write operations.

## Dataset and workload

Use a new, isolated MongoDB database whose name begins `orgflow_perf_`.
`deploy/seed_benchmark.py` refuses other names or existing application records.
It creates 500 active organization members (five Officers), 100 events, 1,000
tasks, 10 committees, 2,500 RSVPs, 1,250 attendance rows, 50 announcements,
50 resource links and 20 meeting drafts. No real member data or provider calls
are involved. Synthetic passwords are randomly generated with the normal
application password hasher and saved only to the supplied local accounts file.

The load client uses 25 separate authenticated sessions (20 Members and five
Officers), a closed loop, one-second think time and 600 measured seconds after
login and page warm-up. Each user cycles through dashboard, roster, committees,
tasks, events, announcements, resources and personal profile. Officers also read
the application queue and meeting drafts. External resource URLs are not opened.

Each response must be HTTP 200; redirects and network errors do not count as
successful fast requests. The pass criterion is at least 95% successful requests
strictly below three seconds. The client also requires zero errors for its exit
status to pass. It records aggregate and per-page nearest-rank p50/p95/max,
counts, error statuses and a separate login-POST setup summary. Login/form
warm-up is not included in the measured page request population.

## Reproduce

1. Start a separate local MongoDB process/volume and select a new database.
   Never point seeding at the review or production database.
2. Configure the environment explicitly, without a private dotenv file:

   ```powershell
   $env:DJANGO_SETTINGS_MODULE = 'deploy.settings_benchmark'
   $env:PYTHON_DOTENV_DISABLED = '1'
   $env:MONGODB_URI = 'mongodb://127.0.0.1:27031'
   $env:MONGODB_NAME = 'orgflow_perf_unique_run_name'
   $env:GOOGLE_CLIENT_ID = ''
   $env:OPENAI_API_KEY = ''
   $env:DEEPGRAM_API_KEY = ''
   python manage.py migrate --noinput
   python deploy/seed_benchmark.py
   ```

3. In that environment start the local server on a separate port:
   `python manage.py runserver 127.0.0.1:8001 --noreload`.
   This uses DEBUG=False and normal password hashing, but remains Django's
   threaded development server, not the production Gunicorn/TLS topology.
4. Run the client from another terminal:

   ```text
   python deploy/benchmark_pages.py --base-url http://127.0.0.1:8001 --accounts-file .validation/performance-accounts.json --seconds 600 --users 25 --think-seconds 1 --output .validation/scrum80-result.json
   ```

5. Retain sanitized result/dataset metadata and application source revision;
   keep accounts files, database files, cookies and logs out of Git/images.
   Stop only the benchmark processes you started. The normal review app may
   continue running independently on port 8000.

The result file contains no account passwords, cookies or page bodies. Do not
publish the accounts JSON. `.validation/` is excluded from Git and Docker.
Run `python -m unittest deploy.test_benchmark_pages` to check threshold handling.

## Interpretation

Keep failed baselines as evidence. Investigate slow pages and repeat the same
dataset/workload after a fix. A local pass supports the agreed local measurement
task; the intended VM/container/reverse-proxy/TLS environment needs its own run
before claiming production performance acceptance. This is a closed-loop test,
so it does not establish capacity at a fixed externally imposed arrival rate.
