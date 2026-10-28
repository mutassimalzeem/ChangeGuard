"""Offline classifier evaluation; optionally opt in to the configured LLM."""

import argparse
import json
from collections import Counter
from pathlib import Path

from app.document_processing.classification import ClassificationInput, RuleFirstClassifier
from app.document_processing.schema import Classification

DEFAULT_DATASET = Path(__file__).resolve().parents[2] / "tests/fixtures/classification/golden.json"


def evaluate(cases, classify, *, threshold=0.8):
    if not cases:
        raise ValueError("Evaluation dataset must not be empty")
    ids = [case["id"] for case in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("Evaluation case IDs must be unique")
    matrix, totals, predicted, correct = Counter(), Counter(), Counter(), Counter()
    failures, review, llm = [], 0, 0
    for case in cases:
        expected = case["expected"]
        # Validate labels with the same schema as production output.
        Classification(
            document_type=expected, confidence=1, reasoning="gold label", model_or_rule_used="gold"
        )
        result = Classification.model_validate(
            classify(ClassificationInput.model_validate(case["input"]))
        )
        totals[expected] += 1
        predicted[result.document_type] += 1
        matrix[expected, result.document_type] += 1
        correct[expected] += result.document_type == expected
        review += result.confidence < threshold
        llm += result.model_or_rule_used.startswith("llm:")
        if result.document_type != expected:
            failures.append(
                {"id": case["id"], "expected": expected, "predicted": result.document_type}
            )
    count = len(cases)
    return {
        "documents": count,
        "correct": sum(correct.values()),
        "accuracy": sum(correct.values()) / count,
        "review_required": review,
        "confident_coverage": (count - review) / count,
        "llm_calls": llm,
        "per_type": {
            label: {
                "support": totals[label],
                "correct": correct[label],
                "recall": correct[label] / totals[label],
                "precision": correct[label] / predicted[label] if predicted[label] else 0,
            }
            for label in sorted(totals)
        },
        "confusion_matrix": {
            label: {
                prediction: matrix[label, prediction]
                for prediction in sorted(predicted)
                if matrix[label, prediction]
            }
            for label in sorted(totals)
        },
        "failures": failures,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--llm", action="store_true", help="Opt in to configured live LLM fallback")
    parser.add_argument("--min-accuracy", type=float, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not 0 <= args.min_accuracy <= 1:
        parser.error("--min-accuracy must be between zero and one")
    cases = json.loads(args.dataset.read_text(encoding="utf-8"))
    classify = RuleFirstClassifier().classify
    threshold = 0.8
    if args.llm:
        from app.core.config import get_settings
        from app.document_processing.providers import Services

        settings = get_settings()
        if settings.llm_provider != "openai" or not settings.llm_api_key:
            parser.error("--llm requires configured LLM_PROVIDER=openai and LLM_API_KEY")
        classify, threshold = Services().classify, settings.classification_review_threshold
    report = evaluate(cases, classify, threshold=threshold)
    report["mode"] = "rules_with_llm_fallback" if args.llm else "rules_only"
    output = json.dumps(report, indent=2) + "\n"
    print(output, end="")
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    return int(report["accuracy"] < args.min_accuracy)


if __name__ == "__main__":
    raise SystemExit(main())
