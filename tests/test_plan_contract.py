import math
import unittest

from pydantic import ValidationError

from plan_geometry import straight_line_distance_m
from plan_schema import Plan, PlanRequest, ScenePreference
from plan_validation import normalize_candidate, validate_plan


def request(days=2, landmarks=None):
    return PlanRequest.model_validate({
        "days": days,
        "landmarks": landmarks or [
            {"id": "A", "name": "同名", "geo": [35.0, 135.0], "bangumiName": "作品甲", "image": "https://example.com/a.jpg"},
            {"id": "B", "name": "同名", "geo": [35.0, 135.0], "bangumiName": "作品乙", "image": "https://example.com/b.jpg"},
            {"id": "C", "name": "第三处", "geo": [35.01, 135.01]},
            {"id": "D", "name": "第四处", "geo": [35.02, 135.02]},
        ],
    })


class PlanContractTests(unittest.TestCase):
    def test_optional_scene_times_from_anitabi_do_not_reject_valid_locations(self):
        cases = [
            (None, None), ("", None), ("  ", None), (0, 0), ("4758", 4758),
            ("18：41", 1121), (" 13:56 ", 836), ("01:00:29", 3629),
            ("5分40秒", 340), ("1时31分36秒", 5496), ("62min13s", 3733),
            ("18分", 1080), ("1分07", 67), ("P14", None), ("封面", None),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                req = request(days=1, landmarks=[{"id": "A", "name": "测试点", "geo": [35, 135], "s": raw}])
                self.assertEqual(req.landmarks[0].s, expected)
                self.assertEqual(req.snapshot()["landmarks"][0]["s"], expected)

    def test_rejects_invalid_input_before_agent(self):
        valid = request().snapshot()["landmarks"]
        cases = [
            {"days": 0, "landmarks": valid},
            {"days": 1, "landmarks": []},
            {"days": 1, "landmarks": [{**valid[0], "geo": [35]}]},
            {"days": 1, "landmarks": [{**valid[0], "geo": [math.inf, 135]}]},
            {"days": 1, "landmarks": [{**valid[0], "geo": [91, 135]}]},
            {"days": 1, "landmarks": [valid[0], {**valid[1], "id": "A"}]},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValidationError):
                PlanRequest.model_validate(case)

    def test_complete_plan_keeps_original_ids_and_geometry(self):
        req = request()
        plan, errors = normalize_candidate(req, "run-fixed", {"days": [
            {"day": 1, "point_ids": ["A", "B"]},
            {"day": 2, "point_ids": ["D", "C"]},
        ]})
        self.assertEqual(errors, [])
        self.assertEqual(plan.status, "complete")
        self.assertTrue(plan.validation.passed)
        self.assertEqual([lm["id"] for lm in plan.request_snapshot["landmarks"]], ["A", "B", "C", "D"])
        self.assertEqual(set(plan.days[0].point_ids), {"A", "B"})
        self.assertEqual(plan.days[0].legs[0].distance_m, 0)
        self.assertEqual(validate_plan(plan, req), [])
        self.assertAlmostEqual(
            plan.days[1].legs[0].distance_m,
            straight_line_distance_m([35.01, 135.01], [35.02, 135.02]),
            delta=0.01,
        )

    def test_more_days_than_points_keeps_empty_days(self):
        req = request(days=5)
        plan, errors = normalize_candidate(req, "run-fixed", {"days": [
            {"day": 1, "point_ids": ["A"]}, {"day": 2, "point_ids": ["B"]},
            {"day": 3, "point_ids": ["C"]}, {"day": 4, "point_ids": ["D"]},
            {"day": 5, "point_ids": []},
        ]})
        self.assertEqual(errors, [])
        self.assertEqual(len(plan.days), 5)
        self.assertEqual(plan.days[-1].point_ids, [])
        self.assertIn("EMPTY_DAY", [warning.code for warning in plan.validation.warnings])

    def test_bad_references_become_draft_with_all_input_points_accounted_for(self):
        req = request()
        plan, errors = normalize_candidate(req, "run-fixed", {"days": [
            {"day": 1, "point_ids": ["A", "B", "X"]},
            {"day": 2, "point_ids": ["B", "C"]},
        ]})
        self.assertEqual(plan.status, "draft")
        self.assertEqual(plan.unassigned_point_ids, ["D"])
        self.assertEqual({error.code for error in errors}, {"UNKNOWN_LANDMARK", "DUPLICATE_LANDMARK", "MISSING_LANDMARK"})
        self.assertEqual(validate_plan(plan, req), [])

    def test_unusable_output_has_no_plan(self):
        plan, errors = normalize_candidate(request(), "run-fixed", {"days": "bad"})
        self.assertIsNone(plan)
        self.assertEqual(errors[0].code, "MODEL_OUTPUT_INVALID")

    def test_start_date_is_optional_but_rejects_timestamps_and_invalid_dates(self):
        payload = request().snapshot()
        self.assertIsNone(PlanRequest.model_validate(payload).start_date)
        self.assertIsNone(PlanRequest.model_validate({**payload, "start_date": ""}).start_date)
        for value in (12345, True, "2026-02-30", "2026-10-26T12:00:00", "20261026"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                PlanRequest.model_validate({**payload, "start_date": value})

    def test_scene_constraints_survive_geometry_optimization_and_round_trip(self):
        req = request(days=1)
        preferences = [
            ScenePreference(point_id="A", preferred_time="evening"),
            ScenePreference(point_id="B", preferred_time="sunset"),
            ScenePreference(point_id="C", preferred_time="morning"),
            ScenePreference(point_id="D", preferred_time="afternoon"),
        ]
        plan, errors = normalize_candidate(req, "run-fixed", {"days": [{"day": 1, "point_ids": ["A", "B", "C", "D"]}]}, scene_preferences=preferences)
        self.assertEqual(errors, [])
        self.assertEqual(plan.days[0].point_ids, ["C", "D", "B", "A"])
        self.assertEqual(validate_plan(plan, req), [])
        restored = Plan.model_validate_json(plan.model_dump_json())
        self.assertEqual(restored.scene_preferences, preferences)
        self.assertEqual(restored.days[0].point_ids, ["C", "D", "B", "A"])

    def test_story_order_for_same_work_does_not_apply_to_other_work(self):
        req = request(days=1, landmarks=[
            {"id": "A", "name": "结尾", "geo": [35, 135], "bangumiName": "同一作品"},
            {"id": "B", "name": "开头", "geo": [35.01, 135], "bangumiName": "同一作品"},
        ])
        preferences = [ScenePreference(point_id="A", scene_order=2), ScenePreference(point_id="B", scene_order=1)]
        plan, errors = normalize_candidate(req, "run", {"days": [{"day": 1, "point_ids": ["A", "B"]}]}, scene_preferences=preferences)
        self.assertEqual(errors, [])
        self.assertEqual(plan.days[0].point_ids, ["B", "A"])
        req.landmarks[1].bangumiName = "另一作品"
        plan, errors = normalize_candidate(req, "run", {"days": [{"day": 1, "point_ids": ["A", "B"]}]}, scene_preferences=preferences)
        self.assertEqual(errors, [])
        self.assertEqual(plan.days[0].point_ids, ["A", "B"])

    def test_time_preference_takes_priority_when_story_order_conflicts(self):
        req = request(days=1, landmarks=[
            {"id": 1, "name": "夜景", "geo": [35, 135], "bangumiName": "作品"},
            {"id": 2, "name": "晨景", "geo": [35.01, 135], "bangumiName": "作品"},
        ])
        plan, errors = normalize_candidate(req, "run", {"days": [{"day": 1, "point_ids": [1, 2]}]}, scene_preferences=[
            ScenePreference(point_id=1, preferred_time="evening", scene_order=1),
            ScenePreference(point_id=2, preferred_time="morning", scene_order=2),
        ])
        self.assertEqual(errors, [])
        self.assertEqual(plan.days[0].point_ids, [2, 1])
        self.assertTrue(all(type(value) is int for value in plan.days[0].point_ids))


if __name__ == "__main__":
    unittest.main()

