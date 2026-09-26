"""Shared Ask Paper pipeline for the API and generation evaluation."""
from app.embedding import create_embedding
from app.repository import search_chunks
from app.rag import generate_answer


def answer_question(paper_id: int, question: str, *, include_context: bool = False) -> dict:
    # 1. Embed the question
    query_embedding = create_embedding(question)

    # 2. Retrieve relevant chunks
    results = search_chunks(
        paper_id=paper_id,
        query_embedding=query_embedding,
        limit=5,
    )

    # 3. Generate an answer from retrieved context
    answer = generate_answer(
        question=question,
        retrieved_chunks=results,
    )

    response = {
        "paper_id": paper_id,
        "question": question,
        "answer": answer,
        "sources": [
            {
                "chunk_index": result["chunk_index"],
                "page_number": result["page_number"],
                "similarity": result["similarity"],
            }
            for result in results
        ],
    }
    if include_context:
        response["retrieved_chunks"] = results
    return response
