import unittest
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from threading import Barrier

import planning_progress as progress
from search_runtime import run_search_tasks


class PlanningProgressTests(unittest.TestCase):
    def test_updates_preserve_identity_timing_and_public_summaries(self):
        events = []

        @progress.track_stage("retrieve", "检索巡礼资料")
        def retrieve(state, config=None):
            progress.activity("retrieve", "knowledge", "查询知识库", "正在查询", "running")
            progress.activity("retrieve", "knowledge", "查询知识库", "命中 4 处，2 处需要补充")
            return {"value": 1, "_step_summary": "已整理 6 处资料"}

        with progress.reporting(events.append):
            self.assertEqual(retrieve({}), {"value": 1})
        self.assertEqual([event["sequence"] for event in events], list(range(1, len(events) + 1)))
        activity = [event for event in events if event["kind"] == "detail"]
        self.assertEqual(activity[0]["id"], activity[1]["id"])
        self.assertEqual(activity[0]["started_at"], activity[1]["started_at"])
        self.assertGreaterEqual(activity[1]["duration_ms"], 0)
        self.assertEqual(events[-1]["summary"], "已整理 6 处资料")
        self.assertEqual(events[-1]["status"], "completed")
        self.assertFalse(any(key.startswith("_") for event in events for key in event))

    def test_same_name_landmarks_have_separate_worker_activities(self):
        events = []

        def search(point_id):
            with progress.point_scope(point_id):
                progress.activity("retrieve", "baidu:同名", "百度 · 同名", "新增 1 条来源")

        @progress.track_stage("retrieve", "检索巡礼资料")
        def retrieve(state, config=None):
            list(run_search_tasks([(point, search, (point,)) for point in ("A", "B")]))
            return {}

        with progress.reporting(events.append):
            retrieve({})
        details = [event for event in events if event["kind"] == "detail"]
        self.assertEqual(len(details), 2)
        self.assertEqual(len({event["id"] for event in details}), 2)

    def test_late_worker_results_are_ignored_after_run_closes(self):
        events = []
        captured = []

        @progress.track_stage("retrieve", "检索巡礼资料")
        def retrieve(state, config=None):
            captured.append(copy_context())
            return {}

        with progress.reporting(events.append):
            retrieve({})
        count = len(events)
        captured[0].run(progress.activity, "retrieve", "late", "迟到结果", "不应发送")
        self.assertEqual(len(events), count)

    def test_parallel_runs_do_not_share_progress(self):
        barrier = Barrier(2)

        def run(name):
            events = []

            @progress.track_stage("route", "编排每日路线")
            def route(state, config=None):
                barrier.wait(timeout=2)
                progress.activity("route", "result", name, f"{name}的结果")
                return {"_step_summary": name}

            with progress.reporting(events.append):
                route({})
            return events

        with ThreadPoolExecutor(max_workers=2) as executor:
            first, second = list(executor.map(run, ["甲", "乙"]))
        self.assertEqual(first[-1]["summary"], "甲")
        self.assertEqual(second[-1]["summary"], "乙")
        self.assertNotIn("乙的结果", [event["summary"] for event in first])


if __name__ == "__main__":
    unittest.main()
