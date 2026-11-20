"""Read-only paired KB component pilot using existing protected environment."""

import json
import os
import time

from veteran_access_bridge.services.call_knowledge import search_call_knowledge


def main():
    rows = []
    queries = [
        "How do I prepare for my primary care appointment?",
        "How do I cancel my appointment?",
        "Can I have a video appointment?",
        "Can I cancel a video appointment?",
    ]
    for repetition in range(2):
        for query in queries:
            variants = ("baseline", "candidate")
            if repetition % 2:
                variants = tuple(reversed(variants))
            for variant in variants:
                os.environ["VAB_KB_QUERY_NORMALIZATION"] = (
                    "true" if variant == "candidate" else "false"
                )
                started = time.perf_counter()
                result = search_call_knowledge(query)
                rows.append(
                    {
                        "repetition": repetition,
                        "variant": variant,
                        "query": query,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                        "status": result["status"],
                        "count": len(result["results"]),
                        "policy_authority": result["policy_authority"],
                        "review_statuses": sorted(
                            {r["review_status"] for r in result["results"]}
                        ),
                    }
                )
    print(json.dumps({"kind": "paired_lexical_retrieval_pilot", "results": rows}))


if __name__ == "__main__":
    main()
