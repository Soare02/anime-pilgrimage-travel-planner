import unittest
import time
from unittest.mock import patch

import agent_v2
from plan_schema import PlanRequest


def sample_request():
    return PlanRequest.model_validate({
        "days": 2,
        "landmarks": [
            {"id": "A", "name": "同名", "geo": [35, 135], "bangumiName": "作品甲"},
            {"id": "B", "name": "同名", "geo": [35, 135], "bangumiName": "作品乙"},
            {"id": "C", "name": "第三处", "geo": [35.01, 135.01]},
            {"id": "D", "name": "第四处", "geo": [35.02, 135.02]},
        ],
    })


class AgentV2Tests(unittest.TestCase):
    def run_mocked(self, model_fn):
        with patch.object(agent_v2.rag_service, "query_landmarks_context", return_value={
            "context": "", "missing_landmarks": [], "sources": [], "landmark_context": {},
        }), patch.object(agent_v2, "_model", side_effect=model_fn):
            return agent_v2.run_plan(sample_request(), "run-test", on_progress=lambda *_: None, should_cancel=lambda: False)

    def test_complete_plan_and_notes_share_ids(self):
        def model(node, prompt, config=None):
            if node == "route":
                return {"days": [{"day": 1, "point_ids": ["A", "B"]}, {"day": 2, "point_ids": ["C", "D"]}]}
            if node == "content_audit":
                return {"is_valid": True, "errors": []}
            return {"notes": [{"point_id": "A", "scene_description": "截图显示桥面"}]}

        # _model receives (config, node, prompt).
        plan, errors, text = self.run_mocked(lambda config, node, prompt: model(node, prompt))
        self.assertEqual(errors, [])
        self.assertEqual(plan.status, "complete")
        self.assertEqual(plan.point_notes[0].point_id, "A")
        self.assertEqual(plan.point_notes[0].scene_description, "截图显示桥面")
        self.assertIn("点位间直线距离", text)
        self.assertIn("作品甲", text)
        self.assertIn("作品乙", text)

    def test_bad_audit_json_never_completes(self):
        calls = []

        def model(config, node, prompt):
            calls.append(node)
            if node == "route":
                return {"days": [{"day": 1, "point_ids": ["A", "B"]}, {"day": 2, "point_ids": ["C", "D"]}]}
            return {}

        plan, errors, _ = self.run_mocked(model)
        self.assertEqual(plan.status, "draft")
        self.assertFalse(plan.validation.passed)
        self.assertIn("MODEL_OUTPUT_INVALID", [error.code for error in errors])
        self.assertEqual(calls.count("route"), agent_v2.MAX_REVISIONS + 1)

    def test_missing_point_after_repairs_remains_draft(self):
        def model(config, node, prompt):
            return {"days": [{"day": 1, "point_ids": ["A", "B"]}, {"day": 2, "point_ids": ["C"]}]}

        plan, errors, text = self.run_mocked(model)
        self.assertEqual(plan.status, "draft")
        self.assertEqual(plan.unassigned_point_ids, ["D"])
        self.assertIn("MISSING_LANDMARK", [error.code for error in errors])
        self.assertIn("第四处", text)

    def test_cancel_before_retrieval_stops_calls(self):
        with patch.object(agent_v2.rag_service, "query_landmarks_context") as query, patch.object(agent_v2, "_model") as model:
            plan, errors, _ = agent_v2.run_plan(sample_request(), "run-cancel", on_progress=lambda *_: None, should_cancel=lambda: True)
        self.assertIsNone(plan)
        self.assertEqual(errors[0].code, "RUN_CANCELLED")
        query.assert_not_called()
        model.assert_not_called()

    def test_sources_keep_point_ids_and_review_states(self):
        shared = "src_shared"
        with patch.object(agent_v2.rag_service, "query_landmarks_context", return_value={
            "context": "", "missing_landmarks": [{"id": "B", "name": "同名"}],
            "sources": [{"source_id": shared, "url": "https://example.org/page", "title": "资料", "review_status": "approved", "point_ids": ["A"]}],
            "landmark_context": {},
            "failures": [{"code": "EMBEDDING_CONFIG_UNVERIFIED", "message": "向量配置未核实", "landmark_id": "A"}],
        }), patch.object(agent_v2.rag_service, "ingest_landmarks", return_value={
            "search_context": "", "sources": [{"source_id": shared, "url": "https://example.org/page", "title": "资料", "review_status": "unreviewed", "point_ids": ["B"]}],
            "landmark_context": {}, "failures": [],
        }):
            result = agent_v2.retrieve_node({"request_snapshot": sample_request().snapshot()}, {
                "configurable": {"deadline": time.monotonic() + 10, "should_cancel": lambda: False, "on_progress": lambda *_: None},
            })
        self.assertEqual(len(result["sources"]), 2)
        by_status = {source["review_status"]: source for source in result["sources"]}
        self.assertEqual(by_status["approved"]["point_ids"], ["A"])
        self.assertEqual(by_status["unreviewed"]["point_ids"], ["B"])
        self.assertIn("EMBEDDING_CONFIG_UNVERIFIED", [warning.code for warning in result["warnings"]])


if __name__ == "__main__":
    unittest.main()
