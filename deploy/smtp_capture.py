"""Disposable CI-only SMTP sink; stores in memory and never delivers mail.

Bind inside the private CI network. Its unauthenticated HTTP message body API
must never be published beyond the disposable test environment. No request,
recipient or message content is logged. Requires only Python 3.12 stdlib.
"""

import argparse
import json
import re
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_MESSAGE_BYTES = 1024 * 1024
MAX_MESSAGES = 100
MESSAGES = []
MESSAGE_LOCK = threading.Lock()


class SMTPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class SMTPHandler(socketserver.StreamRequestHandler):
    timeout = 20

    def reply(self, text):
        self.wfile.write((text + "\r\n").encode("ascii"))
        self.wfile.flush()

    def handle(self):
        mail_from = None
        recipients = []
        self.reply("220 orgflow-ci-capture ESMTP")
        try:
            while True:
                raw = self.rfile.readline(65537)
                if not raw:
                    return
                if len(raw) > 65536:
                    self.reply("500 Command too long")
                    return
                command, _, argument = raw.decode("utf-8", "replace").strip().partition(" ")
                command = command.upper()
                if command in {"EHLO", "HELO"}:
                    self.reply("250-orgflow-ci-capture")
                    self.reply(f"250 SIZE {MAX_MESSAGE_BYTES}")
                elif command == "MAIL":
                    match = re.fullmatch(r"FROM:\s*<([^>]*)>(?:\s+.*)?", argument, re.I)
                    if match is None:
                        self.reply("501 Invalid sender syntax")
                        continue
                    mail_from = match.group(1)
                    recipients = []
                    self.reply("250 Sender accepted")
                elif command == "RCPT":
                    match = re.fullmatch(r"TO:\s*<([^>]+)>(?:\s+.*)?", argument, re.I)
                    if mail_from is None:
                        self.reply("503 MAIL required")
                    elif match is None or len(recipients) >= 50:
                        self.reply("501 Invalid recipient syntax or limit")
                    else:
                        recipients.append(match.group(1))
                        self.reply("250 Recipient captured locally")
                elif command == "DATA":
                    if mail_from is None or not recipients:
                        self.reply("503 MAIL and RCPT required")
                        continue
                    self.reply("354 End with <CRLF>.<CRLF>")
                    chunks = []
                    size = 0
                    while True:
                        line = self.rfile.readline(MAX_MESSAGE_BYTES + 1)
                        if not line:
                            return
                        if line in {b".\r\n", b".\n"}:
                            break
                        if line.startswith(b".."):
                            line = line[1:]
                        size += len(line)
                        if size > MAX_MESSAGE_BYTES:
                            self.reply("552 Message limit exceeded")
                            return
                        chunks.append(line)
                    with MESSAGE_LOCK:
                        if len(MESSAGES) >= MAX_MESSAGES:
                            self.reply("452 Capture storage full")
                            return
                        MESSAGES.append({
                            "mail_from": mail_from,
                            "recipients": list(recipients),
                            "data": b"".join(chunks).decode("utf-8", "replace"),
                        })
                    mail_from = None
                    recipients = []
                    self.reply("250 Message retained in disposable capture")
                elif command == "RSET":
                    mail_from = None
                    recipients = []
                    self.reply("250 Reset")
                elif command == "NOOP":
                    self.reply("250 OK")
                elif command == "QUIT":
                    self.reply("221 Bye")
                    return
                else:
                    self.reply("502 Command not supported")
        except (ConnectionError, TimeoutError):
            return


class CaptureHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/messages":
            self.send_error(404)
            return
        with MESSAGE_LOCK:
            payload = json.dumps({"messages": list(MESSAGES)}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--smtp-port", type=int, default=8026)
    parser.add_argument("--http-port", type=int, default=8025)
    args = parser.parse_args()
    with ThreadingHTTPServer((args.bind, args.http_port), CaptureHTTPHandler) as http:
        with SMTPServer((args.bind, args.smtp_port), SMTPHandler) as smtp:
            thread = threading.Thread(target=http.serve_forever, daemon=True)
            thread.start()
            try:
                smtp.serve_forever()
            finally:
                http.shutdown()


if __name__ == "__main__":
    main()
