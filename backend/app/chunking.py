def split_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 200
) -> list[str]:

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        chunk = text[start:end]

        chunks.append(chunk)

        start += chunk_size - overlap

    return chunks

def split_pages(pages: list[dict]) -> list[dict]:
    chunks = []

    chunk_index = 0

    for page in pages:
        page_chunks = split_text(page["text"])

        for content in page_chunks:
            chunks.append(
                {
                    "chunk_index": chunk_index,
                    "page_number": page["page_number"],
                    "content": content,
                }
            )

            chunk_index += 1

    return chunks