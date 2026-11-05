"""Report generators for Markdown and JSON evaluation outputs."""

# ruff: noqa: E501
import json
from datetime import UTC, datetime
from typing import Any


def generate_json_report(
    evaluation_results: dict[str, Any],
    gate_results: dict[str, Any],
    comparisons: dict[str, Any] | None = None,
) -> str:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "ci_status": "PASSED" if gate_results.get("passed") else "FAILED",
        "gates": gate_results,
        "suites": evaluation_results,
    }
    if comparisons:
        payload["comparisons"] = comparisons
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def generate_markdown_report(
    evaluation_results: dict[str, Any],
    gate_results: dict[str, Any],
    comparisons: dict[str, Any] | None = None,
) -> str:
    ci_passed = gate_results.get("passed", False)
    status_badge = "🟢 **PASSED**" if ci_passed else "🔴 **FAILED**"
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# 🛡️ ChangeGuard Evaluation Report",
        "",
        f"- **Timestamp**: `{now_str}`",
        f"- **CI Status**: {status_badge}",
        f"- **Quality Gates**: {gate_results.get('passed_gates', 0)} / {gate_results.get('total_gates', 0)} Passed",
        "",
        "---",
        "",
        "## 1. 🚦 CI Quality Gates",
        "",
        "| Gate | Required Threshold | Actual Metric | Status | Description |",
        "|---|:---:|:---:|:---:|---|",
    ]

    for g in gate_results.get("gates", []):
        icon = "✅ PASS" if g["passed"] else "❌ FAIL"
        lines.append(
            f"| `{g['name']}` | **{g['threshold']}** | `{g['actual']}` | {icon} | {g['description']} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 2. 📊 Subsystem Evaluation Metrics",
        "",
    ])

    # 1. Classification
    if "classification" in evaluation_results:
        c_res = evaluation_results["classification"]
        lines.extend([
            "### 2.1 Document Classification Accuracy",
            "",
            f"- **Overall Accuracy**: `{c_res.get('accuracy', 0.0):.2%}` ({c_res.get('correct', 0)} / {c_res.get('total', 0)} documents)",
            "",
            "| Document Type | Support | Correct | Precision | Recall | F1 Score |",
            "|---|:---:|:---:|:---:|:---:|:---:|",
        ])
        for doc_type, stats in sorted(c_res.get("per_class", {}).items()):
            lines.append(
                f"| `{doc_type}` | {stats['support']} | {stats['correct']} | "
                f"{stats['precision']:.2%} | {stats['recall']:.2%} | {stats['f1']:.2%} |"
            )
        lines.append("")

    # 2. Extraction
    if "extraction" in evaluation_results:
        e_res = evaluation_results["extraction"]
        lines.extend([
            "### 2.2 Field-Level Extraction Precision & Recall",
            "",
            f"- **Critical Field Accuracy**: `{e_res.get('critical_field_accuracy', 0.0):.2%}` "
            f"({e_res.get('critical_facts_correct', 0)} / {e_res.get('critical_facts_total', 0)} facts)",
            f"- **Overall Fact Precision**: `{e_res.get('precision', 0.0):.2%}`",
            f"- **Overall Fact Recall**: `{e_res.get('recall', 0.0):.2%}`",
            f"- **Overall Fact F1**: `{e_res.get('f1', 0.0):.2%}`",
            "",
            "| Top Extracted Fields | Expected | Correct | Precision | Recall |",
            "|---|:---:|:---:|:---:|:---:|",
        ])
        for fname, stats in sorted(e_res.get("by_field", {}).items())[:10]:
            lines.append(
                f"| `{fname}` | {stats['expected']} | {stats['correct']} | "
                f"{stats['precision']:.2%} | {stats['recall']:.2%} |"
            )
        lines.append("")

    # 3. Entity Linking
    if "entity_linking" in evaluation_results:
        ent_res = evaluation_results["entity_linking"]
        lines.extend([
            "### 2.3 Entity-Link Accuracy",
            "",
            f"- **Link Accuracy**: `{ent_res.get('accuracy', 0.0):.2%}`",
            f"- **Link Precision**: `{ent_res.get('precision', 0.0):.2%}`",
            f"- **Link Recall**: `{ent_res.get('recall', 0.0):.2%}`",
            f"- **Link F1**: `{ent_res.get('f1', 0.0):.2%}`",
            "",
        ])

    # 4. Retrieval
    if "retrieval" in evaluation_results:
        r_res = evaluation_results["retrieval"]
        lines.extend([
            "### 2.4 Retrieval Precision & Recall at K",
            "",
            "| Metric | Score | Details |",
            "|---|:---:|---|",
            f"| **Precision@1** | `{r_res.get('precision@1', 0.0):.2%}` | Top-1 candidate relevancy |",
            f"| **Precision@3** | `{r_res.get('precision@3', 0.0):.2%}` | Top-3 candidate relevancy |",
            f"| **Precision@5** | `{r_res.get('precision@5', 0.0):.2%}` | Top-5 candidate relevancy |",
            f"| **Recall@5** | `{r_res.get('recall@5', 0.0):.2%}` | Fraction of golden documents captured in top-5 |",
            f"| **MRR** | `{r_res.get('mrr', 0.0):.4f}` | Mean Reciprocal Rank across queries |",
            f"| **Exact Identifier Match** | `{r_res.get('exact_identifier_match_rate', 0.0):.2%}` | Queries with exact code ranking #1 |",
            f"| **Refusal Accuracy** | `{r_res.get('refusal_accuracy', 0.0):.2%}` | Correct 'insufficient_evidence' responses |",
            "",
        ])

    # 5. Citations & Groundedness
    if "citations" in evaluation_results:
        cit_res = evaluation_results["citations"]
        lines.extend([
            "### 2.5 Citation Coverage & Groundedness",
            "",
            f"- **Citation Coverage**: `{cit_res.get('citation_coverage', 0.0):.2%}` "
            f"({cit_res.get('facts_with_citation', 0)} / {cit_res.get('total_facts', 0)} facts cited)",
            f"- **Text Groundedness Rate**: `{cit_res.get('groundedness_rate', 0.0):.2%}`",
            f"- **Unsupported Factual Claims**: `{cit_res.get('unsupported_factual_claims', 0)}` (Zero hallucination requirement)",
            "",
        ])

    # 6. Refusal
    if "refusal" in evaluation_results:
        ref_res = evaluation_results["refusal"]
        lines.extend([
            "### 2.6 Refusal Correctness",
            "",
            f"- **Refusal Accuracy**: `{ref_res.get('refusal_accuracy', 0.0):.2%}` "
            f"({ref_res.get('correct_refusals', 0)} / {ref_res.get('total', 0)} missing evidence cases)",
            "",
        ])

    # 7. Duplicates
    if "duplicates" in evaluation_results:
        dup_res = evaluation_results["duplicates"]
        lines.extend([
            "### 2.7 Duplicate Detection",
            "",
            f"- **Precision**: `{dup_res.get('precision', 0.0):.2%}`",
            f"- **Recall**: `{dup_res.get('recall', 0.0):.2%}`",
            f"- **F1 Score**: `{dup_res.get('f1', 0.0):.2%}`",
            "",
        ])

    # 8. Risks
    if "risks" in evaluation_results:
        risk_res = evaluation_results["risks"]
        lines.extend([
            "### 2.8 Deterministic Risk Precision & Recall",
            "",
            f"- **Overall Risk Precision**: `{risk_res.get('precision', 0.0):.2%}`",
            f"- **Overall Risk Recall**: `{risk_res.get('recall', 0.0):.2%}`",
            f"- **Overall Risk F1 Score**: `{risk_res.get('f1', 0.0):.2%}`",
            "",
            "| Risk Finding Type | Support | True Positives | Precision | Recall |",
            "|---|:---:|:---:|:---:|:---:|",
        ])
        for rtype, rstats in sorted(risk_res.get("by_risk_type", {}).items()):
            lines.append(
                f"| `{rtype}` | {rstats['expected']} | {rstats['true_positives']} | "
                f"{rstats['precision']:.2%} | {rstats['recall']:.2%} |"
            )
        lines.append("")

    # Comparisons section
    if comparisons:
        lines.extend([
            "---",
            "",
            "## 3. 🔬 Comparative Benchmark Matrix",
            "",
        ])

        # Prompt versions
        if "prompt_versions" in comparisons:
            p_comp = comparisons["prompt_versions"]
            lines.extend([
                "### 3.1 Prompt Engineering Versions",
                "",
                f"- **Recommended Variant**: `{p_comp.get('best_variant')}`",
                "",
                "| Prompt Version | Classify Acc | Critical Field Acc | Citation Cov | Hallucinations | P50 Latency |",
                "|---|:---:|:---:|:---:|:---:|:---:|",
            ])
            for vname, vdata in p_comp.get("variants", {}).items():
                lines.append(
                    f"| `{vname}` | {vdata['classification_accuracy']:.2%} | "
                    f"{vdata['critical_field_accuracy']:.2%} | {vdata['citation_coverage']:.2%} | "
                    f"{vdata['unsupported_claims']} claims | {vdata['latency_p50_ms']}ms |"
                )
            lines.append("")

        # Models
        if "models" in comparisons:
            m_comp = comparisons["models"]
            lines.extend([
                "### 3.2 Model Architecture Comparison",
                "",
                f"- **Architecture Policy**: {m_comp.get('recommendation')}",
                "",
                "| Model | Provider | Classify Acc | Critical Acc | Citation Cov | Latency | Cost/1k Docs |",
                "|---|---|:---:|:---:|:---:|:---:|:---:|",
            ])
            for mname, mdata in m_comp.get("models", {}).items():
                lines.append(
                    f"| `{mname}` | {mdata['provider']} | {mdata['classification_accuracy']:.2%} | "
                    f"{mdata['critical_field_accuracy']:.2%} | {mdata['citation_coverage']:.2%} | "
                    f"{mdata['avg_latency_ms']}ms | ${mdata['estimated_cost_per_1k_docs_usd']:.2f} |"
                )
            lines.append("")

        # Retrieval settings
        if "retrieval_settings" in comparisons:
            r_comp = comparisons["retrieval_settings"]
            lines.extend([
                "### 3.3 Retrieval Engine Configurations",
                "",
                f"- **Recommended Setting**: `{r_comp.get('recommended_setting')}`",
                "",
                "| Setting | Precision@1 | Recall@5 | MRR | Exact ID Match | Latency |",
                "|---|:---:|:---:|:---:|:---:|:---:|",
            ])
            for sname, sdata in r_comp.get("settings", {}).items():
                lines.append(
                    f"| `{sname}` | {sdata['precision@1']:.2%} | {sdata['recall@5']:.2%} | "
                    f"{sdata['mrr']:.4f} | {sdata['exact_id_match_rate']:.2%} | {sdata['latency_ms']}ms |"
                )
            lines.append("")

        # Chunking strategies
        if "chunking_strategies" in comparisons:
            c_comp = comparisons["chunking_strategies"]
            lines.extend([
                "### 3.4 Document Chunking Strategies",
                "",
                f"- **Recommended Strategy**: `{c_comp.get('recommended_strategy')}`",
                "",
                "| Strategy | Recall@5 | Clause Truncation Rate | Citation Precision | Mean Size |",
                "|---|:---:|:---:|:---:|:---:|",
            ])
            for strat_name, strat_data in c_comp.get("strategies", {}).items():
                lines.append(
                    f"| `{strat_name}` | {strat_data['retrieval_recall@5']:.2%} | "
                    f"{strat_data['boundary_clause_truncation_rate']:.2%} | "
                    f"{strat_data['citation_precision']:.2%} | {strat_data['mean_chunk_size_chars']}c |"
                )
            lines.append("")

    return "\n".join(lines) + "\n"
