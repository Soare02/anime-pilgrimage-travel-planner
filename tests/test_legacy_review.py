import unittest
from unittest.mock import patch

import agent


STATE = {
    "raw_landmarks": [{"id": "A", "name": "测试点"}],
    "refined_itinerary": {"days": [{"day_number": 1, "landmarks": [{"name": "测试点"}]}]},
    "revision_count": 3,
}


class LegacyReviewTests(unittest.TestCase):
    def check_draft(self, response):
        with patch.object(agent, "traced_llm_invoke", return_value=response), \
             patch.object(agent, "llm_deepseek") as model:
            result = agent.supervisor_editor_node(STATE)
        self.assertEqual(result["review_status"], "draft")
        self.assertTrue(result["errors"])
        self.assertIn("规划未通过", result["final_output"])
        self.assertEqual(agent.should_continue(result), "end")
        model.stream.assert_not_called()

    def test_bad_json_is_not_success(self):
        self.check_draft("broken JSON")

    def test_failed_review_with_empty_errors_is_not_success(self):
        self.check_draft('{"is_valid":false,"errors":[]}')

    def test_wrong_error_type_is_not_success(self):
        self.check_draft('{"is_valid":false,"errors":"bad"}')


if __name__ == "__main__":
    unittest.main()
