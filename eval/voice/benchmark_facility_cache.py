"""Read-only component benchmark; no agent, call, database, or deployment writes."""

import argparse
import json
import os
import statistics
import time
from datetime import datetime, timezone

from veteran_access_bridge.adapters.va_facilities import read_health_facility


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--facility-id", default="vha_589A5")
    parser.add_argument("--samples", type=int, default=5)
    args = parser.parse_args()
    if not 3 <= args.samples <= 20:
        parser.error("samples must be between 3 and 20")
    observations = []
    # Interleave variants to reduce sequence bias. The first candidate is cold.
    # Each baseline call still makes a fresh API request with its own HTTP client.
    for repetition in range(args.samples):
        for variant, ttl in (("baseline", "0"), ("candidate", "60")):
            os.environ["VAB_FACILITY_METADATA_CACHE_SECONDS"] = ttl
            start = time.perf_counter()
            result = read_health_facility(args.facility_id)
            observations.append(
                {
                    "variant": variant,
                    "repetition": repetition,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 3),
                    "cache_hit": result["cache_hit"],
                    "cache_age_seconds": result["cache_age_seconds"],
                    "facility_id": result["facility_id"],
                    "time_zone": result["time_zone"],
                    "source_verified": result["source_verified"],
                }
            )
    summaries = {}
    for label, rows in (
        ("baseline", [r for r in observations if r["variant"] == "baseline"]),
        (
            "candidate_cold",
            [
                r
                for r in observations
                if r["variant"] == "candidate" and not r["cache_hit"]
            ],
        ),
        (
            "candidate_warm",
            [r for r in observations if r["variant"] == "candidate" and r["cache_hit"]],
        ),
    ):
        durations = [r["duration_ms"] for r in rows]
        summaries[label] = {
            "n": len(rows),
            "median_ms": statistics.median(durations) if durations else None,
            "max_ms": max(durations) if durations else None,
        }
    print(
        json.dumps(
            {
                "measured_at": datetime.now(timezone.utc).isoformat(),
                "scope": "isolated public VA sandbox facility metadata lookup",
                "deployment_changed": False,
                "booking_created": False,
                "limitations": (
                    "Component microbenchmark only; not end-to-end voice latency. "
                    "Small sample, no p95 claim. Warm cache benefits apply only "
                    "while the process and TTL remain valid. No patient, slot, "
                    "identity or consent caching."
                ),
                "summary": summaries,
                "observations": observations,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
