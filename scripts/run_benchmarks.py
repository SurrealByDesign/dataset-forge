"""Run the Dataset Forge benchmark suite.

Usage:
    python scripts/run_benchmarks.py
    python scripts/run_benchmarks.py --manifest benchmarks/benchmark_manifest.json
    python scripts/run_benchmarks.py --output benchmarks/results/

Exit codes:
    0 -- all non-skipped expectations passed
    1 -- one or more expectations failed
    2 -- manifest not found or schema error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure src/ is on the path when run from the project root
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from dataset_forge.benchmark import (
    BenchmarkRun,
    load_manifest,
    run_benchmark,
    write_json_results,
    write_txt_results,
)


def _print_summary(run: BenchmarkRun) -> None:
    print(f"Benchmark: {run.manifest_path}")
    print(f"Timestamp: {run.timestamp}")
    print(f"Total     : {run.total}")
    print(f"Passed    : {run.passed}")
    print(f"Failed    : {run.failed}")
    print(f"Skipped   : {run.skipped}")
    print(f"Status    : {'PASS' if run.success else 'FAIL'}")
    print()
    for r in run.results:
        status = "SKIP" if r.skipped else ("PASS" if r.passed else "FAIL")
        detail = ""
        if r.skipped:
            detail = f"  ({r.skip_reason})"
        elif not r.passed:
            exp_tag = "found" if r.expectation.should_detect else "no-find"
            act_tag = "found" if r.actual_found else "no-find"
            sev_tag = ""
            if r.expectation.expected_severity and r.actual_severity:
                sev_tag = (
                    f" sev={r.actual_severity!r}"
                    f" (expected {r.expectation.expected_severity!r})"
                )
            detail = f"  [expected={exp_tag} actual={act_tag}{sev_tag}]"
        print(f"[{status}] {r.case_id} / {r.expectation.analyzer_id}{detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Dataset Forge benchmarks.")
    parser.add_argument(
        "--manifest",
        default="benchmarks/benchmark_manifest.json",
        help="Path to benchmark manifest JSON (default: benchmarks/benchmark_manifest.json)",
    )
    parser.add_argument(
        "--output",
        default="benchmarks/results",
        help="Directory for output files (default: benchmarks/results/)",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = _ROOT / manifest_path

    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    try:
        load_manifest(manifest_path)  # validate schema before running
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    output_dir = Path(args.output)
    if not output_dir.is_absolute():
        output_dir = _ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Running benchmarks from {manifest_path} ...")
    print()

    run = run_benchmark(manifest_path, project_root=_ROOT)
    _print_summary(run)

    json_out = output_dir / "benchmark_results.json"
    txt_out  = output_dir / "benchmark_results.txt"
    write_json_results(run, json_out)
    write_txt_results(run, txt_out)

    print()
    print(f"Results written to {output_dir}/")

    return 0 if run.success else 1


if __name__ == "__main__":
    sys.exit(main())
