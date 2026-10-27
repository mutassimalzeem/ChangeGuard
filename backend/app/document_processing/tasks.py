"""Document processing Celery tasks."""

from celery import shared_task

from app.core.celery_app import celery_app


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def extract_text(self, document_id: str):
    """Extract text from document (OCR, PDF parsing, etc.)."""
    # TODO: Implement text extraction
    # 1. Download from object storage
    # 2. Run OCR/text extraction based on file type
    # 3. Store extracted text
    # 4. Update document status
    pass


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def classify_document(self, document_id: str):
    """Classify document type."""
    # TODO: Implement document classification
    pass


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def extract_structured_fields(self, document_id: str):
    """Extract structured fields from document."""
    # TODO: Implement structured field extraction
    pass


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def create_embeddings(self, document_id: str):
    """Create vector embeddings for document chunks."""
    # TODO: Implement embedding creation
    pass


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def link_to_entities(self, document_id: str):
    """Link document to domain entities."""
    # TODO: Implement entity linking
    pass