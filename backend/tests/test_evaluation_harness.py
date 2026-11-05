"""Unit and integration tests for ChangeGuard evaluation harness."""

# ruff: noqa: E501
import json

from app.evaluation.comparison import ComparisonRunner
from app.evaluation.config import (
    MAX_UNSUPPORTED_FACTUAL_CLAIMS,
    MIN_CITATION_COVERAGE,
    MIN_CLASSIFICATION_ACCURACY,
    MIN_CRITICAL_FIELD_EXTRACTION_ACCURACY,
    EvaluationSuite,
    find_golden_dir,
)
from app.evaluation.gates import evaluate_ci_gates
from app.evaluation.harness import EvaluationHarness
from app.evaluation.run import main


def test_golden_directory_discovery():
    golden_dir = find_golden_dir()
    assert golden_dir.exists()
    assert (golden_dir / "manifest.json").exists()


def test_harness_run_all_suites():
    harness = EvaluationHarness()
    results = harness.run_suite(suite=EvaluationSuite.ALL)

    suites = results["suites"]
    assert "classification" in suites
    assert "extraction" in suites
    assert "entity_linking" in suites
    assert "retrieval" in suites
    assert "citations" in suites
    assert "refusal" in suites
    assert "duplicates" in suites
    assert "risks" in suites

    # Verify classification accuracy passes CI threshold
    assert suites["classification"]["accuracy"] >= MIN_CLASSIFICATION_ACCURACY

    # Verify critical field extraction passes CI threshold
    assert suites["extraction"]["critical_field_accuracy"] >= MIN_CRITICAL_FIELD_EXTRACTION_ACCURACY

    # Verify citation coverage passes CI threshold
    assert suites["citations"]["citation_coverage"] >= MIN_CITATION_COVERAGE

    # Verify zero unsupported claims
    assert suites["citations"]["unsupported_factual_claims"] <= MAX_UNSUPPORTED_FACTUAL_CLAIMS

    # Check gates
    gates = results["gates"]
    assert gates["passed"] is True
    assert gates["passed_gates"] == gates["total_gates"]


def test_harness_individual_suite_selection():
    harness = EvaluationHarness()

    res_cls = harness.run_suite(suite=EvaluationSuite.CLASSIFICATION, include_comparison=False)
    assert "classification" in res_cls["suites"]
    assert "extraction" not in res_cls["suites"]

    res_ext = harness.run_suite(suite=EvaluationSuite.EXTRACTION, include_comparison=False)
    assert "extraction" in res_ext["suites"]
    assert "classification" not in res_ext["suites"]

    res_ret = harness.run_suite(suite=EvaluationSuite.RETRIEVAL, include_comparison=False)
    assert "retrieval" in res_ret["suites"]


def test_comparison_runner_matrices():
    runner = ComparisonRunner()
    comparisons = runner.run_all_comparisons()

    assert "prompt_versions" in comparisons
    assert "models" in comparisons
    assert "retrieval_settings" in comparisons
    assert "chunking_strategies" in comparisons

    # Prompt versions comparison assertions
    prompts = comparisons["prompt_versions"]["variants"]
    assert "prompt_v1_baseline" in prompts
    assert "prompt_v2_cot" in prompts
    assert "prompt_v2_structured_json" in prompts
    assert prompts["prompt_v2_structured_json"]["classification_accuracy"] > prompts["prompt_v1_baseline"]["classification_accuracy"]

    # Model comparison assertions
    models = comparisons["models"]["models"]
    assert "primary_gpt4o" in models
    assert "fast_haiku" in models
    assert "deterministic_baseline" in models

    # Retrieval settings comparison assertions
    ret_settings = comparisons["retrieval_settings"]["settings"]
    assert "bm25_only" in ret_settings
    assert "dense_only" in ret_settings
    assert "hybrid_rrf" in ret_settings
    assert "hybrid_rrf_reranked" in ret_settings
    assert ret_settings["hybrid_rrf_reranked"]["recall@5"] >= ret_settings["bm25_only"]["recall@5"]

    # Chunking strategies assertions
    chunks = comparisons["chunking_strategies"]["strategies"]
    assert "fixed_token_512" in chunks
    assert "page_boundary" in chunks
    assert "section_semantic" in chunks
    assert chunks["section_semantic"]["boundary_clause_truncation_rate"] < chunks["fixed_token_512"]["boundary_clause_truncation_rate"]


def test_ci_gate_failure_triggers():
    # Simulated failing classification
    failing_results = {
        "classification": {"accuracy": 0.88},  # < 90%
        "extraction": {"critical_field_accuracy": 0.90},
        "citations": {"citation_coverage": 0.96, "unsupported_factual_claims": 0},
    }
    gate_res = evaluate_ci_gates(failing_results)
    assert gate_res["passed"] is False

    # Simulated failing critical field accuracy
    failing_results_2 = {
        "classification": {"accuracy": 0.95},
        "extraction": {"critical_field_accuracy": 0.82},  # < 85%
        "citations": {"citation_coverage": 0.96, "unsupported_factual_claims": 0},
    }
    gate_res_2 = evaluate_ci_gates(failing_results_2)
    assert gate_res_2["passed"] is False

    # Simulated failing citation coverage
    failing_results_3 = {
        "classification": {"accuracy": 0.95},
        "extraction": {"critical_field_accuracy": 0.90},
        "citations": {"citation_coverage": 0.92, "unsupported_factual_claims": 0},  # < 95%
    }
    gate_res_3 = evaluate_ci_gates(failing_results_3)
    assert gate_res_3["passed"] is False

    # Simulated unsupported claim (hallucination)
    failing_results_4 = {
        "classification": {"accuracy": 0.95},
        "extraction": {"critical_field_accuracy": 0.90},
        "citations": {"citation_coverage": 0.98, "unsupported_factual_claims": 1},  # > 0
    }
    gate_res_4 = evaluate_ci_gates(failing_results_4)
    assert gate_res_4["passed"] is False


def test_report_generation(tmp_path):
    harness = EvaluationHarness()
    results = harness.run_suite(suite=EvaluationSuite.ALL)

    json_path, md_path = harness.generate_reports(results, output_dir=tmp_path)
    assert json_path is not None and json_path.exists()
    assert md_path is not None and md_path.exists()

    # Validate JSON report format
    report_json = json.loads(json_path.read_text(encoding="utf-8"))
    assert report_json["ci_status"] == "PASSED"
    assert "gates" in report_json
    assert "suites" in report_json
    assert "comparisons" in report_json

    # Validate Markdown report content
    report_md = md_path.read_text(encoding="utf-8")
    assert "ChangeGuard Evaluation Report" in report_md
    assert "CI Quality Gates" in report_md
    assert "PASSED" in report_md


def test_cli_runner(tmp_path):
    # Test CLI invocation
    exit_code = main([
        "--suite", "all",
        "--output-dir", str(tmp_path),
        "--format", "both",
    ])
    assert exit_code == 0
    assert (tmp_path / "evaluation_report.json").exists()
    assert (tmp_path / "evaluation_report.md").exists()
