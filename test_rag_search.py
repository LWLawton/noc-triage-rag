"""
tests/test_rag_search.py
Unit tests for RAGSearch — uses a temporary Chroma DB.
Skips gracefully if chromadb/sentence-transformers are not installed.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


# Skip entire module if RAG dependencies are not installed
pytest.importorskip("chromadb", reason="chromadb not installed — skipping RAG tests")
pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed — skipping RAG tests")


from tools.rag_search import RAGSearch
from tools.audit_logger import AuditLogger


@pytest.fixture
def rag(tmp_path):
    """Create a RAGSearch instance with a fresh temporary Chroma DB."""
    audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"), ticket_id="RAGTEST")
    rag = RAGSearch(
        runbooks_dir="runbooks/",
        persist_dir=str(tmp_path / "chroma_db"),
        embedding_model="all-MiniLM-L6-v2",
        audit_logger=audit,
    )
    rag.initialize()
    return rag


class TestRAGIndexing:
    def test_index_builds_successfully(self, rag):
        count = rag._collection.count()
        assert count > 0, "Expected runbook chunks to be indexed"

    def test_rebuild_index(self, rag):
        original_count = rag._collection.count()
        rag.rebuild_index()
        new_count = rag._collection.count()
        assert new_count == original_count


class TestRAGSearch:
    def test_interface_down_query_returns_results(self, rag):
        results = rag.search("interface down notconnect port link", n_results=3)
        assert len(results) > 0

    def test_top_result_has_required_fields(self, rag):
        results = rag.search("interface down", n_results=1)
        assert len(results) == 1
        r = results[0]
        assert "text" in r
        assert "source" in r
        assert "runbook" in r
        assert "score" in r
        assert 0.0 <= r["score"] <= 1.0

    def test_interface_down_top_match(self, rag):
        results = rag.search("port down notconnect cable unplugged switch access", n_results=3)
        runbooks = [r["runbook"] for r in results]
        assert "interface_down" in runbooks, (
            f"Expected 'interface_down' in top results, got: {runbooks}"
        )

    def test_bgp_query_matches_bgp_runbook(self, rag):
        results = rag.search("BGP neighbor session down peer", n_results=3)
        runbooks = [r["runbook"] for r in results]
        assert "bgp_neighbor_down" in runbooks

    def test_high_cpu_query_matches_cpu_runbook(self, rag):
        results = rag.search("high CPU utilization process sorted", n_results=3)
        runbooks = [r["runbook"] for r in results]
        assert "high_cpu" in runbooks

    def test_search_returns_no_more_than_requested(self, rag):
        results = rag.search("any query", n_results=2)
        assert len(results) <= 2


class TestDirectRunbookRetrieval:
    def test_get_runbook_by_name_found(self, rag):
        content = rag.get_runbook_by_name("interface_down")
        assert content is not None
        assert "Interface Down" in content

    def test_get_runbook_by_name_with_extension(self, rag):
        content = rag.get_runbook_by_name("interface_down.md")
        assert content is not None

    def test_get_runbook_by_name_not_found(self, rag):
        content = rag.get_runbook_by_name("nonexistent_runbook")
        assert content is None


class TestFormatContext:
    def test_format_context_returns_string(self, rag):
        results = rag.search("interface down", n_results=2)
        context = rag.format_context(results)
        assert isinstance(context, str)
        assert len(context) > 0

    def test_format_context_respects_max_chars(self, rag):
        results = rag.search("interface down", n_results=3)
        context = rag.format_context(results, max_chars=500)
        assert len(context) <= 600  # Small buffer for truncation message

    def test_format_context_empty_results(self, rag):
        context = rag.format_context([])
        assert "No relevant" in context
