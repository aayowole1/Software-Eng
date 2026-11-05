"""Authenticated, closed-loop page-response benchmark for SCRUM-80.

Use synthetic accounts and an explicitly selected host. Credentials are read
from a local JSON file and never included in the result. This measures HTML
HTTP responses, not browser rendering, assets, provider calls or write traffic.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import threading
import time
from urllib.parse import urlsplit

import requests


def summary(samples):
    times = sorted(row["seconds"] for row in samples)
    count = len(times)
    good = sum(row["ok"] and row["seconds"] < 3 for row in samples)
    return {
        "requests": count,
        "successful": sum(row["ok"] for row in samples),
        "errors": sum(not row["ok"] for row in samples),
        "successful_under_3s_percent": round(100 * good / count, 3) if count else 0,
        "p50_seconds": round(times[math.ceil(count * .50) - 1], 4) if count else None,
        "p95_seconds": round(times[math.ceil(count * .95) - 1], 4) if count else None,
        "max_seconds": round(times[-1], 4) if count else None,
        "meets_95_percent_under_3s": bool(count) and good / count >= .95,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--accounts-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--users", type=int, default=25)
    parser.add_argument("--think-seconds", type=float, default=1)
    args = parser.parse_args()
    target = urlsplit(args.base_url)
    if target.scheme not in {"http", "https"} or not target.netloc or target.username or target.password or target.query or target.fragment:
        parser.error("Use an explicit HTTP(S) origin without credentials, query or fragment.")
    if args.seconds < 1 or args.users < 1 or args.think_seconds < 0:
        parser.error("Duration/users must be positive and think time non-negative.")
    base = args.base_url.rstrip("/")
    accounts = json.loads(args.accounts_file.read_text(encoding="utf-8"))
    if len(accounts) < args.users:
        parser.error("Provide a separate synthetic account for each virtual user.")
    sessions = []
    startup = []
    for account in accounts[:args.users]:
        session = requests.Session()
        session.trust_env = False
        login = session.get(base + "/accounts/login/", timeout=15)
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', login.text)
        if not token:
            raise RuntimeError("Login form did not supply a CSRF token.")
        started = time.perf_counter()
        response = session.post(base + "/accounts/login/", data={
            "username": account["username"], "password": account["password"],
            "csrfmiddlewaretoken": token.group(1),
        }, headers={"Referer": base + "/accounts/login/"}, allow_redirects=False, timeout=15)
        elapsed = time.perf_counter() - started
        if response.status_code != 302 or "sessionid" not in session.cookies:
            raise RuntimeError("A synthetic account failed authentication; no load test started.")
        startup.append({"seconds": elapsed, "ok": True})
        for path in account["paths"]:
            warm = session.get(base + path, allow_redirects=False, timeout=15)
            if warm.status_code != 200:
                raise RuntimeError(f"Warm-up failed for {path}: HTTP {warm.status_code}")
        sessions.append((session, account["paths"]))

    samples = []
    lock = threading.Lock()
    start = time.perf_counter()
    deadline = start + args.seconds

    def worker(index):
        session, paths = sessions[index]
        position = index
        try:
            while time.perf_counter() < deadline:
                path = paths[position % len(paths)]
                began = time.perf_counter()
                status = None
                error = None
                try:
                    response = session.get(base + path, allow_redirects=False, timeout=(3, 10))
                    status = response.status_code
                    ok = status == 200
                except requests.RequestException as failure:
                    ok = False
                    error = type(failure).__name__
                row = {"path": path, "seconds": time.perf_counter() - began,
                       "ok": ok, "status": status, "error": error}
                with lock:
                    samples.append(row)
                position += 1
                time.sleep(min(args.think_seconds, max(0, deadline - time.perf_counter())))
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=args.users) as pool:
        futures = [pool.submit(worker, index) for index in range(args.users)]
        while any(not future.done() for future in futures):
            time.sleep(min(30, max(1, deadline - time.perf_counter())))
            with lock:
                progress = summary(samples)
            print(json.dumps({"elapsed_seconds": round(time.perf_counter() - start), **progress}), flush=True)
        for future in futures:
            future.result()
    paths = sorted({sample["path"] for sample in samples})
    result = {
        "base_url": base, "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "platform": platform.platform(), "python": platform.python_version(),
        "configured_duration_seconds": args.seconds, "measured_elapsed_seconds": round(time.perf_counter() - start, 3),
        "virtual_users": args.users, "think_seconds": args.think_seconds,
        "workload": "Authenticated HTML GET pages; closed loop; no assets/browser rendering/provider calls/writes",
        "aggregate": summary(samples), "login_post_setup_only": summary(startup),
        "per_path": {path: summary([row for row in samples if row["path"] == path]) for path in paths},
        "error_statuses": {str(status): sum(row["status"] == status and not row["ok"] for row in samples)
                           for status in set(row["status"] for row in samples if not row["ok"])},
        "error_types": {error: sum(row["error"] == error for row in samples)
                        for error in set(row["error"] for row in samples if row["error"])},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result_file": str(args.output), "aggregate": result["aggregate"]}), flush=True)
    return 0 if result["aggregate"]["meets_95_percent_under_3s"] and not result["aggregate"]["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
