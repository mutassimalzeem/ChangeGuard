"""CLI entrypoint for running ChangeGuard golden evaluation suites.

Usage:
    python -m app.evaluation.run --suite all
"""

# ruff: noqa: T201, E501, E402
import argparse
import sys
from pathlib import Path

# Add backend directory to sys.path if invoked directly
REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.evaluation.config import EvaluationSuite
from app.evaluation.harness import EvaluationHarness


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run evaluation suites against ChangeGuard golden dataset."
    )
    parser.add_argument(
        "--suite",
        type=str,
        default=EvaluationSuite.ALL.value,
        choices=[s.value for s in EvaluationSuite],
        help="Evaluation suite to execute (default: all)",
    )
    parser.add_argument(
        "--golden-dir",
        type=Path,
        default=None,
        help="Path to golden evaluation dataset directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Path to output directory for Markdown and JSON reports",
    )
    parser.add_argument(
        "--format",
        type=str,
        default="both",
        choices=["both", "markdown", "json"],
        help="Report export format (default: both)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Force execution of comparison matrix across prompts, models, and retrieval settings",
    )
    parser.add_argument(
        "--ci",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enforce CI quality gates and exit with 1 on threshold failure (default: true)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print verbose evaluation details to stdout",
    )

    args = parser.parse_args(argv)

    try:
        harness = EvaluationHarness(golden_dir=args.golden_dir)
    except FileNotFoundError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    print(f"==> Running ChangeGuard Evaluation Suite: '{args.suite}'")
    print(f"==> Golden Dataset Path: {harness.golden_dir}")

    run_data = harness.run_suite(
        suite=args.suite,
        include_comparison=args.compare,
    )

    # Export reports
    json_path, md_path = harness.generate_reports(
        run_data,
        output_dir=args.output_dir,
        report_format=args.format,
    )

    if json_path:
        print(f"==> JSON Report written to: {json_path}")
    if md_path:
        print(f"==> Markdown Report written to: {md_path}")

    # Display summary
    gates = run_data["gates"]
    print("\n" + "=" * 60)
    print("🚦 CI QUALITY GATES SUMMARY")
    print("=" * 60)
    for g in gates.get("gates", []):
        status = "PASSED" if g["passed"] else "FAILED"
        print(
            f"  [{status:^6}] {g['name']:<38} Actual: {g['actual']:<10} Required: {g['threshold']}"
        )

    overall_passed = gates.get("passed", False)
    status_str = "PASSED" if overall_passed else "FAILED"
    print("=" * 60)
    print(
        f"Overall Status: {status_str} ({gates.get('passed_gates', 0)}/{gates.get('total_gates', 0)} gates passed)\n"
    )

    if args.verbose and md_path:
        print(md_path.read_text(encoding="utf-8"))

    if args.ci and not overall_passed:
        print("❌ CI Gate failure: Quality thresholds were not met.", file=sys.stderr)
        return 1

    print("✅ All evaluation suites and CI quality gates passed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
