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

IQP_UI_URL = f"https://quantum.{_SUBDOMAIN}.ibm.com"
RUNTIME_URL = f"https://{_SUBDOMAIN}.ibm.com"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def require_env(name: str, hint: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"{name} not set. {hint}")
    return value


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

    is_blocked_by_limit(api_key, crn)

    print(f"\n\n⚠️ Consider canceling the new workload at {IQP_UI_URL}/workloads?user=me")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        pass
