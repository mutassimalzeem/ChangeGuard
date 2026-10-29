"""Replaceable embedding/reranking adapters; only authorized text reaches a reranker."""

import math
import re
from typing import Protocol

from starlette.concurrency import run_in_threadpool

from app.document_processing.providers import Services

DIMENSIONS = 1536


class EmbeddingUnavailableError(RuntimeError):
    """The query embedding provider could not serve this search."""


class QueryEmbedder(Protocol):
    model: str

    async def embed(self, query: str) -> list[float]: ...


class Reranker(Protocol):
    async def scores(self, query: str, texts: tuple[str, ...]) -> list[float]: ...


def validate_embedding(vector):
    if len(vector) != DIMENSIONS or not all(math.isfinite(value) for value in vector):
        raise ValueError("Expected a finite 1536-dimensional query embedding")  # noqa: TRY003
    if not any(vector):
        raise ValueError("Query embedding must be nonzero")  # noqa: TRY003
    return vector


class ProcessingEmbedder:
    """Use the same configured model and dimensions as ingestion, off the event loop."""

    def __init__(self):
        self.services = Services()
        self.model = self.services.settings.embedding_model

    async def embed(self, query):
        try:
            (vector,) = await run_in_threadpool(self.services.embed, [query])
            return validate_embedding(vector)
        except Exception as exc:
            # Translate outages and malformed responses without exposing provider
            # request details, query text, credentials or internal error messages.
            raise EmbeddingUnavailableError from exc


class KeywordCoverageReranker:
    """Optional deterministic local reranker; no document data leaves the process.

    A cross-encoder can replace this adapter using the same score-only interface.
    It cannot introduce chunks that were absent from the authorized candidate set.
    """

    async def scores(self, query, texts):
        terms = set(re.findall(r"\w+", query.casefold()))
        return [
            len(terms & set(re.findall(r"\w+", text.casefold()))) / len(terms) for text in texts
        ]
