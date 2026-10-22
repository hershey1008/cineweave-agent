"""Compare graph routing against the frozen baseline using identical fixture inputs.

Run from repository root: python -m evaluation.runners.compare_orchestration
PYTHONPATH must include backend (pytest.ini already configures this for tests).
"""

import argparse
import asyncio
import json
import platform
import statistics
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

from evaluation.orchestration_cases import CASES, FixtureTurn, normalized


def percentile(values, fraction):
    return sorted(values)[max(0, int(len(values) * fraction + .999) - 1)]


async def compare(repeats):
    samples = {"legacy": [], "langgraph": []}
    mismatches, details = [], []
    for case in CASES:
        # Warm compilation and imports outside measured runs.
        for mode in samples:
            with FixtureTurn(case) as fixture:
                await fixture.run(mode)
        for index in range(repeats):
            responses = {}
            # Alternate order to reduce warm-cache/order bias.
            modes = ["legacy", "langgraph"] if index % 2 == 0 else ["langgraph", "legacy"]
            for mode in modes:
                with FixtureTurn(case) as fixture:
                    started = perf_counter()
                    responses[mode] = await fixture.run(mode)
                    samples[mode].append((perf_counter() - started) * 1000)
                    assert fixture.client.parse.await_count == 1
            if normalized(responses["legacy"]) != normalized(responses["langgraph"]):
                mismatches.append({"case": case["name"], "repeat": index})
        details.append({"case": case["name"], "status": responses["langgraph"]["status"],
                        "nodes": [n["node"] for n in responses["langgraph"]["trace"]["orchestration"]["nodes"]]})
    return {"generated_at": datetime.now(timezone.utc).isoformat(),
            "scope": "deterministic orchestration fixtures; no live LLM, database or retrieval",
            "python": platform.python_version(), "langgraph": version("langgraph"),
            "cases": len(CASES), "repeats": repeats,
            "pairs": len(CASES) * repeats, "mismatches": mismatches,
            "parser_calls_per_turn": 1,
            "latency_ms": {mode: {"p50": round(statistics.median(values), 3),
                                  "p95": round(percentile(values, .95), 3)}
                           for mode, values in samples.items()},
            "routes": details,
            "limitations": ["Fixture latency measures local orchestration overhead, not application P95.",
                            "Equal outputs do not establish retrieval relevance or real LLM quality."]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--output", type=Path,
                        default=Path("evaluation/reports/generated/orchestration-comparison.json"))
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    report = asyncio.run(compare(args.repeats))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["cases", "pairs", "mismatches", "latency_ms"]}))
    raise SystemExit(bool(report["mismatches"]))


if __name__ == "__main__":
    main()
