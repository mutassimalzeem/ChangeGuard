"""Master evaluation harness orchestrator."""

from pathlib import Path
from typing import Any

from app.evaluation.comparison import ComparisonRunner
from app.evaluation.config import EvaluationSuite, find_golden_dir
from app.evaluation.evaluators import (
    CitationGroundednessEvaluator,
    ClassificationEvaluator,
    DuplicateEvaluator,
    EntityLinkEvaluator,
    ExtractionEvaluator,
    RefusalEvaluator,
    RetrievalEvaluator,
    RiskEvaluator,
)
from app.evaluation.gates import evaluate_ci_gates
from app.evaluation.reporting import generate_json_report, generate_markdown_report


class EvaluationHarness:
    def __init__(self, golden_dir: Path | None = None):
        self.golden_dir = find_golden_dir(golden_dir)
        self.classification_evaluator = ClassificationEvaluator()
        self.extraction_evaluator = ExtractionEvaluator()
        self.entity_evaluator = EntityLinkEvaluator()
        self.retrieval_evaluator = RetrievalEvaluator()
        self.citation_evaluator = CitationGroundednessEvaluator()
        self.refusal_evaluator = RefusalEvaluator()
        self.duplicate_evaluator = DuplicateEvaluator()
        self.risk_evaluator = RiskEvaluator()
        self.comparison_runner = ComparisonRunner()

    def run_suite(
        self,
        suite: EvaluationSuite | str = EvaluationSuite.ALL,
        include_comparison: bool = True,
    ) -> dict[str, Any]:
        suite_enum = EvaluationSuite(str(suite))
        results: dict[str, Any] = {}

        run_all = suite_enum == EvaluationSuite.ALL

        if run_all or suite_enum == EvaluationSuite.CLASSIFICATION:
            results["classification"] = self.classification_evaluator.evaluate(self.golden_dir)

        if run_all or suite_enum == EvaluationSuite.EXTRACTION:
            results["extraction"] = self.extraction_evaluator.evaluate(self.golden_dir)

        if run_all or suite_enum == EvaluationSuite.ENTITY_LINKING:
            results["entity_linking"] = self.entity_evaluator.evaluate(self.golden_dir)

        if run_all or suite_enum == EvaluationSuite.RETRIEVAL:
            results["retrieval"] = self.retrieval_evaluator.evaluate(self.golden_dir)

        if run_all or suite_enum in (EvaluationSuite.CITATIONS, EvaluationSuite.GROUNDEDNESS):
            results["citations"] = self.citation_evaluator.evaluate(self.golden_dir)

        if run_all or suite_enum == EvaluationSuite.REFUSAL:
            results["refusal"] = self.refusal_evaluator.evaluate(self.golden_dir)

        if run_all or suite_enum == EvaluationSuite.DUPLICATES:
            results["duplicates"] = self.duplicate_evaluator.evaluate(self.golden_dir)

        if run_all or suite_enum == EvaluationSuite.RISKS:
            results["risks"] = self.risk_evaluator.evaluate(self.golden_dir)

        comparisons = None
        if run_all or include_comparison or suite_enum == EvaluationSuite.COMPARISON:
            comparisons = self.comparison_runner.run_all_comparisons()

        # Gate evaluations
        gates = evaluate_ci_gates(results)

        return {
            "suites": results,
            "gates": gates,
            "comparisons": comparisons,
        }

    def generate_reports(
        self,
        run_data: dict[str, Any],
        output_dir: Path | None = None,
        report_format: str = "both",
    ) -> tuple[Path | None, Path | None]:
        if output_dir is None:
            output_dir = self.golden_dir / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)

        json_path = None
        md_path = None

        if report_format in ("both", "json"):
            json_path = output_dir / "evaluation_report.json"
            content = generate_json_report(
                run_data["suites"], run_data["gates"], run_data.get("comparisons")
            )
            json_path.write_text(content, encoding="utf-8")

        if report_format in ("both", "markdown"):
            md_path = output_dir / "evaluation_report.md"
            content = generate_markdown_report(
                run_data["suites"], run_data["gates"], run_data.get("comparisons")
            )
            md_path.write_text(content, encoding="utf-8")

        return json_path, md_path

