import math
import unittest

from pydantic import ValidationError

from plan_geometry import straight_line_distance_m
from plan_schema import PlanRequest
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


if __name__ == "__main__":
    unittest.main()

