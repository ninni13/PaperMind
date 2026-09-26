from openai import OpenAI

CHAT_MODEL = "gpt-5-mini"

client = OpenAI()


def generate_answer(
    question: str,
    retrieved_chunks: list[dict],
) -> str:

    context = "\n\n".join(
        [
            (
                f"[Source: Page {chunk['page_number']}, "
                f"Chunk {chunk['chunk_index']}]\n"
                f"{chunk['content']}"
            )
            for chunk in retrieved_chunks
        ]
    )

    response = client.responses.create(
        model=CHAT_MODEL,
        instructions=(
            "You are a research paper assistant. "
            "Answer the user's question using only the provided context. "
            "Do not use outside knowledge. "
            "If the context does not contain enough information, say that "
            "the answer cannot be determined from the provided paper. "
            "Cite the relevant page numbers in your answer, "
            "for example [Page 3]. "
            "Only cite pages that directly support the claim."
        ),
        input=f"""
Context:
{context}

Question:
{question}
""",
    )

    return response.output_text