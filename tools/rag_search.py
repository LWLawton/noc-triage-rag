"""
rag_search.py
Local RAG retrieval using ChromaDB + sentence-transformers.

The first call to RAGSearch builds (or loads) the Chroma collection
from the runbooks/ directory. Subsequent calls are fast vector lookups.

No internet access. No external APIs. Fully local.
"""

import os
from pathlib import Path
from typing import Optional

from tools.audit_logger import AuditLogger


# Lazy imports — only loaded when RAG is initialized
_chroma = None
_embedder = None


class RAGSearch:
    """
    Local retrieval-augmented search over Markdown runbooks.

    Usage:
        rag = RAGSearch(runbooks_dir="runbooks/", persist_dir="chroma_db/")
        rag.build_index()
        result = rag.search("interface down port not connect", n_results=3)
    """

    COLLECTION_NAME = "noc_runbooks"

    def __init__(
        self,
        runbooks_dir: str = "runbooks/",
        persist_dir: str = "chroma_db/",
        embedding_model: str = "all-MiniLM-L6-v2",
        audit_logger: Optional[AuditLogger] = None,
    ):
        self.runbooks_dir = Path(runbooks_dir)
        self.persist_dir = Path(persist_dir)
        self.embedding_model_name = embedding_model
        self.audit = audit_logger or AuditLogger()

        self._client = None
        self._collection = None
        self._embedder = None
        self._initialized = False

    # ── Initialization ────────────────────────────────────────────────────────

    def initialize(self) -> None:
        """Load Chroma client and embedding model. Build index if needed."""
        if self._initialized:
            return

        try:
            import chromadb
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                f"RAG dependencies not installed: {e}\n"
                "Run: pip install chromadb sentence-transformers"
            ) from e

        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # Persistent Chroma client
        self._client = chromadb.PersistentClient(path=str(self.persist_dir))

        # Load or create collection
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        # Load embedding model
        self._embedder = SentenceTransformer(self.embedding_model_name)

        # Index runbooks if collection is empty
        if self._collection.count() == 0:
            self._index_runbooks()
        else:
            self.audit.info("rag_search", f"Loaded existing Chroma index ({self._collection.count()} chunks).")

        self._initialized = True

    def rebuild_index(self) -> None:
        """Force a full re-index of all runbooks."""
        if not self._initialized:
            self.initialize()
        # Delete existing collection
        self._client.delete_collection(self.COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._index_runbooks()

    def _index_runbooks(self) -> None:
        """Chunk and embed all Markdown runbooks into Chroma."""
        runbook_files = sorted(self.runbooks_dir.glob("*.md"))
        if not runbook_files:
            self.audit.info("rag_search", "No runbooks found to index.", path=str(self.runbooks_dir))
            return

        documents = []
        metadatas = []
        ids = []

        for fpath in runbook_files:
            chunks = self._chunk_markdown(fpath)
            for i, chunk in enumerate(chunks):
                doc_id = f"{fpath.stem}_{i}"
                documents.append(chunk)
                metadatas.append({
                    "source": fpath.name,
                    "runbook": fpath.stem,
                    "chunk_index": i,
                })
                ids.append(doc_id)

        if documents:
            embeddings = self._embedder.encode(documents, show_progress_bar=False).tolist()
            self._collection.add(
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids,
            )
            self.audit.info(
                "rag_search",
                f"Indexed {len(documents)} chunks from {len(runbook_files)} runbooks.",
            )

    def _chunk_markdown(self, fpath: Path, chunk_size: int = 500, overlap: int = 100) -> list[str]:
        """
        Split a Markdown file into overlapping text chunks.
        Tries to split on section headers (##) first, then falls back to
        character-level chunking.
        """
        text = fpath.read_text(encoding="utf-8")
        # Split on level-2 headings
        import re
        sections = re.split(r"\n(?=## )", text)
        chunks = []
        for section in sections:
            if len(section) <= chunk_size:
                chunks.append(section.strip())
            else:
                # Further split large sections
                for start in range(0, len(section), chunk_size - overlap):
                    chunk = section[start : start + chunk_size].strip()
                    if chunk:
                        chunks.append(chunk)
        return [c for c in chunks if len(c) > 50]  # Drop tiny fragments

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: str, n_results: int = 3) -> list[dict]:
        """
        Search the runbook index for chunks relevant to the query.
        Returns a list of dicts: {text, source, runbook, score, chunk_index}
        """
        if not self._initialized:
            self.initialize()

        query_embedding = self._embedder.encode([query], show_progress_bar=False).tolist()[0]

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, self._collection.count() or 1),
            include=["documents", "metadatas", "distances"],
        )

        output = []
        if results and results.get("documents"):
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                output.append({
                    "text": doc,
                    "source": meta.get("source", "unknown"),
                    "runbook": meta.get("runbook", "unknown"),
                    "chunk_index": meta.get("chunk_index", 0),
                    "score": round(1 - dist, 4),  # cosine similarity (higher = better)
                })

        self.audit.rag_query(
            query=query,
            results_count=len(output),
            runbook=output[0]["runbook"] if output else None,
        )

        return output

    def get_runbook_by_name(self, runbook_name: str) -> Optional[str]:
        """
        Return the full text of a named runbook (e.g. 'interface_down').
        Used for direct retrieval when ticket type is already known.
        """
        stem = runbook_name.replace(".md", "")
        fpath = self.runbooks_dir / f"{stem}.md"
        if fpath.exists():
            return fpath.read_text(encoding="utf-8")
        return None

    def format_context(self, results: list[dict], max_chars: int = 2000) -> str:
        """
        Format RAG search results into a clean context string for the LLM prompt.
        Truncates to max_chars to stay within context window.
        """
        if not results:
            return "No relevant runbook sections found."

        lines = []
        total = 0
        for r in results:
            header = f"[Runbook: {r['runbook']} | Score: {r['score']}]"
            block = f"{header}\n{r['text']}\n"
            if total + len(block) > max_chars:
                remaining = max_chars - total
                if remaining > 100:
                    lines.append(block[:remaining] + "\n...[truncated]")
                break
            lines.append(block)
            total += len(block)

        return "\n---\n".join(lines)
