"""Offline coverage of the v2 search chain, shared budgets and provenance."""

import os
import threading
import time
import unittest
from contextvars import ContextVar
from types import SimpleNamespace
from unittest.mock import Mock, patch

import rag_service
import tools
from search_runtime import run_search_tasks


def page(name, **changes):
    return {
        "url": f"https://example.org/{name}", "title": "作品 宇治桥 圣地巡礼",
        "content": "作品 宇治桥 剧情还原、交通及拍照攻略。", **changes,
    }


class RagWebFallbackTests(unittest.TestCase):
    def setUp(self):
        self.service = rag_service.RAGService.__new__(rag_service.RAGService)
        self.search = Mock(return_value={"results": []})
        self.service.tavily_client = SimpleNamespace(search=self.search)
        environment = patch.dict(os.environ, {
            "TAVILY_INCLUDE_DOMAINS": "", "TAVILY_EXCLUDE_DOMAINS": "github.com",
            "TAVILY_MAX_RETRIES": "0", "RAG_TAVILY_MAX_QUERIES": "2",
            "RAG_TAVILY_CORE_QUERIES": "1", "RAG_TAVILY_SITE_QUERIES": "1",
            "RAG_TAVILY_MIN_RESULTS": "2", "RAG_ENABLE_DIRECT_FALLBACK": "1",
            "RAG_DIRECT_SEARCH_ENGINES": "baidu,bing,ddg", "RAG_DIRECT_MAX_QUERIES": "2",
            "RAG_WEB_TIMEOUT_SECONDS": "2", "RAG_TAVILY_PHASE_TIMEOUT_SECONDS": "0.5",
        })
        environment.start()
        self.addCleanup(environment.stop)
        direct = patch.object(rag_service.scene_tools, "search_scene_pages", return_value=([], []))
        self.direct = direct.start()
        self.addCleanup(direct.stop)
        trace = patch.object(rag_service, "_trace_search_route")
        trace.start()
        self.addCleanup(trace.stop)

    def lookup(self, **kwargs):
        return self.service._search_single_landmark("宇治桥", "作品", **kwargs)

    def test_sufficient_tavily_sources_skip_site_and_direct_search(self):
        self.search.return_value = {"results": [page("one"), page("two")]}
        result = self.lookup()
        self.assertEqual(len(result["pages"]), 2)
        self.assertEqual(self.search.call_count, 1)
        self.direct.assert_not_called()
        self.assertEqual(result["routes"], ["tavily"])

    def test_missing_api_key_uses_baidu_without_requiring_legacy_backend_config(self):
        self.service.tavily_client = None
        self.direct.return_value = ([page("one"), page("two")], [])
        with patch.dict(os.environ, {"ANIME_SCENE_BACKEND": "tavily", "DIRECT_SEARCH_ENGINE": "ddg"}):
            result = self.lookup()
        self.assertEqual(result["routes"], ["baidu"])
        self.assertEqual(len(result["pages"]), 2)
        self.assertEqual(self.direct.call_args.args[2], "baidu")
        self.assertIn("TOOL_UNCONFIGURED", [failure["code"] for failure in result["failures"]])
        self.search.assert_not_called()

    def test_partial_tavily_results_are_supplemented_and_deduplicated(self):
        self.search.return_value = {"results": [page("one")]}
        self.direct.return_value = ([
            page("one", url="https://example.org/one#photo"), page("two"),
            page("bad", url="javascript:alert(1)"),
            page("irrelevant", title="技术博客", content="unrelated programming tutorial"),
        ], [])
        result = self.lookup()
        self.assertEqual([item["url"] for item in result["pages"]], ["https://example.org/one", "https://example.org/two"])
        self.assertEqual(self.search.call_count, 2)  # One core query, then one site query.
        self.assertIn("site:", self.search.call_args.kwargs["query"])
        self.assertEqual(self.direct.call_count, 1)
        self.assertEqual(self.direct.call_args.kwargs["exclude_urls"], {"https://example.org/one"})

    def test_failed_tavily_and_baidu_continue_through_bing_to_duckduckgo(self):
        self.search.side_effect = ConnectionError("Tavily offline")

        def direct(queries, terms, engine, **kwargs):
            if engine == "baidu":
                raise TimeoutError("Baidu offline")
            if engine == "bing":
                return [], [("中文", "Bing blocked")]
            return [page("one"), page("two")], []

        self.direct.side_effect = direct
        result = self.lookup()
        self.assertEqual(result["routes"], ["tavily", "baidu", "bing", "ddg"])
        self.assertEqual(len(result["pages"]), 2)
        self.assertEqual(self.search.call_count, 1)  # No site calls against a failed primary service.
        self.assertIn("TOOL_TIMEOUT", [failure["code"] for failure in result["failures"]])

    def test_supplementation_stops_after_bing_provides_enough_unique_sources(self):
        self.service.tavily_client = None
        self.direct.side_effect = lambda queries, terms, engine, **kwargs: ([page(engine)], [])
        result = self.lookup()
        self.assertEqual(result["routes"], ["baidu", "bing"])
        self.assertEqual(len(result["pages"]), 2)

    def test_disable_switch_retains_tavily_only_behavior(self):
        self.service.tavily_client = None
        with patch.dict(os.environ, {"RAG_ENABLE_DIRECT_FALLBACK": "0"}):
            result = self.lookup()
        self.assertEqual(result["pages"], [])
        self.direct.assert_not_called()

    def test_malformed_primary_items_do_not_prevent_direct_supplementation(self):
        self.search.return_value = {"results": [None, "broken item", {"title": None, "url": None}, page("one")]}
        self.direct.return_value = ([page("two")], [])
        result = self.lookup()
        self.assertEqual([item["url"] for item in result["pages"]], ["https://example.org/one", "https://example.org/two"])
        self.assertEqual(result["routes"], ["tavily", "baidu"])

    def test_direct_queries_keep_japanese_aliases_and_respect_query_limit(self):
        self.service.tavily_client = None
        self.direct.return_value = ([page("one"), page("two")], [])
        self.lookup(original_name="宇治橋", bangumi_original_name="響け！ユーフォニアム")
        queries = self.direct.call_args.args[0]
        self.assertEqual(len(queries), 2)
        self.assertEqual(queries[1][0], "日文")
        self.assertIn("宇治橋", queries[1][1])
        self.assertIn("響け！ユーフォニアム", queries[1][1])

    def test_custom_engine_order_is_used_and_duplicates_are_removed(self):
        self.service.tavily_client = None
        with patch.dict(os.environ, {"RAG_DIRECT_SEARCH_ENGINES": "bing,bing,invalid,ddg"}):
            result = self.lookup()
        self.assertEqual(result["routes"], ["bing", "ddg"])

    def test_cancelled_direct_search_does_not_start_next_engine_or_return_pages(self):
        self.service.tavily_client = None
        cancelled = threading.Event()

        def direct(*args, **kwargs):
            cancelled.set()
            return [page("one")], []

        self.direct.side_effect = direct
        result = self.lookup(should_cancel=cancelled.is_set)
        self.assertEqual(self.direct.call_count, 1)
        self.assertEqual(result["pages"], [])
        self.assertEqual(result["failures"][-1]["code"], "RUN_CANCELLED")

    def test_slow_tavily_does_not_consume_fallback_time_budget(self):
        release = threading.Event()
        self.addCleanup(release.set)
        self.search.side_effect = lambda **kwargs: (release.wait(2), {"results": []})[1]
        self.direct.return_value = ([page("one"), page("two")], [])
        started = time.monotonic()
        try:
            with patch.dict(os.environ, {"RAG_TAVILY_PHASE_TIMEOUT_SECONDS": "0.05", "RAG_WEB_TIMEOUT_SECONDS": "0.6"}):
                result = self.lookup()
            self.assertLess(time.monotonic() - started, 1)
            self.assertEqual(len(result["pages"]), 2)
            self.assertEqual(result["routes"], ["tavily", "baidu"])
            self.assertIn("TOOL_TIMEOUT", [failure["code"] for failure in result["failures"]])
        finally:
            release.set()

    def test_expired_deadline_starts_no_network_calls(self):
        result = self.lookup(deadline=time.monotonic() - 1)
        self.search.assert_not_called()
        self.direct.assert_not_called()
        self.assertEqual(result["pages"], [])
        self.assertEqual(result["failures"][-1]["code"], "TOOL_TIMEOUT")

    def test_direct_sources_follow_the_same_domain_restrictions(self):
        self.service.tavily_client = None
        self.direct.return_value = ([page("one"), page("two", url="https://notexample.org/two")], [])
        with patch.dict(os.environ, {"TAVILY_INCLUDE_DOMAINS": "example.org"}):
            result = self.lookup()
        self.assertEqual([item["url"] for item in result["pages"]], ["https://example.org/one"])

    def test_fallback_pages_keep_source_metadata_and_wait_for_approval(self):
        self.service.tavily_client = None
        self.direct.return_value = ([page("one"), page("two")], [])
        self.service.is_landmark_indexed = lambda _: False
        self.service.is_landmark_pending = lambda _: False
        self.service.add_to_pending = Mock()
        self.service.db = SimpleNamespace(add_documents=Mock())
        result = self.service.ingest_landmarks([{"id": "selected-id", "name": "宇治桥", "bangumiName": "作品"}])
        self.assertEqual(result["pending_count"], 1)
        self.assertEqual(len(result["sources"]), 2)
        self.assertTrue(all(source["review_status"] == "unreviewed" for source in result["sources"]))
        self.assertTrue(all(source["point_ids"] == ["selected-id"] for source in result["sources"]))
        self.assertTrue(all(source["retrieved_at"] for source in result["sources"]))
        staged = self.service.add_to_pending.call_args.kwargs["chunk_metadata"]
        self.assertEqual([meta["url"] for meta in staged], ["https://example.org/one", "https://example.org/two"])
        self.service.db.add_documents.assert_not_called()

    def test_batch_timeout_drops_late_results_without_staging_them(self):
        release = threading.Event()
        finished = threading.Event()
        self.service.is_landmark_indexed = lambda _: False
        self.service.is_landmark_pending = lambda _: False
        self.service.add_to_pending = Mock()

        def slow_search(*args):
            release.wait(2)
            finished.set()
            return {"text": "late content", "pages": [page("late")], "failures": []}

        self.service._search_single_landmark = slow_search
        try:
            result = self.service.ingest_landmarks(
                [{"id": "one", "name": "宇治桥", "bangumiName": "作品"}], deadline=time.monotonic() + 0.05,
            )
            self.assertEqual(result["pending_count"], 0)
            self.assertIn("TOOL_TIMEOUT", [failure["code"] for failure in result["failures"]])
        finally:
            release.set()
        self.assertTrue(finished.wait(1))
        self.service.add_to_pending.assert_not_called()


class DirectSearchRuntimeTests(unittest.TestCase):
    def test_html_search_filters_domains_and_duplicates_before_fetching_pages(self):
        results = [page("one"), page("one", url="https://example.org/one#photo"), page("denied", url="https://notexample.org/denied")]
        with patch.dict(os.environ, {"TAVILY_INCLUDE_DOMAINS": "example.org", "TAVILY_EXCLUDE_DOMAINS": ""}), \
             patch.object(tools, "_baidu_html_search", return_value=(results, [])), \
             patch.object(tools, "_fetch_page_content", return_value=("宇治桥 圣地巡礼 拍照攻略正文" * 5, None)) as fetch:
            pages, failures = tools.search_scene_pages([("中文", "宇治桥 圣地巡礼")], ["宇治桥"], "baidu")
        self.assertEqual(failures, [])
        self.assertEqual(len(pages), 1)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(pages[0]["url"], "https://example.org/one")

    def test_runtime_does_not_wait_for_cancelled_requests_or_start_queued_work(self):
        release = threading.Event()
        queued = Mock()
        deadline = time.monotonic() + 0.05
        started = time.monotonic()
        try:
            result = list(run_search_tasks([
                ("blocked", lambda: release.wait(2), ()), ("queued", queued, ()),
            ], should_stop=lambda: time.monotonic() >= deadline, max_workers=1))
            self.assertEqual(result, [])
            self.assertLess(time.monotonic() - started, 1)
            queued.assert_not_called()
        finally:
            release.set()

    def test_runtime_propagates_trace_context_to_search_workers(self):
        context = ContextVar("test-search-context", default="missing")
        token = context.set("run-known")
        try:
            result = list(run_search_tasks([("query", context.get, ())]))
        finally:
            context.reset(token)
        self.assertEqual(result, [("query", "run-known", None)])


if __name__ == "__main__":
    unittest.main()
