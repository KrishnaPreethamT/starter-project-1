"""Embed markdown documentation and upsert heading-sized chunks into pgvector."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from app.clients.azure_openai import AzureLLMClient
from app.config import Settings
from app.repositories.documents import DocumentChunk, DocumentRepository


def split_markdown(path: Path, root: Path) -> list[DocumentChunk]:
    text = path.read_text(encoding="utf-8")
    title = path.stem
    heading = title
    lines: list[str] = []
    chunks: list[DocumentChunk] = []
    for line in text.splitlines():
        match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if match:
            if lines:
                content = "\n".join(lines).strip()
                if content:
                    chunks.append(DocumentChunk(path.relative_to(root).as_posix(), heading, f"Document: {title}\nSection: {heading}\n{content}"))
            heading = match.group(2).strip()
            lines = [line]
        else:
            lines.append(line)
    if lines:
        content = "\n".join(lines).strip()
        if content:
            chunks.append(DocumentChunk(path.relative_to(root).as_posix(), heading, f"Document: {title}\nSection: {heading}\n{content}"))
    return chunks


def main() -> int:
    load_dotenv(ROOT / ".env")
    settings = Settings.from_environment()
    settings.validate_database()
    if not settings.azure_openai_embedding_deployment:
        raise SystemExit("Set AZURE_OPENAI_EMBEDDING_DEPLOYMENT in .env")
    docs = ROOT / "data/starter-project-2/docs"
    chunks = [chunk for path in sorted(docs.rglob("*.md")) for chunk in split_markdown(path, docs)]
    client = AzureLLMClient(settings)
    vectors = client.embed_texts([chunk.content for chunk in chunks])
    DocumentRepository(settings.database_url).upsert(chunks, vectors)
    print(f"Upserted {len(chunks)} document chunks from {len(list(docs.rglob('*.md')))} markdown files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
