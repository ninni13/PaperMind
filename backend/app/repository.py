from app.database import get_connection

def create_paper(filename: str, file_hash: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO papers (filename, file_hash)
                VALUES (%s, %s)
                RETURNING id;
                """,
                (filename, file_hash),
            )

            paper_id = cur.fetchone()[0]

        conn.commit()

    return paper_id

def create_chunks(
    paper_id: int,
    chunks: list[dict],
    embeddings: list[list[float]],
):
    rows = [
        (
            paper_id,
            chunk["chunk_index"],
            chunk["page_number"],
            chunk["content"],
            embedding,
        )
        for chunk, embedding in zip(chunks, embeddings)
    ]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO chunks (
                    paper_id,
                    chunk_index,
                    page_number,
                    content,
                    embedding
                )
                VALUES (%s, %s, %s, %s, %s);
                """,
                rows,
            )

        conn.commit()

def search_chunks(
    paper_id: int,
    query_embedding: list[float],
    limit: int = 5,
):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    chunk_index,
                    page_number,
                    content,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM chunks
                WHERE paper_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
                """,
                (
                    query_embedding,
                    paper_id,
                    query_embedding,
                    limit,
                ),
            )

            results = cur.fetchall()

    return [
        {
            "chunk_index": row[0],
            "page_number": row[1],
            "content": row[2],
            "similarity": row[3],
        }
        for row in results
    ]

def get_papers():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, filename, created_at
                FROM papers
                ORDER BY created_at DESC;
                """
            )

            rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "filename": row[1],
            "created_at": row[2],
        }
        for row in rows
    ]

def get_chunk(paper_id: int, chunk_index: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT chunk_index, page_number, content
                FROM chunks
                WHERE paper_id = %s
                  AND chunk_index = %s;
                """,
                (paper_id, chunk_index),
            )

            row = cur.fetchone()

    if row is None:
        return None

    return {
        "chunk_index": row[0],
        "page_number": row[1],
        "content": row[2],
    }

def get_paper_by_hash(file_hash: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, filename, created_at
                FROM papers
                WHERE file_hash = %s;
                """,
                (file_hash,),
            )

            row = cur.fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "filename": row[1],
        "created_at": row[2],
    }

def delete_paper(paper_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM papers
                WHERE id = %s
                RETURNING id;
                """,
                (paper_id,),
            )

            deleted = cur.fetchone()

        conn.commit()

    return deleted is not None

def get_first_chunks(paper_id: int, limit: int = 3):
    """Read the paper opening in document order, without vector search."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT chunk_index, page_number, content
                FROM chunks
                WHERE paper_id = %s
                ORDER BY chunk_index ASC
                LIMIT %s;
                """,
                (paper_id, limit),
            )
            rows = cur.fetchall()

    return [
        {
            "chunk_index": row[0],
            "page_number": row[1],
            "content": row[2],
        }
        for row in rows
    ]
