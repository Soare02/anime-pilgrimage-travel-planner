import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import server
from plan_schema import PlanRequest
from plan_validation import normalize_candidate


BODY = {
    "days": 2,
    "landmarks": [
        {"id": "A", "name": "同名", "geo": [35.0, 135.0], "bangumiName": "作品甲"},
        {"id": "B", "name": "同名", "geo": [35.01, 135.01], "bangumiName": "作品乙"},
    ],
}


class ServerV2Tests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)

    def test_invalid_input_returns_field_error_without_starting_run(self):
        with patch.object(server.agent_trace, "start_run") as start:
            response = self.client.post("/api/v2/agent/plan", json={**BODY, "days": 0})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "INVALID_INPUT")
        self.assertTrue(response.json()["fields"])
        start.assert_not_called()

    def test_structured_success_stream_has_terminal_event(self):
        req = PlanRequest.model_validate(BODY)
        plan, errors = normalize_candidate(req, "run-test", {"days": [
            {"day": 1, "point_ids": ["A"]}, {"day": 2, "point_ids": ["B"]},
        ]})
        with patch.object(server.agent_trace, "start_run", return_value="run-test"), \
             patch.object(server.agent_trace, "end_run_by_id"), \
             patch.object(server, "run_plan", return_value=(plan, errors, "# 计划\n")):
            response = self.client.post("/api/v2/agent/plan", json=BODY)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        self.assertEqual([event["type"] for event in events], ["run_started", "plan_ready", "run_finished"])
        self.assertTrue(all(event["run_id"] == "run-test" and event["event_id"] for event in events))
        self.assertEqual(events[-1]["payload"]["status"], "success")
        self.assertEqual(events[1]["payload"]["plan"]["days"][0]["point_ids"], ["A"])

    def test_draft_stream_never_reports_success(self):
        req = PlanRequest.model_validate(BODY)
        plan, errors = normalize_candidate(req, "run-test", {"days": [
            {"day": 1, "point_ids": ["A"]}, {"day": 2, "point_ids": []},
        ]})
        with patch.object(server.agent_trace, "start_run", return_value="run-test"), \
             patch.object(server.agent_trace, "end_run_by_id"), \
             patch.object(server, "run_plan", return_value=(plan, errors, "# 草案\n")):
            response = self.client.post("/api/v2/agent/plan", json=BODY)
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        self.assertEqual([event["type"] for event in events], ["run_started", "plan_draft", "run_finished"])
        self.assertEqual(events[-1]["payload"]["status"], "failed")
        self.assertFalse(events[1]["payload"]["plan"]["validation"]["passed"])


if __name__ == "__main__":
    unittest.main()

