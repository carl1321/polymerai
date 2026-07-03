"""Minimal RAG stub for retriever tool (Document, Resource, Retriever, build_retriever)."""

from typing import Any


class Document:
    """Minimal document for retriever results."""

    def __init__(self, content: str = "", metadata: dict | None = None):
        self.content = content
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {"content": self.content, "metadata": self.metadata}


class Resource:
    """Minimal resource placeholder for rag:// URIs."""

    pass


class Retriever:
    """Stub retriever; query_relevant_documents returns empty list by default."""

    def query_relevant_documents(self, keywords: str, resources: list[Resource]) -> list[Document]:
        return []


def build_retriever() -> Retriever:
    """Return a stub Retriever instance."""
    return Retriever()
