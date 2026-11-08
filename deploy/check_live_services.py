"""Redacted prerequisites; paid synthetic probes require two explicit opt-ins.

No Django settings import, database writes, email delivery, or OAuth login occurs.
Run with --help for the bounded live options. Never print exception messages:
provider exceptions and configuration values can contain credentials.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import re
import socket
import ssl
import sys
import tempfile
import time
from urllib.parse import urlsplit
import wave


ROOT = Path(__file__).resolve().parents[1]
ALLOW_FLAG = "ORGFLOW_ALLOW_LIVE_CHECKS"
WALL_SECONDS = 30
NOTES = (
    "This is a fictional OrgFlow service check with no real people or member data. "
    "The group discussed a practice meeting. Action: Reserve the blue meeting room. "
    "Action: Send the synthetic agenda. No other work was assigned."
)
CONFIG_NAMES = (
    "OPENAI_API_KEY", "OPENAI_MODEL", "DEEPGRAM_API_KEY", "GOOGLE_CLIENT_ID",
    "DJANGO_EMAIL_POLICY", "EMAIL_BACKEND", "EMAIL_HOST", "EMAIL_PORT", "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD", "EMAIL_USE_TLS", "EMAIL_USE_SSL", "DEFAULT_FROM_EMAIL",
)
ENDPOINTS = {
    "openai": "api.openai.com",
    "deepgram": "api.deepgram.com",
    "google_sign_in": "accounts.google.com",
    "google_oauth": "oauth2.googleapis.com",
    "google_certificates": "www.googleapis.com",
}


def configuration():
    values = {}
    env_file = ROOT / ".env"
    dotenv_status = "absent"
    if env_file.is_file():
        try:
            from dotenv import dotenv_values

            # No interpolation: do not expand secrets into diagnostic values.
            values = dict(dotenv_values(env_file, interpolate=False))
            dotenv_status = "loaded"
        except Exception:
            dotenv_status = "unreadable_or_dependency_missing"
    for name in CONFIG_NAMES:
        if name in os.environ:
            values[name] = os.environ[name]
    return {key: str(values.get(key) or "").strip() for key in CONFIG_NAMES}, dotenv_status


def tls_check(item):
    name, host = item
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=5) as raw:
            with context.wrap_socket(raw, server_hostname=host) as connection:
                return name, {"status": "passed", "certificate_verified": True,
                              "tls_version": connection.version()}
    except Exception as error:
        return name, {"status": "failed", "certificate_verified": False,
                      "error_type": type(error).__name__}


def origin_check(origin):
    if not origin:
        return {"status": "blocked", "reason": "browser_origin_not_supplied",
                "cloud_allowlist_verified": False}
    try:
        parts = urlsplit(origin)
        local = parts.hostname == "localhost"
        host = (parts.hostname or "").encode("idna").decode("ascii")
        valid_host = bool(host) and len(host) <= 253 and all(
            re.fullmatch(r"(?!-)[a-zA-Z0-9-]{1,63}(?<!-)", label)
            for label in host.split(".")
        )
        # Google permits localhost HTTP for development; deployed origins use HTTPS.
        valid = valid_host and parts.scheme in ("http", "https")
        valid = valid and (parts.scheme == "https" or local)
        valid = valid and not (parts.username or parts.password or parts.query or parts.fragment)
        valid = valid and parts.path == "" and parts.port != 0
        valid = valid and not any(character.isspace() for character in origin)
        valid = valid and not parts.netloc.endswith(":")
        return {"status": "syntax_passed" if valid else "failed",
                "https_or_localhost_http": bool(valid),
                "cloud_allowlist_verified": False,
                "reason": "operator_must_match_exact_scheme_host_port_in_google_cloud"}
    except (UnicodeError, ValueError, TypeError):
        return {"status": "failed", "reason": "invalid_origin",
                "cloud_allowlist_verified": False}


def inspect_audio(path, confirmed):
    if path is None:
        return {"status": "blocked", "reason": "synthetic_wav_not_supplied"}
    if not confirmed:
        return {"status": "blocked", "reason": "synthetic_audio_confirmation_required"}
    try:
        resolved = Path(path).resolve(strict=True)
        if resolved.is_relative_to(ROOT / "meetings" / "testdata"):
            return {"status": "blocked", "reason": "undocumented_repository_audio_not_allowed"}
        if not resolved.is_file() or resolved.stat().st_size > 1_000_000:
            return {"status": "blocked", "reason": "wav_file_missing_or_too_large"}
        with wave.open(str(resolved), "rb") as audio:
            frames = audio.getnframes()
            valid = (audio.getnchannels() == 1 and audio.getsampwidth() == 2
                     and audio.getframerate() == 16000 and audio.getcomptype() == "NONE"
                     and 0 < frames <= 320000)
            if not valid:
                return {"status": "blocked", "reason": "require_pcm16_mono_16000hz_0_to_20_seconds"}
            pcm = audio.readframes(frames)
            if len(pcm) != frames * 2:
                return {"status": "blocked", "reason": "truncated_wav"}
        return {"status": "ready", "synthetic_confirmed_by_operator": True,
                "duration_seconds": round(frames / 16000, 4), "pcm_bytes": len(pcm)}
    except Exception as error:
        return {"status": "blocked", "reason": "invalid_wav",
                "error_type": type(error).__name__}


def worker(service, audio_path):
    """Internal child: one adapter invocation, no secrets or responses in stdout."""
    if os.environ.get(ALLOW_FLAG) != "synthetic-only":
        return {"status": "blocked", "reason": "explicit_live_environment_required"}
    config, dotenv_status = configuration()
    if dotenv_status == "unreadable_or_dependency_missing":
        return {"status": "blocked", "reason": "configuration_unreadable"}
    sys.path.insert(0, str(ROOT))
    started = time.perf_counter()
    try:
        if service == "openai":
            if not config["OPENAI_API_KEY"]:
                return {"status": "blocked", "reason": "openai_key_missing"}
            import openai

            original_client = openai.OpenAI
            calls = []

            def capped_client(**kwargs):
                kwargs.update(api_key=config["OPENAI_API_KEY"], timeout=20.0, max_retries=0,
                              base_url="https://api.openai.com/v1")
                client = original_client(**kwargs)
                original_create = client.chat.completions.create

                def capped_create(*args, **request):
                    if calls:
                        raise RuntimeError("Only one synthetic request is permitted")
                    calls.append(True)
                    request["max_tokens"] = 250
                    return original_create(*args, **request)

                client.chat.completions.create = capped_create
                return client

            openai.OpenAI = capped_client
            os.environ["OPENAI_API_KEY"] = config["OPENAI_API_KEY"]
            os.environ["OPENAI_MODEL"] = config["OPENAI_MODEL"] or "gpt-4o-mini"
            from meetings.ai import summarize_meeting

            assert len(NOTES.split()) <= 100
            result = summarize_meeting(NOTES)
            valid = bool(result.summary) and len(result.action_items) == 2
            joined = " ".join(result.action_items).lower()
            valid = valid and "blue meeting room" in joined and "synthetic agenda" in joined
            return {"status": "passed" if valid else "failed",
                    "schema_and_known_actions_valid": bool(valid), "request_count": len(calls),
                    "input_words": len(NOTES.split()), "max_output_tokens": 250,
                    "sdk_retries": 0, "elapsed_seconds": round(time.perf_counter() - started, 3)}
        if not config["DEEPGRAM_API_KEY"]:
            return {"status": "blocked", "reason": "deepgram_key_missing"}
        audio = inspect_audio(audio_path, True)
        if audio["status"] != "ready":
            return audio
        os.environ["DEEPGRAM_API_KEY"] = config["DEEPGRAM_API_KEY"]
        from meetings.stt import DeepgramTranscriber

        transcriber = DeepgramTranscriber()
        try:
            with wave.open(str(audio_path), "rb") as source:
                # Keep the transmission bounded even if a local file changes
                # after preflight. Never stream an unbounded file to a provider.
                pcm = source.readframes(320000)
                if source.readframes(1) or len(pcm) != audio["pcm_bytes"]:
                    return {"status": "blocked", "reason": "audio_changed_after_validation"}
                for offset in range(0, len(pcm), 32000):
                    transcriber.add_pcm(pcm[offset:offset + 32000])
            transcript = transcriber.finish()
            return {"status": "passed" if transcript.strip() else "failed",
                    "nonempty_final_transcript": bool(transcript.strip()),
                    "transcript_characters": len(transcript), "request_count": 1,
                    "audio": audio, "adapter_temp_file_removed": not transcriber.audio_path.exists(),
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "limit": "nonempty round_trip only; transcription accuracy not established"}
        finally:
            transcriber.discard()
    except Exception as error:
        # Do not disclose provider response text, credentials, transcript, or file paths.
        return {"status": "failed", "error_type": type(error).__name__,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "reason": "redacted_provider_or_adapter_error_do_not_automatically_retry"}


def _worker_entry(service, audio_path, scratch, results):
    # A multiprocessing target, not a public command-line bypass. The only CLI
    # route to this process is main() after every selected prerequisite passes.
    os.environ.update(TMP=scratch, TEMP=scratch, TMPDIR=scratch)
    tempfile.tempdir = None
    with open(os.devnull, "w") as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
        results.put(worker(service, audio_path))


def run_live(service, audio_path):
    with tempfile.TemporaryDirectory(prefix="orgflow-synthetic-check-") as scratch:
        context = multiprocessing.get_context("spawn")
        results = context.Queue()
        process = context.Process(target=_worker_entry,
                                  args=(service, audio_path, scratch, results), daemon=True)
        try:
            process.start()
            process.join(WALL_SECONDS)
            if process.is_alive():
                process.terminate()
                process.join(3)
                if process.is_alive():
                    process.kill()
                    process.join()
                return {"status": "timed_out", "wall_timeout_seconds": WALL_SECONDS,
                        "reason": "request_may_have_been_billed_do_not_automatically_retry"}
            if process.exitcode != 0:
                return {"status": "failed", "reason": "worker_failed_output_redacted"}
            payload = results.get(timeout=1)
            payload["wall_timeout_seconds"] = WALL_SECONDS
            return payload
        except Exception as error:
            return {"status": "failed", "error_type": type(error).__name__,
                    "reason": "worker_result_unavailable_output_redacted"}
        finally:
            if process.pid and process.is_alive():
                process.terminate()
                process.join()
            results.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Opt into paid synthetic provider probes")
    parser.add_argument("--service", choices=("both", "openai", "deepgram"), default="both")
    parser.add_argument("--audio", type=Path, help="New synthetic PCM16/mono/16kHz WAV, at most 20 seconds")
    parser.add_argument("--synthetic-audio-confirmed", action="store_true")
    parser.add_argument("--origin", help="Exact Google authorized JavaScript origin, no path or slash")
    parser.add_argument("--no-network", action="store_true", help="Skip certificate-verified TLS handshakes")
    parser.add_argument("--output", type=Path, help="Write the same redacted JSON report")
    args = parser.parse_args(argv)
    config, dotenv_status = configuration()
    presence = {name: bool(config[name]) for name in CONFIG_NAMES}
    available = {name: importlib.util.find_spec(name) is not None
                 for name in ("openai", "websocket", "dotenv")}
    smtp_names = ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD", "DEFAULT_FROM_EMAIL")
    policy = config["DJANGO_EMAIL_POLICY"].lower()
    smtp_selected = (policy == "smtp" if policy else
                     config["EMAIL_BACKEND"] == "django.core.mail.backends.smtp.EmailBackend")
    tls_value = (config["EMAIL_USE_TLS"] or "true").lower()
    ssl_value = (config["EMAIL_USE_SSL"] or "false").lower()
    valid_security = tls_value in ("true", "false") and ssl_value in ("true", "false")
    one_secure_route = (tls_value == "true") != (ssl_value == "true")
    try:
        valid_port = 1 <= int(config["EMAIL_PORT"] or ("465" if ssl_value == "true" else "587")) <= 65535
    except ValueError:
        valid_port = False
    smtp_ready = (all(presence[name] for name in smtp_names) and valid_port
                  and smtp_selected and valid_security and one_secure_route)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "synthetic_live_requested" if args.live else "prerequisites_only",
        "credential_values_redacted": True, "dotenv_status": dotenv_status,
        "configuration_presence": presence, "dependencies_available": available,
        "tls_endpoints": {},
        "openai": {"status": "ready_for_opt_in" if presence["OPENAI_API_KEY"] and available["openai"] else "blocked",
                   "live_passed": False, "model_override_present": presence["OPENAI_MODEL"],
                   "default_model": "gpt-4o-mini", "default_model_deprecated_shutdown": "2027-01-14"},
        "deepgram": {"status": "ready_for_opt_in" if presence["DEEPGRAM_API_KEY"] and available["websocket"] else "blocked",
                     "live_passed": False, "model": "nova-3", "format": "linear16_mono_16000hz",
                     "audio": inspect_audio(args.audio, args.synthetic_audio_confirmed)},
        "google": {"status": "configured_unverified" if presence["GOOGLE_CLIENT_ID"] else "blocked",
                   "origin": origin_check(args.origin), "live_login_passed": False},
        "smtp": {"status": "configured_unverified" if smtp_ready else "blocked",
                 "authenticated_tls_configuration_complete": bool(smtp_ready),
                 "delivery_passed": False, "email_sent": False},
        "scope": "TLS is connectivity only; no authentication, quota, delivery, browser or deployment acceptance claim",
        "application_timeout_limits": {
            "openai": "30s SDK timeout per attempt, max_retries=2: up to 3 attempts plus retry delays; no 30s total guarantee",
            "deepgram": "10s connection; 60s receive deadline after audio send; send time additional; no 30s total guarantee",
            "synthetic_checker": "one invocation per selected provider, 30s child wall timeout; no automatic retries",
        },
    }
    if args.no_network:
        report["tls_endpoints"] = {name: {"status": "not_checked"} for name in ENDPOINTS}
    else:
        with ThreadPoolExecutor(max_workers=len(ENDPOINTS)) as pool:
            report["tls_endpoints"] = dict(pool.map(tls_check, ENDPOINTS.items()))
    if args.live:
        selected = ("openai", "deepgram") if args.service == "both" else (args.service,)
        reasons = []
        if os.environ.get(ALLOW_FLAG) != "synthetic-only":
            reasons.append("explicit_process_environment_synthetic_only_flag_required")
        if dotenv_status == "unreadable_or_dependency_missing":
            reasons.append("configuration_unreadable")
        for service in selected:
            if report[service]["status"] != "ready_for_opt_in":
                reasons.append(service + "_key_or_dependency_missing")
            if not args.no_network and report["tls_endpoints"][service]["status"] != "passed":
                reasons.append(service + "_tls_prerequisite_failed")
        if "deepgram" in selected and report["deepgram"]["audio"]["status"] != "ready":
            reasons.append("deepgram_synthetic_audio_prerequisite_missing")
        if reasons:
            report["live_gate"] = {"status": "blocked", "reasons": reasons, "provider_calls": 0}
        else:
            report["live_gate"] = {"status": "authorized_synthetic_only"}
            for service in selected:
                result = run_live(service, args.audio)
                report[service]["probe"] = result
                report[service]["live_passed"] = result["status"] == "passed"
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if not args.live:
        return 0  # Report generated successfully; inspect each service's status.
    return 0 if report.get("live_gate", {}).get("status") == "authorized_synthetic_only" and all(
        report[name]["live_passed"] for name in selected
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
