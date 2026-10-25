"""Offline checks for RAG fallback, provenance, and bounded tool failures."""

import unittest
import os
import threading
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.documents import Document

import rag_service
import tools
import agent_trace


class FakeReranker:
    def rerank_with_scores(self, query, documents):
        return [(index, -1.0, doc) for index, doc in enumerate(documents)]


class RecallDB:
    def __init__(self, documents, vector_error=None):
        self.documents = documents
        self.vector_error = vector_error
        self.vector_calls = 0

    def get(self, where=None, include=None):
        point_id = where["landmark_id"]
        docs = [doc for doc in self.documents if doc.metadata.get("landmark_id") == point_id]
        return {
            "documents": [doc.page_content for doc in docs],
            "metadatas": [doc.metadata for doc in docs],
        }

    def similarity_search(self, query, k=4):
        self.vector_calls += 1
        if self.vector_error:
            raise self.vector_error
        return self.documents


class RagReliabilityTests(unittest.TestCase):
    def make_service(self, db, vector_enabled=True):
        service = rag_service.RAGService.__new__(rag_service.RAGService)
        service.db = db
        service.vector_enabled = vector_enabled
        service.reranker = FakeReranker()
        return service

    def test_id_hits_survive_vector_timeout_and_keep_source(self):
        doc = Document(
            page_content="宇治桥 动漫巡礼场景说明",
            metadata={
                "landmark_id": "point-a", "landmark_name": "宇治桥",
                "chunk_id": 0, "source_id": "src_known",
                "url": "https://example.org/uji", "title": "巡礼页",
                "retrieved_at": "2026-09-26T00:00:00+00:00",
                "review_status": "approved",
            },
        )
        db = RecallDB([doc], vector_error=TimeoutError("embedding offline"))
        service = self.make_service(db)
        with patch.object(rag_service, "log_rag_event"):
            result = service.query_landmarks_context([{"id": "point-a", "name": "宇治桥"}])
        self.assertEqual(result["missing_landmarks"], [])
        self.assertEqual(result["hit_landmarks"][0]["id"], "point-a")
        self.assertEqual(result["sources"][0]["source_id"], "src_known")
        self.assertEqual(result["sources"][0]["point_ids"], ["point-a"])
        self.assertEqual(result["landmark_context"]["point-a"]["source_ids"], ["src_known"])
        self.assertEqual(result["failures"][0]["code"], "TOOL_TIMEOUT")

    def test_unverified_collection_skips_vector_and_keeps_id_hits(self):
        doc = Document(page_content="宇治桥资料", metadata={"landmark_id": "one", "chunk_id": 0})
        db = RecallDB([doc])
        service = self.make_service(db, vector_enabled=False)
        with patch.object(rag_service, "log_rag_event"):
            result = service.query_landmarks_context([{"id": "one", "name": "宇治桥"}])
        self.assertEqual(db.vector_calls, 0)
        self.assertEqual(result["hit_landmarks"][0]["id"], "one")
        self.assertEqual(result["sources"][0]["review_status"], "missing")
        self.assertEqual(result["sources"][0]["url"], "")

    def test_same_name_other_point_id_is_not_reused(self):
        own = Document(page_content="同名地点 A", metadata={"landmark_id": "a", "chunk_id": 0})
        other = Document(page_content="同名地点 B", metadata={"landmark_id": "b", "chunk_id": 0})
        service = self.make_service(RecallDB([own, other]))
        with patch.object(rag_service, "log_rag_event"):
            result = service.query_landmarks_context([{"id": "a", "name": "同名地点"}])
        texts = [chunk["text"] for chunk in result["landmark_context"]["a"]["chunks"]]
        self.assertEqual(texts, ["同名地点 A"])

    def test_ingest_splits_each_page_with_its_own_source(self):
        service = self.make_service(RecallDB([]))
        service.is_landmark_indexed = lambda point_id: False
        service.is_landmark_pending = lambda point_id: False
        service._search_single_landmark = lambda *args: {
            "text": "search context", "failures": [],
            "pages": [
                {"url": "https://example.org/one", "title": "Page one", "content": "one page content", "retrieved_at": "2026-09-26T00:00:00+00:00"},
                {"url": "https://example.org/two", "title": "Page two", "content": "two page content", "retrieved_at": "2026-09-26T00:00:01+00:00"},
            ],
        }
        staged = []
        service.add_to_pending = lambda *args, **kwargs: staged.append((args, kwargs))
        result = service.ingest_landmarks([{"id": "one", "name": "宇治桥", "bangumiName": "作品"}])
        self.assertEqual(result["pending_count"], 1)
        self.assertEqual(len(result["sources"]), 2)
        chunks = staged[0][0][4]
        metadata = staged[0][1]["chunk_metadata"]
        self.assertEqual(chunks, ["one page content", "two page content"])
        self.assertEqual([item["url"] for item in metadata], ["https://example.org/one", "https://example.org/two"])
        self.assertTrue(all(item["review_status"] == "unreviewed" for item in result["sources"]))

    def test_cancelled_ingest_does_not_write_pending(self):
        service = self.make_service(RecallDB([]))
        service.is_landmark_indexed = lambda point_id: False
        service.is_landmark_pending = lambda point_id: False
        cancelled = threading.Event()

        def search(*args):
            cancelled.set()
            return {
                "text": "search result", "failures": [],
                "pages": [{"url": "https://example.org/one", "title": "One", "content": "page content"}],
            }

        service._search_single_landmark = search
        service.add_to_pending = lambda *args, **kwargs: self.fail("cancelled ingest must not stage chunks")
        result = service.ingest_landmarks(
            [{"id": "one", "name": "宇治桥", "bangumiName": "作品"}],
            should_cancel=cancelled.is_set,
        )
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["pending_count"], 0)

    def test_cancelled_search_does_not_start_site_fallback(self):
        service = self.make_service(RecallDB([]))
        cancelled = threading.Event()
        calls = []

        def search(**kwargs):
            calls.append(kwargs["query"])
            cancelled.set()
            return {"results": []}

        service.tavily_client = SimpleNamespace(search=search)
        with patch.dict(os.environ, {"RAG_TAVILY_CORE_QUERIES": "1", "RAG_TAVILY_SITE_QUERIES": "2"}):
            result = service._search_single_landmark("宇治桥", "作品", should_cancel=cancelled.is_set)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["failures"][-1]["code"], "RUN_CANCELLED")

    def test_approval_preserves_per_chunk_metadata(self):
        service = self.make_service(RecallDB([]))
        saved = []
        service.db.add_documents = lambda docs: saved.extend(docs)
        service._read_pending = lambda: [{
            "id": "pending-one", "landmark_id": "one", "landmark_name": "宇治桥",
            "bangumi": "作品", "chunks": ["chunk one", "chunk two"],
            "chunk_metadata": [
                {"source_id": "src_one", "url": "https://example.org/one", "title": "One", "retrieved_at": "t1"},
                {"source_id": "src_two", "url": "https://example.org/two", "title": "Two", "retrieved_at": "t2"},
            ],
        }]
        service._write_pending = lambda pending: None
        with patch.object(rag_service, "log_rag_event"):
            self.assertTrue(service.approve_pending("pending-one"))
        self.assertEqual([doc.metadata["source_id"] for doc in saved], ["src_one", "src_two"])
        self.assertEqual([doc.metadata["review_status"] for doc in saved], ["approved", "approved"])

    def test_unverified_binding_prevents_new_vector_write(self):
        service = self.make_service(RecallDB([]), vector_enabled=False)
        service._read_pending = lambda: [{
            "id": "pending-one", "landmark_id": "one", "landmark_name": "宇治桥",
            "chunks": ["text"],
        }]
        writes = []
        service._write_pending = lambda pending: writes.append(pending)
        service.db.add_documents = lambda docs: self.fail("unverified collection must not be written")
        self.assertFalse(service.approve_pending("pending-one"))
        self.assertEqual(writes, [])

    def test_binding_compares_model_even_when_dimension_matches(self):
        service = self.make_service(RecallDB([]))
        service.embedding_config = {
            "embedding_config_version": "1", "embedding_model": "model-b",
            "embedding_base_url": "http://localhost:1234/v1", "embedding_dimension": 1024,
        }
        service.db._collection = SimpleNamespace(metadata={**service.embedding_config, "embedding_model": "model-a"})
        self.assertFalse(service._embedding_binding_verified())

    def test_embedding_api_error_does_not_switch_models(self):
        embedding = rag_service.FallbackEmbeddings(dimension=3)
        embedding.client = SimpleNamespace(embeddings=SimpleNamespace(create=lambda **kwargs: (_ for _ in ()).throw(TimeoutError("offline"))))
        with self.assertRaises(TimeoutError):
            embedding.embed_query("宇治桥")

    def test_weather_timeout_has_stable_code(self):
        with patch.object(tools.requests, "get", side_effect=tools.requests.exceptions.Timeout("slow")):
            with patch.object(tools, "_record_tool_failure", return_value="TOOL_TIMEOUT"):
                value = tools.get_weather.invoke({"city": "京都"})
        self.assertIn("[TOOL_TIMEOUT]", value)

    def test_trace_uses_caller_run_id_and_records_terminal_stage(self):
        persisted = []
        with patch.object(agent_trace, "_persist_run", side_effect=lambda run: persisted.append(run)):
            run_id = agent_trace.start_run(2, ["宇治桥"], run_id="run_reliability_test")
            agent_trace.end_run_by_id(run_id, status="error", error="TOOL_TIMEOUT")
        self.assertEqual(run_id, "run_reliability_test")
        self.assertEqual(persisted[-1]["status"], "error")
        self.assertEqual(persisted[-1]["steps"][-1]["type"], "run_finished")


if __name__ == "__main__":
    unittest.main()
