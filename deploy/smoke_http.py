"""Real HTTPS smoke against disposable CI containers; only synthetic fixtures."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import http.cookiejar
import json
import re
import ssl
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request

p = argparse.ArgumentParser()
p.add_argument('--base', default='https://localhost:18443')
p.add_argument('--ca', required=True)
p.add_argument('--fixtures', required=True)
p.add_argument('--phase', choices=['initial', 'restored'], default='initial')
a = p.parse_args()
fixture = json.load(open(a.fixtures, encoding='utf-8'))
context = ssl.create_default_context(cafile=a.ca)

class Session:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), urllib.request.HTTPCookieProcessor(self.cookies))

    def request(self, path, data=None, expected=200, csrf=True):
        headers = {}
        if data is not None:
            data = dict(data)
            if csrf:
                token = next(c.value for c in self.cookies if c.name == 'csrftoken')
                data['csrfmiddlewaretoken'] = token
            headers['Referer'] = a.base + path
            data = urllib.parse.urlencode(data).encode()
        try:
            result = self.opener.open(urllib.request.Request(a.base + path, data=data, headers=headers), timeout=35)
        except urllib.error.HTTPError as error:
            result = error
        body = result.read().decode()
        assert result.code == expected, (path, result.code, expected)
        return body, result

    def login(self, name, password='Synthetic-Smoke-2026!'):
        self.request('/accounts/login/')
        body, result = self.request('/accounts/login/', {'username': 'smoke_' + name, 'password': password})
        assert '/accounts/login/' not in result.url, 'Login failed'
        return body

s = Session()
_, response = s.request('/health/')
assert response.headers['Strict-Transport-Security']
assert response.headers['X-Content-Type-Options'] == 'nosniff'
s.request('/health/ready/')
body, _ = s.request('/accounts/login/')
assets = re.findall(r'(?:src|href)="(/static/[^"?]+)', body)
assert assets, 'No static assets found'
for path in set(assets):
    _, result = s.request(path)
    assert 'max-age=' in result.headers.get('Cache-Control', '')
s.login('member')
assert all(c.secure for c in s.cookies if c.name in ('sessionid', 'csrftoken'))
task_path = '/tasks/' + fixture['task'] + '/'
body, _ = s.request(task_path)
if a.phase == 'initial':
    s.request(task_path + 'claim/', {'version': '0'}, expected=403, csrf=False)
    s.request(task_path + 'claim/', {'version': '0'})
    s.request(task_path + 'status/', {'version': '1', 'status': 'done'})
    _, result = s.request('/tasks/new/', expected=403)
else:
    assert 'Done' in body and 'smoke_member' in body
outside = Session()
outside.login('outsider')
outside.request(task_path, expected=404)
officer = Session()
officer.login('officer')
if a.phase == 'initial':
    path = '/tasks/from-meeting/' + fixture['draft'] + '/'
    officer.request(path)
    body, _ = officer.request(path, {'priority': 'medium'})
    assert 'Created 1 task(s); 0 already existed.' in body
    body, _ = officer.request(path, {'priority': 'medium'})
    assert 'Created 0 task(s); 1 already existed.' in body
    # SMTP delivery is inspected separately in the disposable capture service.
    reset = Session()
    reset.request('/accounts/password-reset/')
    reset.request('/accounts/password-reset/', {'email': 'reset@example.invalid'})
latencies = []
def read_task(_):
    started = time.perf_counter()
    # No simultaneous writes or claims. Each reader has its own cookie jar.
    reader = Session()
    reader.cookies = s.cookies
    reader.opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), urllib.request.HTTPCookieProcessor(reader.cookies))
    reader.request('/tasks/')
    return time.perf_counter() - started
with ThreadPoolExecutor(max_workers=5) as pool:
    latencies = list(pool.map(read_task, range(25)))
print(json.dumps({'phase': a.phase, 'https': 'trusted private test certificate', 'static_assets': len(set(assets)), 'secure_cookies': True, 'task_role_and_committee_checks': 'passed', 'read_requests': len(latencies), 'read_p95_seconds': round(sorted(latencies)[int(.95 * len(latencies))], 4), 'scope': 'bounded CI smoke; not the 25-user, 10-minute NFR benchmark'}, indent=2))
