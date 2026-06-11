#!/usr/bin/env python3
"""Minimal reproduction script for https://github.com/IBM/qauvern/issues/153.

See README.md for setup instructions.
"""

import os
import sys
import warnings
from dataclasses import dataclass
from urllib.parse import quote

import requests
from qiskit import QuantumCircuit
from qiskit.transpiler import generate_preset_pass_manager
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_SUBDOMAIN = "test.cloud" if os.environ.get("STAGING") else "cloud"

IAM_URL = f"https://iam.{_SUBDOMAIN}.ibm.com/identity/token"
RC_URL = f"https://resource-controller.{_SUBDOMAIN}.ibm.com/v2/resource_instances"
IQP_UI_URL = f"https://quantum.{_SUBDOMAIN}.ibm.com"
RUNTIME_URL = f"https://{_SUBDOMAIN}.ibm.com"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InstanceConfig:
    limit: int | None
    allocation: int | None


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
    return resp.json()["access_token"]


def prompt_to_configure_ui() -> None:
    pause(
        f"In the IQP UI ({IQP_UI_URL}/instances), set the allocation to be the "
        f"'Cycle usage'. Also, check 'Set as limit'."
    )


def fetch_instance(iam_token: str, crn: str) -> InstanceConfig:
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
    config = InstanceConfig(
        limit=extensions.get("instance_limit_seconds"),
        allocation=extensions.get("usage_allocation_seconds"),
    )
    return config


def prompt_to_verify_initial_config(config: InstanceConfig) -> None:
    pause(
        f"Verify the following values match what you set in the UI:\n"
        f"  limit:      {config.limit}\n"
        f"  allocation: {config.allocation}\n"
        f"If not, fix the UI and rerun."
    )


def patch_allocation(iam_token: str, crn: str, allocation_seconds: int) -> None:
    print(f"\nPatching allocation to {allocation_seconds}s via resource controller...")
    resp = requests.patch(
        f"{RC_URL}/{quote(crn, safe='')}",
        headers={
            "Authorization": f"Bearer {iam_token}",
            "Content-Type": "application/json",
        },
        # The API broker expects usage_allocation_seconds as a string.
        json={"parameters": {"usage_allocation_seconds": str(allocation_seconds)}},
    )
    resp.raise_for_status()


def prompt_to_verify_set_as_limit_unchecked() -> None:
    pause(
        f"In the IQP UI ({IQP_UI_URL}/instances), reload the page, then confirm 'Set as limit' is now\n"
        f"unchecked. (This is a UI bug: editing allocation should not\n"
        f"clear the limit checkbox.)"
    )


def is_blocked_by_limit(api_key: str, crn: str) -> bool:
    """Submit a probe circuit and return True if the usage limit blocked it.

    The job is still accepted by the runtime; it's the SDK that emits a
    UserWarning saying "This instance has met its usage limit. Workloads will
    not run until time is made available." We catch that warning to detect
    the blocked state.
    """
    print("\nSubmitting a minimal circuit...")

    service = QiskitRuntimeService(token=api_key, instance=crn, url=RUNTIME_URL)
    backend = service.least_busy(operational=True, simulator=False)

    qc = QuantumCircuit(1)
    qc.h(0)
    qc.measure_all()

    isa_circuit = generate_preset_pass_manager(
        backend=backend, optimization_level=1
    ).run(qc)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        job = Sampler(mode=backend).run([isa_circuit])

    blocked = any("usage limit" in str(w.message) for w in caught)
    status = "blocked" if blocked else "queued"
    print(f"Job submitted ({status}). job_id={job.job_id()}")
    return blocked


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

    # --- Initial setup: configure UI, verify values, confirm jobs blocked ---
    prompt_to_configure_ui()
    initial = fetch_instance(iam_token, crn)
    if initial.allocation is None:
        sys.exit("Invalid setup: instance has no usage_allocation_seconds set.")
    prompt_to_verify_initial_config(initial)
    if not is_blocked_by_limit(api_key, crn):
        sys.exit(
            "Invalid setup: expected the first job to be blocked by the usage "
            "limit, but it was queued normally. Re-check the UI configuration."
        )


    # --- Patch allocation by +1s and verify it changed without touching limit ---
    new_allocation = initial.allocation + 1
    patch_allocation(iam_token, crn, new_allocation)
    after = fetch_instance(iam_token, crn)

    if after.allocation != new_allocation:
        sys.exit(
            f"Patch failed: expected allocation={new_allocation}, "
            f"got allocation={after.allocation}."
        )
    if after.limit != initial.limit:
        sys.exit(
            f"Unexpected limit change: was {initial.limit}, now {after.limit}. "
            f"PATCHing allocation should not modify the limit."
        )
    print("OK: allocation incremented by 1s and limit unchanged.")

    # --- Reproduce the bugs ---
    prompt_to_verify_set_as_limit_unchecked()

    if is_blocked_by_limit(api_key, crn):
        sys.exit(
            "Bug did not reproduce: job is still blocked, as we want."
        )
    print(
        "BUG REPRODUCED: job was not blocked even though the limit field is "
        "unchanged. Patching allocation incorrectly interefered with the limit."
    )

    print(f"\n\n⚠️ Consider canceling the new workloads at {IQP_UI_URL}/workloads?user=me")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        pass
