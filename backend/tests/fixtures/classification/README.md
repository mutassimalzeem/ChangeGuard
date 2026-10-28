# Classification golden documents

22 synthetic examples cover all ten types, filename/metadata/text evidence,
conflicts and unknown images. No customer data or secrets are included.
`expected` is the human label and is never sent to the classifier.

`requires_fallback_or_review` defines expected routing for unit tests. Evaluation
ignores it when scoring, so abstentions stay in the accuracy denominator.
Mocked fallback labels test control flow, not live LLM accuracy.

Run `python -m app.evaluation.classification` from `backend` for the offline report.
