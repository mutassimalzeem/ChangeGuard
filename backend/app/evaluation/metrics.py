"""Evaluation metrics calculation for ChangeGuard AI subsystems."""

from collections import Counter
from typing import Any


class EvaluationInputError(ValueError):
    """Raised when evaluation inputs are invalid or empty."""

    def __init__(
        self,
        message: str = "Predictions and targets must be non-empty and of equal length",
    ) -> None:
        super().__init__(message)


def calculate_classification_metrics(predictions: list[str], targets: list[str]) -> dict[str, Any]:
    if not targets or len(predictions) != len(targets):
        raise EvaluationInputError

    total = len(targets)
    correct = sum(p == t for p, t in zip(predictions, targets, strict=True))
    accuracy = correct / total

    classes = sorted(set(targets) | set(predictions))
    target_counts = Counter(targets)
    pred_counts = Counter(predictions)
    matrix = Counter(zip(targets, predictions, strict=True))

    per_class = {}
    for cls_name in classes:
        tp = matrix[(cls_name, cls_name)]
        fp = pred_counts[cls_name] - tp
        fn = target_counts[cls_name] - tp
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        per_class[cls_name] = {
            "support": target_counts[cls_name],
            "correct": tp,
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
        }

    confusion_matrix = {
        target: {pred: matrix[(target, pred)] for pred in classes if matrix[(target, pred)] > 0}
        for target in sorted(set(targets))
    }

    return {
        "total": total,
        "correct": correct,
        "accuracy": round(accuracy, 4),
        "per_class": per_class,
        "confusion_matrix": confusion_matrix,
    }


def calculate_extraction_metrics(
    predicted_records: list[dict[str, Any]],
    expected_records: list[dict[str, Any]],
    critical_fields_by_type: dict[str, list[str]],
) -> dict[str, Any]:
    total_expected_facts = 0
    total_predicted_facts = 0
    correct_facts = 0

    total_critical_facts = 0
    correct_critical_facts = 0

    field_stats: dict[str, Counter] = {}

    for pred_rec, exp_rec in zip(predicted_records, expected_records, strict=True):
        doc_type = exp_rec.get("document_type", "other")
        critical_names = set(critical_fields_by_type.get(doc_type, []))

        exp_fields = exp_rec.get("expected", {})
        pred_fields = pred_rec.get("predicted", {})

        for name, exp_val in exp_fields.items():
            if name in ("items", "document_references") and isinstance(exp_val, list):
                continue
            if not isinstance(exp_val, dict) or "missing" not in exp_val:
                continue

            stats = field_stats.setdefault(name, Counter())
            total_expected_facts += 1
            stats["expected"] += 1

            is_critical = name in critical_names
            if is_critical:
                total_critical_facts += 1

            pred_val = pred_fields.get(name)
            if pred_val is not None:
                total_predicted_facts += 1
                stats["predicted"] += 1

                # Compare values
                expected_missing = exp_val.get("missing", False)
                predicted_missing = pred_val.get("missing", False)

                if expected_missing == predicted_missing:
                    if expected_missing:
                        correct_facts += 1
                        stats["correct"] += 1
                        if is_critical:
                            correct_critical_facts += 1
                    else:
                        exp_v = exp_val.get("value")
                        pred_v = pred_val.get("value")
                        if exp_v == pred_v:
                            correct_facts += 1
                            stats["correct"] += 1
                            if is_critical:
                                correct_critical_facts += 1

    precision = correct_facts / total_predicted_facts if total_predicted_facts > 0 else 0.0
    recall = correct_facts / total_expected_facts if total_expected_facts > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    critical_accuracy = (
        correct_critical_facts / total_critical_facts if total_critical_facts > 0 else 1.0
    )

    by_field = {}
    for fname, c in field_stats.items():
        exp = c["expected"]
        corr = c["correct"]
        pr = c["predicted"]
        f_prec = corr / pr if pr > 0 else 0.0
        f_rec = corr / exp if exp > 0 else 0.0
        by_field[fname] = {
            "expected": exp,
            "correct": corr,
            "precision": round(f_prec, 4),
            "recall": round(f_rec, 4),
        }

    return {
        "total_expected_facts": total_expected_facts,
        "total_predicted_facts": total_predicted_facts,
        "correct_facts": correct_facts,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "critical_facts_total": total_critical_facts,
        "critical_facts_correct": correct_critical_facts,
        "critical_field_accuracy": round(critical_accuracy, 4),
        "by_field": by_field,
    }


def calculate_entity_metrics(
    predicted_links: list[list[str]], expected_links: list[list[str]]
) -> dict[str, Any]:
    total_expected = 0
    total_predicted = 0
    correct = 0

    for pred, exp in zip(predicted_links, expected_links, strict=True):
        set_exp = set(exp)
        set_pred = set(pred)
        total_expected += len(set_exp)
        total_predicted += len(set_pred)
        correct += len(set_exp & set_pred)

    precision = correct / total_predicted if total_predicted > 0 else 1.0
    recall = correct / total_expected if total_expected > 0 else 1.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "total_expected_links": total_expected,
        "total_predicted_links": total_predicted,
        "correct_links": correct,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(correct / max(total_expected, 1), 4),
    }


def calculate_retrieval_metrics(
    query_results: list[dict[str, Any]], k_values: tuple[int, ...] = (1, 3, 5)
) -> dict[str, Any]:
    metrics: dict[str, Any] = {f"precision@{k}": 0.0 for k in k_values}
    metrics.update({f"recall@{k}": 0.0 for k in k_values})
    metrics["mrr"] = 0.0
    metrics["exact_identifier_matches"] = 0
    metrics["exact_identifier_queries"] = 0
    metrics["refusal_correctness"] = 0
    metrics["refusal_queries"] = 0

    total_queries = len(query_results)
    if total_queries == 0:
        return metrics

    for item in query_results:
        retrieved_ids = item.get("retrieved_ids", [])
        expected_ids = set(item.get("expected_ids", []))
        is_exact_id_query = item.get("is_exact_id_query", False)
        is_refusal_query = item.get("is_refusal_query", False)
        returned_refusal = item.get("status") == "insufficient_evidence"

        if is_refusal_query:
            metrics["refusal_queries"] += 1
            if returned_refusal and len(retrieved_ids) == 0:
                metrics["refusal_correctness"] += 1
            continue

        if is_exact_id_query:
            metrics["exact_identifier_queries"] += 1
            if retrieved_ids and retrieved_ids[0] in expected_ids:
                metrics["exact_identifier_matches"] += 1

        # Calculate P@K, R@K
        for k in k_values:
            top_k = retrieved_ids[:k]
            hits = len(set(top_k) & expected_ids)
            prec = hits / k if k > 0 else 0.0
            rec = hits / len(expected_ids) if expected_ids else 1.0
            metrics[f"precision@{k}"] += prec
            metrics[f"recall@{k}"] += rec

        # MRR
        rr = 0.0
        for rank, rid in enumerate(retrieved_ids, start=1):
            if rid in expected_ids:
                rr = 1.0 / rank
                break
        metrics["mrr"] += rr

    search_queries = total_queries - metrics["refusal_queries"]
    if search_queries > 0:
        for k in k_values:
            metrics[f"precision@{k}"] = round(metrics[f"precision@{k}"] / search_queries, 4)
            metrics[f"recall@{k}"] = round(metrics[f"recall@{k}"] / search_queries, 4)
        metrics["mrr"] = round(metrics["mrr"] / search_queries, 4)

    if metrics["exact_identifier_queries"] > 0:
        metrics["exact_identifier_match_rate"] = round(
            metrics["exact_identifier_matches"] / metrics["exact_identifier_queries"], 4
        )
    else:
        metrics["exact_identifier_match_rate"] = 1.0

    if metrics["refusal_queries"] > 0:
        metrics["refusal_accuracy"] = round(
            metrics["refusal_correctness"] / metrics["refusal_queries"], 4
        )
    else:
        metrics["refusal_accuracy"] = 1.0

    return metrics


def calculate_citation_groundedness_metrics(
    extracted_items: list[dict[str, Any]],
) -> dict[str, Any]:
    total_facts = 0
    facts_with_citation = 0
    facts_grounded_in_text = 0
    unsupported_factual_claims = 0

    for item in extracted_items:
        source_text = item.get("source_text", "").casefold()
        facts = item.get("facts", {})

        for _name, fact in facts.items():
            if not isinstance(fact, dict) or "missing" not in fact:
                continue
            if fact.get("missing"):
                continue

            total_facts += 1
            snippet = fact.get("source_text_snippet")
            page = fact.get("source_page")
            has_citation = snippet is not None and bool(snippet.strip())
            if has_citation and (page is None or (isinstance(page, int) and page >= 1)):
                facts_with_citation += 1

            if snippet:
                snip_norm = " ".join(snippet.casefold().split())
                src_norm = " ".join(source_text.split())
                if snip_norm in src_norm:
                    facts_grounded_in_text += 1
                else:
                    unsupported_factual_claims += 1
            else:
                unsupported_factual_claims += 1

    citation_coverage = facts_with_citation / total_facts if total_facts > 0 else 1.0
    groundedness_rate = facts_grounded_in_text / total_facts if total_facts > 0 else 1.0

    return {
        "total_facts": total_facts,
        "facts_with_citation": facts_with_citation,
        "citation_coverage": round(citation_coverage, 4),
        "facts_grounded_in_text": facts_grounded_in_text,
        "groundedness_rate": round(groundedness_rate, 4),
        "unsupported_factual_claims": unsupported_factual_claims,
    }


def calculate_refusal_metrics(
    refusal_cases: list[dict[str, Any]], predictions: list[dict[str, Any]]
) -> dict[str, Any]:
    total = len(refusal_cases)
    if total == 0:
        return {"refusal_accuracy": 1.0, "total": 0}

    correct = 0
    for case, pred in zip(refusal_cases, predictions, strict=True):
        expected_refusal = (
            case.get("expected_output", {}).get("refusal_behavior", {}).get("refuse_approval", True)
        )
        predicted_refusal = pred.get("refused", False) or pred.get("status") in (
            "insufficient_evidence",
            "rejected",
        )
        if expected_refusal == predicted_refusal:
            correct += 1

    return {
        "total": total,
        "correct_refusals": correct,
        "refusal_accuracy": round(correct / total, 4),
    }


def calculate_duplicate_metrics(
    duplicate_cases: list[dict[str, Any]], predictions: list[dict[str, Any]]
) -> dict[str, Any]:
    tp = 0
    fp = 0
    fn = 0
    tn = 0

    for case, pred in zip(duplicate_cases, predictions, strict=True):
        expected_dup = case.get("expected_output", {}).get("is_duplicate", True)
        predicted_dup = pred.get("is_duplicate", False)

        if expected_dup and predicted_dup:
            tp += 1
        elif not expected_dup and predicted_dup:
            fp += 1
        elif expected_dup and not predicted_dup:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "total_cases": len(duplicate_cases),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def calculate_risk_metrics(
    risk_cases: list[dict[str, Any]], predicted_risks: list[dict[str, Any]]
) -> dict[str, Any]:
    per_type: dict[str, Counter] = {}

    for case, pred in zip(risk_cases, predicted_risks, strict=True):
        expected_type = case.get("expected_output", {}).get("risk_type", "unknown")
        predicted_type = pred.get("risk_type")

        stats = per_type.setdefault(expected_type, Counter())
        stats["expected"] += 1

        if predicted_type == expected_type:
            stats["tp"] += 1
        else:
            stats["fn"] += 1
            if predicted_type:
                pred_stats = per_type.setdefault(predicted_type, Counter())
                pred_stats["fp"] += 1

    overall_tp = sum(c["tp"] for c in per_type.values())
    overall_exp = sum(c["expected"] for c in per_type.values())
    overall_fp = sum(c["fp"] for c in per_type.values())

    precision = overall_tp / (overall_tp + overall_fp) if (overall_tp + overall_fp) > 0 else 1.0
    recall = overall_tp / overall_exp if overall_exp > 0 else 1.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    by_type = {}
    for rtype, c in per_type.items():
        tp = c["tp"]
        exp = c["expected"]
        fp = c["fp"]
        p = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        r = tp / exp if exp > 0 else 0.0
        by_type[rtype] = {
            "expected": exp,
            "true_positives": tp,
            "precision": round(p, 4),
            "recall": round(r, 4),
        }

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "by_risk_type": by_type,
    }
