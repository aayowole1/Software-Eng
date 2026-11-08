"""Score recorded human observations; never generate participant observations."""
import argparse
import json
import math
from pathlib import Path


def score(data):
    required = ("source_revision", "environment", "event_title")
    if data.get("protocol") != "SCRUM-83-member-login-rsvp-v1" or any(
        not isinstance(data.get(key), str) or not data[key].strip() for key in required
    ):
        return {"status": "INCOMPLETE", "reason": "Record the protocol, source revision, environment and event title first."}
    observations = data.get("observations", [])
    if not isinstance(observations, list) or len(observations) != 5:
        return {"status": "INCOMPLETE", "reason": "Exactly five participant records are required."}
    ids = [row.get("participant_id") for row in observations if isinstance(row, dict)]
    if len(ids) != 5 or any(not isinstance(value, str) or not value.strip() for value in ids) or len(set(ids)) != 5:
        return {"status": "INCOMPLETE", "reason": "Five distinct anonymous participant IDs are required."}
    valid = []
    passed = []
    for row in observations:
        elapsed = row.get("elapsed_seconds")
        is_valid = (
            row.get("human_confirmed") is True and row.get("observed") is True
            and type(row.get("completed")) is bool and type(row.get("assisted")) is bool
            and type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed > 0
        )
        if is_valid:
            valid.append(row["participant_id"])
            if row["completed"] and not row["assisted"] and elapsed <= 180:
                passed.append(row["participant_id"])
    return {
        "status": "INCOMPLETE" if len(valid) < 5 else "PASS" if len(passed) >= 4 else "FAIL",
        "recorded_human_observations": len(valid), "remaining_observations": 5 - len(valid),
        "unaided_within_180_seconds": len(passed), "required_successes": 4,
        "successful_participant_ids": passed,
        "qualification": "Scores supplied records only; does not independently establish human participation.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    result = score(json.loads(args.results.read_text(encoding="utf-8")))
    print(json.dumps(result, indent=2))
    return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
