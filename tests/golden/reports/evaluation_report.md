# 🛡️ ChangeGuard Evaluation Report

- **Timestamp**: `2026-11-05 06:15:25 UTC`
- **CI Status**: 🟢 **PASSED**
- **Quality Gates**: 4 / 4 Passed

---

## 1. 🚦 CI Quality Gates

| Gate | Required Threshold | Actual Metric | Status | Description |
|---|:---:|:---:|:---:|---|
| `classification_accuracy` | **>= 90%** | `100.00%` | ✅ PASS | Document classification accuracy across all golden cases |
| `critical_field_extraction_accuracy` | **>= 85%** | `100.00%` | ✅ PASS | Accuracy on critical legal, financial, and identifying fields |
| `citation_coverage` | **>= 95%** | `100.00%` | ✅ PASS | Percentage of extracted facts with valid page and source snippet citation |
| `zero_unsupported_factual_claims` | **== 0** | `0 claims` | ✅ PASS | Prohibits any hallucinated or unevidenced factual claims |

---

## 2. 📊 Subsystem Evaluation Metrics

### 2.1 Document Classification Accuracy

- **Overall Accuracy**: `100.00%` (55 / 55 documents)

| Document Type | Support | Correct | Precision | Recall | F1 Score |
|---|:---:|:---:|:---:|:---:|:---:|
| `boq` | 5 | 5 | 100.00% | 100.00% | 100.00% |
| `change_order` | 10 | 10 | 100.00% | 100.00% | 100.00% |
| `contract` | 5 | 5 | 100.00% | 100.00% | 100.00% |
| `daily_report` | 10 | 10 | 100.00% | 100.00% | 100.00% |
| `email` | 10 | 10 | 100.00% | 100.00% | 100.00% |
| `rfi` | 5 | 5 | 100.00% | 100.00% | 100.00% |
| `site_photo` | 10 | 10 | 100.00% | 100.00% | 100.00% |

### 2.2 Field-Level Extraction Precision & Recall

- **Critical Field Accuracy**: `100.00%` (180 / 180 facts)
- **Overall Fact Precision**: `100.00%`
- **Overall Fact Recall**: `100.00%`
- **Overall Fact F1**: `100.00%`

| Top Extracted Fields | Expected | Correct | Precision | Recall |
|---|:---:|:---:|:---:|:---:|
| `activities` | 10 | 10 | 100.00% | 100.00% |
| `amount` | 10 | 10 | 100.00% | 100.00% |
| `body` | 10 | 10 | 100.00% | 100.00% |
| `co_number` | 10 | 10 | 100.00% | 100.00% |
| `contract_value` | 5 | 5 | 100.00% | 100.00% |
| `contractor` | 5 | 5 | 100.00% | 100.00% |
| `description` | 20 | 20 | 100.00% | 100.00% |
| `due_date` | 5 | 5 | 100.00% | 100.00% |
| `effective_date` | 5 | 5 | 100.00% | 100.00% |
| `employer` | 5 | 5 | 100.00% | 100.00% |

### 2.3 Entity-Link Accuracy

- **Link Accuracy**: `94.74%`
- **Link Precision**: `94.74%`
- **Link Recall**: `94.74%`
- **Link F1**: `94.74%`

### 2.4 Retrieval Precision & Recall at K

| Metric | Score | Details |
|---|:---:|---|
| **Precision@1** | `100.00%` | Top-1 candidate relevancy |
| **Precision@3** | `66.67%` | Top-3 candidate relevancy |
| **Precision@5** | `50.00%` | Top-5 candidate relevancy |
| **Recall@5** | `100.00%` | Fraction of golden documents captured in top-5 |
| **MRR** | `1.0000` | Mean Reciprocal Rank across queries |
| **Exact Identifier Match** | `100.00%` | Queries with exact code ranking #1 |
| **Refusal Accuracy** | `100.00%` | Correct 'insufficient_evidence' responses |

### 2.5 Citation Coverage & Groundedness

- **Citation Coverage**: `100.00%` (284 / 284 facts cited)
- **Text Groundedness Rate**: `100.00%`
- **Unsupported Factual Claims**: `0` (Zero hallucination requirement)

### 2.6 Refusal Correctness

- **Refusal Accuracy**: `100.00%` (5 / 5 missing evidence cases)

### 2.7 Duplicate Detection

- **Precision**: `100.00%`
- **Recall**: `100.00%`
- **F1 Score**: `100.00%`

### 2.8 Deterministic Risk Precision & Recall

- **Overall Risk Precision**: `100.00%`
- **Overall Risk Recall**: `100.00%`
- **Overall Risk F1 Score**: `100.00%`

| Risk Finding Type | Support | True Positives | Precision | Recall |
|---|:---:|:---:|:---:|:---:|
| `conflicting_information` | 4 | 4 | 100.00% | 100.00% |
| `cost_outlier` | 1 | 1 | 100.00% | 100.00% |
| `duplicate_change_order_claim` | 5 | 5 | 100.00% | 100.00% |
| `missing_required_evidence` | 5 | 5 | 100.00% | 100.00% |

---

## 3. 🔬 Comparative Benchmark Matrix

### 3.1 Prompt Engineering Versions

- **Recommended Variant**: `prompt_v2_structured_json`

| Prompt Version | Classify Acc | Critical Field Acc | Citation Cov | Hallucinations | P50 Latency |
|---|:---:|:---:|:---:|:---:|:---:|
| `prompt_v1_baseline` | 89.09% | 81.45% | 88.20% | 6 claims | 1150ms |
| `prompt_v2_cot` | 98.18% | 94.20% | 97.80% | 0 claims | 1820ms |
| `prompt_v2_structured_json` | 100.00% | 98.50% | 99.50% | 0 claims | 1420ms |

### 3.2 Model Architecture Comparison

- **Architecture Policy**: Use deterministic_baseline first; fall back to primary_gpt4o for ambiguous inputs.

| Model | Provider | Classify Acc | Critical Acc | Citation Cov | Latency | Cost/1k Docs |
|---|---|:---:|:---:|:---:|:---:|:---:|
| `primary_gpt4o` | openai | 100.00% | 98.50% | 99.50% | 1380ms | $12.50 |
| `fast_haiku` | anthropic | 94.55% | 91.20% | 96.20% | 620ms | $2.10 |
| `deterministic_baseline` | rule_engine | 100.00% | 95.00% | 100.00% | 15ms | $0.00 |

### 3.3 Retrieval Engine Configurations

- **Recommended Setting**: `hybrid_rrf_reranked`

| Setting | Precision@1 | Recall@5 | MRR | Exact ID Match | Latency |
|---|:---:|:---:|:---:|:---:|:---:|
| `bm25_only` | 75.00% | 68.75% | 0.7708 | 100.00% | 22ms |
| `dense_only` | 75.00% | 75.00% | 0.8125 | 50.00% | 48ms |
| `hybrid_rrf` | 100.00% | 93.75% | 1.0000 | 100.00% | 65ms |
| `hybrid_rrf_reranked` | 100.00% | 100.00% | 1.0000 | 100.00% | 135ms |

### 3.4 Document Chunking Strategies

- **Recommended Strategy**: `section_semantic`

| Strategy | Recall@5 | Clause Truncation Rate | Citation Precision | Mean Size |
|---|:---:|:---:|:---:|:---:|
| `fixed_token_512` | 81.25% | 28.50% | 89.00% | 2048c |
| `page_boundary` | 87.50% | 14.20% | 96.50% | 3120c |
| `section_semantic` | 96.88% | 1.50% | 99.20% | 1640c |

