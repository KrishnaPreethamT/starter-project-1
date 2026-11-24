from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentChunk:
    source: str
    heading: str
    content: str


@dataclass(frozen=True)
class RetrievedChunk:
    source: str
    heading: str
    content: str
    distance: float


class DocumentRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def upsert(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None:
        import psycopg
        from pgvector import Vector
        from pgvector.psycopg import register_vector
        if len(chunks) != len(embeddings):
            raise ValueError("Each document chunk must have one embedding")
        with psycopg.connect(self.database_url, connect_timeout=5) as connection:
            register_vector(connection)
            with connection.cursor() as cursor:
                cursor.executemany(
                    """INSERT INTO documents (source, heading, content, embedding) VALUES (%s, %s, %s, %s)
                       ON CONFLICT (source, heading) DO UPDATE SET content=EXCLUDED.content, embedding=EXCLUDED.embedding""",
                    [(c.source, c.heading, c.content, Vector(e)) for c, e in zip(chunks, embeddings)],
                )

    def search(self, embedding: list[float], limit: int = 5) -> list[RetrievedChunk]:
        import psycopg
        from pgvector import Vector
        from pgvector.psycopg import register_vector
        query_vector = Vector(embedding)
        with psycopg.connect(self.database_url, connect_timeout=5) as connection:
            register_vector(connection)
            rows = connection.execute(
                "SELECT source, heading, content, embedding <=> %s AS distance FROM documents ORDER BY embedding <=> %s LIMIT %s",
                (query_vector, query_vector, limit),
            ).fetchall()
        return [RetrievedChunk(*row) for row in rows]
