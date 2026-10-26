"""Complete a real HTTPS password reset using CI's internal-only SMTP capture.

Only the separate synthetic reset fixture is changed. Never logs reset links,
tokens, mail bodies, cookies or passwords. No external email is delivered.
"""

import argparse
import email
import email.policy
import email.utils
import http.cookiejar
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request

RECIPIENT = "reset@example.invalid"
USERNAME = "smoke_reset"
OLD_PASSWORD = "Synthetic-Smoke-2026!"
NEW_PASSWORD = "Changed-Synthetic-Smoke-2026!"


class SmokeFailure(Exception):
    """Use only fixed, token-free messages in this exception."""


def require(condition, message):
    if not condition:
        raise SmokeFailure(message)


def origin(url):
    parsed = urllib.parse.urlsplit(url)
    return parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, base):
        self.allowed_origin = origin(base)

    def redirect_request(self, request, response, code, message, headers, newurl):
        require(origin(newurl) == self.allowed_origin, "Unexpected cross-origin redirect.")
        return super().redirect_request(request, response, code, message, headers, newurl)


class Session:
    def __init__(self, base, context):
        self.base = base
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context),
            urllib.request.HTTPCookieProcessor(self.cookies), SameOriginRedirect(base),
        )

    def request(self, path, data=None):
        url = urllib.parse.urljoin(self.base + "/", path)
        require(origin(url) == origin(self.base), "Unexpected request origin.")
        headers = {}
        if data is not None:
            token = next((cookie.value for cookie in self.cookies if cookie.name == "csrftoken"), None)
            require(bool(token), "Missing CSRF cookie.")
            data = urllib.parse.urlencode({**data, "csrfmiddlewaretoken": token}).encode("utf-8")
            headers["Referer"] = self.base + "/"
        response = self.opener.open(urllib.request.Request(url, data=data, headers=headers), timeout=35)
        require(response.status == 200, "Unexpected application HTTP status.")
        return response.read().decode("utf-8"), response.geturl()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="https://localhost:18443")
    parser.add_argument("--ca", required=True)
    parser.add_argument("--capture", default="http://127.0.0.1:8025/messages")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    parsed_base = urllib.parse.urlsplit(base)
    parsed_capture = urllib.parse.urlsplit(args.capture)
    require(parsed_base.scheme == "https" and parsed_base.hostname in {"localhost", "127.0.0.1", "::1"}, "HTTPS loopback test base is required.")
    require(not parsed_base.username and not parsed_base.password and parsed_base.path in {"", "/"} and not parsed_base.query and not parsed_base.fragment, "Use a plain test base origin.")
    require(parsed_capture.scheme == "http" and parsed_capture.hostname in {"localhost", "127.0.0.1", "::1"} and parsed_capture.path == "/messages", "Loopback CI capture endpoint is required.")
    context = ssl.create_default_context(cafile=args.ca)

    # Exactly one HTTP capture read; do not print its body or follow its URLs.
    capture = urllib.request.build_opener(SameOriginRedirect(args.capture))
    with capture.open(args.capture, timeout=15) as response:
        require(response.status == 200, "Capture was unavailable.")
        payload = json.load(response)
    messages = payload.get("messages", [])
    require(len(messages) == 1, "Expected exactly one captured reset email.")
    message = messages[0]
    require([address.lower() for address in message.get("recipients", [])] == [RECIPIENT], "Unexpected captured recipient.")
    mime = email.message_from_string(message.get("data", ""), policy=email.policy.default)
    require([address.lower() for _, address in email.utils.getaddresses(mime.get_all("To", []))] == [RECIPIENT], "Unexpected message recipient header.")
    body_part = mime.get_body(preferencelist=("plain",))
    require(body_part is not None, "Reset email has no plain-text body.")
    links = [url for url in re.findall(r"https?://[^\s<>\"']+", body_part.get_content()) if "/accounts/reset/" in url]
    require(len(links) == 1, "Expected one password-reset link.")
    reset_url = links[0]
    parsed_reset = urllib.parse.urlsplit(reset_url)
    require(origin(reset_url) == origin(base) and parsed_reset.scheme == "https", "Reset link must use the trusted HTTPS test origin.")
    require(not parsed_reset.username and not parsed_reset.password and not parsed_reset.query and not parsed_reset.fragment, "Unexpected reset-link structure.")
    require(re.fullmatch(r"/accounts/reset/[A-Za-z0-9_-]+/[A-Za-z0-9-]+/", parsed_reset.path) is not None, "Unexpected reset-link path.")

    reset = Session(base, context)
    body, form_url = reset.request(parsed_reset.path)
    require('name="new_password1"' in body and 'name="new_password2"' in body, "Reset form was unavailable.")
    require(urllib.parse.urlsplit(form_url).path.endswith("/set-password/"), "Reset token was not exchanged for a session value.")
    body, done_url = reset.request(urllib.parse.urlsplit(form_url).path, {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD})
    require(urllib.parse.urlsplit(done_url).path == "/accounts/reset/done/" and "Password changed" in body, "Password reset did not complete.")

    changed = Session(base, context)
    changed.request("/accounts/login/")
    _, login_url = changed.request("/accounts/login/", {"username": USERNAME, "password": NEW_PASSWORD})
    require(urllib.parse.urlsplit(login_url).path != "/accounts/login/", "New synthetic password was rejected.")
    _, profile_url = changed.request("/accounts/me/")
    require(urllib.parse.urlsplit(profile_url).path == "/accounts/me/", "Changed-password session was not authenticated.")

    previous = Session(base, context)
    previous.request("/accounts/login/")
    _, old_login_url = previous.request("/accounts/login/", {"username": USERNAME, "password": OLD_PASSWORD})
    require(urllib.parse.urlsplit(old_login_url).path == "/accounts/login/", "Old synthetic password was accepted.")
    _, denied_profile_url = previous.request("/accounts/me/")
    require(urllib.parse.urlsplit(denied_profile_url).path == "/accounts/login/", "Old-password attempt gained protected access.")
    print(json.dumps({"smtp": "captured internally; no external delivery", "https_reset_link": True, "trusted_test_ca": True, "csrf_reset": "passed", "changed_password_login": "passed", "old_password_denied": True}))


if __name__ == "__main__":
    try:
        main()
    except SmokeFailure as error:
        print(json.dumps({"email_smoke": "failed", "reason": str(error)}))
        sys.exit(1)
    except Exception as error:
        # URL/HTTP exceptions can contain the reset URL. Never echo them.
        print(json.dumps({"email_smoke": "failed", "error_type": type(error).__name__}))
        sys.exit(1)
