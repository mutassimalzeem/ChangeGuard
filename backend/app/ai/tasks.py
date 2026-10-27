"""AI Celery tasks."""

from celery import shared_task

from app.core.celery_app import celery_app


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_classification(self, document_id: str, model: str | None = None):
    """Run document classification with LLM."""
    # TODO: Implement LLM classification
    pass


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_extraction(self, document_id: str, schema: dict, model: str | None = None):
    """Run structured extraction with LLM."""
    # TODO: Implement LLM extraction
    pass


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_risk_detection(self, project_id: str, document_ids: list[str]):
    """Run risk detection analysis."""
    # TODO: Implement risk detection
    pass


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_draft_generation(self, change_order_id: str, model: str | None = None):
    """Generate draft change order narrative."""
    # TODO: Implement draft generation
    pass


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_qa_retrieval(self, question: str, project_id: str, context: dict | None = None):
    """Run Q&A with retrieval-augmented generation."""
    # TODO: Implement RAG Q&A
    pass