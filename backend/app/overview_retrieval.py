"""Select overview evidence; does not generate or persist an overview."""
from app.embedding import create_embeddings
from app.repository import get_first_chunks, search_chunks

OVERVIEW_QUERIES = (
    "main method and proposed approach",
    "datasets and experimental setup",
    "main results and performance",
    "limitations and future work",
)


def get_overview_context(
    paper_id: int,
    front_limit: int = 3,
    query_limit: int = 3,
) -> list[dict]:
    """Combine the opening with four semantic searches scoped to this paper.

    Defaults select at most 15 unique chunks (3 opening + 4 queries x 3).
    Results are deduplicated by chunk_index and returned in document order.
    Similarity is omitted because each search scores against a different query.
    """
    if front_limit < 1 or query_limit < 1:
        raise ValueError("Overview retrieval limits must be positive")

    chunks = get_first_chunks(paper_id, limit=front_limit)
    if not chunks:
        return []

    # Reuse the existing batch helper: four query vectors, one API request.
    embeddings = create_embeddings(list(OVERVIEW_QUERIES))
    if len(embeddings) != len(OVERVIEW_QUERIES):
        raise ValueError("Expected one embedding for each overview query")
    for embedding in embeddings:
        chunks.extend(search_chunks(paper_id, embedding, limit=query_limit))

    unique = {}
    for chunk in chunks:
        unique.setdefault(chunk["chunk_index"], {
            "chunk_index": chunk["chunk_index"],
            "page_number": chunk["page_number"],
            "content": chunk["content"],
        })
    return [unique[index] for index in sorted(unique)]
