#!/usr/bin/env python3
"""Minimal reproduction script for limit-impacted-by-allocation bug.

See README.md for setup instructions.
"""

import json
import os
import sys
from urllib.parse import quote

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

IAM_URL = "https://iam.test.cloud.ibm.com/identity/token"
RC_URL = "https://resource-controller.test.cloud.ibm.com/v2/resource_instances"
IQP_UI_URL = "https://quantum.test.cloud.ibm.com"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def require_env(name: str, hint: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"{name} not set. {hint}")
    return value


def pause(message: str) -> None:
    """Block until the human confirms they've done the manual step."""
    lines = message.splitlines() or [""]
    prefixed = "\n".join(f">>> {line}" for line in lines)
    input(f"\n{prefixed}\n>>>\n>>> Press Enter to continue... ")


# ---------------------------------------------------------------------------
# Step 1: Exchange API key for IAM bearer token
# ---------------------------------------------------------------------------


def get_iam_token(api_key: str) -> str:
    print("Exchanging API key for IAM bearer token...")
    resp = requests.post(
        IAM_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": api_key,
        },
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    print(f"Got IAM token (length {len(token)}).")
    return token


# ---------------------------------------------------------------------------
# Step 2: Configure allocation > cycle usage by 5s, with "Set as limit" checked
# ---------------------------------------------------------------------------


def configure_allocation_in_ui() -> None:
    pause(
        f"In the IQP UI ({IQP_UI_URL}/instances), set the allocation to be > the "
        f"'Cycle usage' by 5 seconds (e.g., if usage is 20s, set to 25s).\n\n"
        f"Also check 'Set as limit'."
    )


# ---------------------------------------------------------------------------
# Step 3: Verify resource controller reflects the configured allocation/limit
# ---------------------------------------------------------------------------


def fetch_instance_limits(iam_token: str, crn: str) -> dict:
    print("\nFetching instance from resource controller...")
    resp = requests.get(
        f"{RC_URL}/{quote(crn, safe='')}",
        headers={
            "Authorization": f"Bearer {iam_token}",
            "Content-Type": "application/json",
        },
    )
    resp.raise_for_status()
    extensions = resp.json().get("extensions", {})
    summary = {
        "instance_limit_seconds": extensions.get("instance_limit_seconds"),
        "usage_allocation_seconds": extensions.get("usage_allocation_seconds"),
    }
    print(json.dumps(summary, indent=2))
    return summary


# ---------------------------------------------------------------------------
# Step 4: Verify that new jobs are rejected
# ---------------------------------------------------------------------------


def verify_jobs_rejected(iam_token: str, crn: str) -> None:
    # TODO: submit a job via Qiskit SDK and confirm it gets rejected.
    print("\nTODO: submit a job via Qiskit SDK and verify it is rejected.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    api_key = require_env(
        "API_KEY", f"Generate one at {IQP_UI_URL} and export API_KEY=..."
    )
    crn = require_env(
        "CRN", f"Pick an instance at {IQP_UI_URL}/instances and export CRN=..."
    )

    iam_token = get_iam_token(api_key)
    configure_allocation_in_ui()
    fetch_instance_limits(iam_token, crn)
    verify_jobs_rejected(iam_token, crn)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        pass
