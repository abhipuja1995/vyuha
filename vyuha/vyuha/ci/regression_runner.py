"""
CI/CD regression gate runner.
Loads test cases tagged 'regression' from the API, runs them, and fails if pass rate < threshold.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

import httpx
import structlog

log = structlog.get_logger()
API_BASE = "http://localhost:8000"


async def run_regression(suite: str, fail_below: float) -> None:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=300) as client:
        # Fetch regression test cases
        resp = await client.get("/test-cases/", params={"tag": suite})
        resp.raise_for_status()
        test_cases = resp.json()

        if not test_cases:
            log.warning("no_regression_cases_found", suite=suite)
            print(f"WARNING: No test cases tagged '{suite}' found.")
            return

        log.info("regression_starting", count=len(test_cases), threshold=fail_below)

        # Trigger runs for each test case
        run_results = []
        for tc in test_cases:
            run_resp = await client.post("/runs/", json={"test_id": tc["test_id"], "k": 1})
            run_resp.raise_for_status()

        # Wait for completion (polling for Phase 1; replace with event-driven in Phase 2)
        await asyncio.sleep(30)

        summary_resp = await client.get("/reports/summary")
        summary = summary_resp.json()

        pass_rate = summary.get("pass_rate", 0.0)
        critical_failures = summary.get("critical_failures", 0)

        report = {
            "suite": suite,
            "total_runs": summary.get("total_runs"),
            "pass_rate": pass_rate,
            "critical_failures": critical_failures,
            "avg_eva_a": summary.get("avg_eva_a"),
            "avg_eva_x": summary.get("avg_eva_x"),
            "threshold": fail_below,
            "gate_passed": pass_rate >= fail_below and critical_failures == 0,
        }

        with open("regression_report.json", "w") as f:
            json.dump(report, f, indent=2)

        print(json.dumps(report, indent=2))

        if critical_failures > 0:
            print(f"\n✗ REGRESSION GATE FAILED: {critical_failures} CRITICAL failure(s) detected")
            sys.exit(1)

        if pass_rate < fail_below:
            print(f"\n✗ REGRESSION GATE FAILED: pass rate {pass_rate:.1%} < threshold {fail_below:.1%}")
            sys.exit(1)

        print(f"\n✓ Regression gate passed: {pass_rate:.1%} >= {fail_below:.1%}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="regression")
    parser.add_argument("--fail-below", type=float, default=0.97)
    args = parser.parse_args()
    asyncio.run(run_regression(args.suite, args.fail_below))


if __name__ == "__main__":
    main()
