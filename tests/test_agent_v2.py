import unittest
import time
from unittest.mock import patch

import agent_v2
from plan_schema import PlanRequest, WeatherSnapshot


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


def sample_weather(geo=None):
    return WeatherSnapshot.model_validate({
        "location": "京都", "geo": geo or [35, 135], "retrieved_at": "2026-10-26T01:00:00+00:00",
        "current_summary": "晴，20°C", "source_url": "https://wttr.in/35,135",
        "forecast": [
            {"date": "2026-10-26", "summary": "雨", "rain_chance_percent": 90},
            {"date": "2026-10-27", "summary": "晴", "rain_chance_percent": 10},
        ],
    })


class AgentV2Tests(unittest.TestCase):
    def run_mocked(self, model_fn, request=None, weather_fn=sample_weather, on_step=None):
        with patch.object(agent_v2.rag_service, "query_landmarks_context", return_value={
            "context": "", "missing_landmarks": [], "sources": [], "landmark_context": {},
        }), patch.object(agent_v2, "_model", side_effect=model_fn), \
             patch.object(agent_v2, "fetch_weather_snapshot", side_effect=weather_fn):
            return agent_v2.run_plan(request or sample_request(), "run-test", on_progress=lambda *_: None, should_cancel=lambda: False, on_step=on_step)

    def test_step_stream_includes_completed_stages_and_actual_summaries(self):
        steps = []

        def model(config, node, prompt):
            if node == "route":
                return {"days": [{"day": 1, "point_ids": ["A", "B"]}, {"day": 2, "point_ids": ["C", "D"]}]}
            if node == "content_audit":
                return {"is_valid": True, "errors": []}
            if node == "scene_preferences":
                return {"preferences": [{"point_id": ref} for ref in ("A", "B", "C", "D")]}
            return {"notes": []}

        plan, errors, _ = self.run_mocked(model, on_step=steps.append)
        self.assertEqual(errors, [])
        self.assertEqual(plan.status, "complete")
        phases = {step["stage"]: step for step in steps if step["kind"] == "phase"}
        self.assertEqual(list(phases), ["input", "retrieve", "experience", "route", "validate", "enrich"])
        self.assertTrue(all(step["status"] == "completed" for step in phases.values()))
        self.assertIn("4 处地点", phases["input"]["summary"])
        self.assertIn("2 天路线初稿", phases["route"]["summary"])
        self.assertIn("全部 4 处地点已覆盖", phases["validate"]["summary"])
        self.assertTrue(any("目的地天气" in step["title"] for step in steps))

    def test_repair_attempts_remain_distinct_under_validation_group(self):
        steps = []
        attempts = 0

        def model(config, node, prompt):
            nonlocal attempts
            if node == "route":
                attempts += 1
                ids = ["C"] if attempts == 1 else ["C", "D"]
                return {"days": [{"day": 1, "point_ids": ["A", "B"]}, {"day": 2, "point_ids": ids}]}
            if node == "content_audit":
                return {"is_valid": True, "errors": []}
            return {"preferences": [], "notes": []}

        plan, errors, _ = self.run_mocked(model, on_step=steps.append)
        self.assertEqual(errors, [])
        self.assertEqual(plan.status, "complete")
        first_check = [step for step in steps if step["id"] == "phase:validate:1"][-1]
        self.assertEqual(first_check["status"], "warning")
        self.assertIn("修复", first_check["summary"])
        repair = [step for step in steps if step["id"] == "phase:route:2"][-1]
        self.assertEqual(repair["group"], "validate")
        self.assertEqual(repair["title"], "路线重排 · 第 1 次")
        final_check = [step for step in steps if step["id"] == "phase:validate:2"][-1]
        self.assertEqual(final_check["status"], "completed")
        self.assertIn("经过 1 次修复", final_check["summary"])

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

    def test_weather_and_plot_affect_planning_and_survive_output(self):
        req = PlanRequest.model_validate({**sample_request().snapshot(), "start_date": "2026-10-26"})
        prompts = {}

        def model(config, node, prompt):
            prompts[node] = prompt
            if node == "scene_preferences":
                return {"preferences": [
                    {"point_id": "A", "preferred_time": "sunset", "scene_summary": "桥上的黄昏场景", "reason": "还原黄昏氛围", "weather_sensitivity": "outdoor"},
                    {"point_id": "B", "preferred_time": "morning", "reason": "原作清晨场景"},
                    {"point_id": "C", "weather_sensitivity": "indoor"}, {"point_id": "D"},
                ]}
            if node == "route":
                return {"days": [
                    {"day": 1, "point_ids": ["C", "D"], "planning_reason": "雨天优先已选室内点", "weather_advice": "预报有雨，注意防滑"},
                    {"day": 2, "point_ids": ["A", "B"], "planning_reason": "晴天按清晨到黄昏还原原作", "weather_advice": "室外拍照，携带饮水"},
                ]}
            if node == "content_audit":
                return {"is_valid": True, "errors": []}
            return {"notes": [{"point_id": "A", "scene_atmosphere": "黄昏的安静氛围", "pose_suggestions": "参照截图的姿态构图"}]}

        plan, errors, text = self.run_mocked(model, request=req)
        self.assertEqual(errors, [])
        self.assertEqual(plan.days[1].point_ids, ["B", "A"])
        self.assertEqual(plan.days[0].date.isoformat(), "2026-10-26")
        self.assertEqual(plan.days[1].date.isoformat(), "2026-10-27")
        self.assertEqual(plan.weather[0].point_ids, ["A", "B", "C", "D"])
        self.assertIn("雨天", plan.days[0].planning_reason)
        self.assertIn("桥上的黄昏场景", prompts["route"])
        self.assertIn('"rain_chance_percent": 90', prompts["route"])
        self.assertIn("2026-10-27", prompts["content_audit"])
        self.assertIn("原作清晨场景", prompts["enrich"])
        self.assertIn("建议到访时段：黄昏", text)
        self.assertIn("动作还原建议：参照截图的姿态构图", text)
        self.assertIn("天气建议：预报有雨", text)
        self.assertEqual(PlanRequest.model_validate(plan.request_snapshot).start_date, req.start_date)

    def test_weather_failure_is_a_warning_and_route_still_completes(self):
        def model(config, node, prompt):
            if node == "route":
                self.assertIn("出发日期为空时", prompt)
                return {"days": [{"day": 1, "point_ids": ["A", "B"]}, {"day": 2, "point_ids": ["C", "D"]}]}
            if node == "content_audit":
                return {"is_valid": True, "errors": []}
            return {"preferences": [], "notes": []}

        plan, errors, _ = self.run_mocked(model, weather_fn=lambda _: (_ for _ in ()).throw(TimeoutError("offline")))
        self.assertEqual(errors, [])
        self.assertEqual(plan.status, "complete")
        self.assertEqual(plan.weather, [])
        self.assertIn("WEATHER_UNAVAILABLE", [warning.code for warning in plan.validation.warnings])
        self.assertIn("WEATHER_DATE_UNSPECIFIED", [warning.code for warning in plan.validation.warnings])

    def test_distant_regions_get_separate_snapshots_and_uncovered_dates_warn(self):
        snapshot = sample_request().snapshot()
        snapshot["landmarks"][3]["geo"] = [35.68, 139.76]
        req = PlanRequest.model_validate({**snapshot, "start_date": "2026-11-20"})
        with patch.object(agent_v2, "fetch_weather_snapshot", side_effect=sample_weather) as weather, \
             patch.object(agent_v2, "_model", return_value={"preferences": []}):
            result = agent_v2.experience_node({"request_snapshot": req.snapshot()})
        self.assertEqual(weather.call_count, 2)
        self.assertEqual([item.point_ids for item in result["weather"]], [["A", "B", "C"], ["D"]])
        self.assertEqual([warning.code for warning in result["warnings"]].count("WEATHER_FORECAST_UNAVAILABLE"), 2)
        self.assertIn("2026-11-20", result["warnings"][0].message)

    def test_repairs_do_not_repeat_weather_or_scene_analysis(self):
        calls = []

        def model(config, node, prompt):
            calls.append(node)
            if node == "scene_preferences":
                return {"preferences": []}
            if node == "route":
                ids = ["C"] if calls.count("route") == 1 else ["C", "D"]
                return {"days": [{"day": 1, "point_ids": ["A", "B"]}, {"day": 2, "point_ids": ids}]}
            if node == "content_audit":
                return {"is_valid": True, "errors": []}
            return {"notes": []}

        plan, errors, _ = self.run_mocked(model)
        self.assertEqual(errors, [])
        self.assertEqual(plan.status, "complete")
        self.assertEqual(calls.count("route"), 2)
        self.assertEqual(calls.count("scene_preferences"), 1)

    def test_unknown_scene_preferences_never_create_new_points(self):
        with patch.object(agent_v2, "fetch_weather_snapshot", side_effect=sample_weather), \
             patch.object(agent_v2, "_model", return_value={"preferences": [{"point_id": "invented", "preferred_time": "evening"}]}):
            result = agent_v2.experience_node({"request_snapshot": sample_request().snapshot()})
        self.assertEqual([pref.point_id for pref in result["scene_preferences"]], ["A", "B", "C", "D"])
        self.assertTrue(all(pref.preferred_time == "any" for pref in result["scene_preferences"]))
        self.assertIn("SCENE_DATA_INCOMPLETE", [warning.code for warning in result["warnings"]])


if __name__ == "__main__":
    unittest.main()
