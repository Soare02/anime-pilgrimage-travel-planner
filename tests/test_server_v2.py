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
        self.assertIn("巡礼天数", response.json()["message"])
        start.assert_not_called()

    def test_invalid_coordinates_identify_the_actual_landmark(self):
        body = {**BODY, "landmarks": [{**BODY["landmarks"][0], "geo": [91, 135]}]}
        with patch.object(server.agent_trace, "start_run") as start:
            response = self.client.post("/api/v2/agent/plan", json=body)
        self.assertEqual(response.status_code, 422)
        self.assertIn("第 1 个地标的坐标", response.json()["message"])
        self.assertIn("坐标超出合法经纬度范围", response.json()["message"])
        start.assert_not_called()

    def test_invalid_departure_date_is_rejected_before_starting_a_run(self):
        with patch.object(server.agent_trace, "start_run") as start:
            response = self.client.post("/api/v2/agent/plan", json={**BODY, "start_date": "2026-02-30"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("出发日期", response.json()["message"])
        start.assert_not_called()

    def test_landmark_limit_reports_count_instead_of_blaming_coordinates(self):
        body = {"days": 1, "landmarks": [
            {**BODY["landmarks"][0], "id": str(index)} for index in range(server.MAX_LANDMARKS + 1)
        ]}
        with patch.object(server.agent_trace, "start_run") as start:
            response = self.client.post("/api/v2/agent/plan", json=body)
        self.assertEqual(response.status_code, 422)
        self.assertIn(f"已选择 {server.MAX_LANDMARKS + 1} 个地标", response.json()["message"])
        self.assertIn(f"最多支持 {server.MAX_LANDMARKS} 个", response.json()["message"])
        start.assert_not_called()

    def test_structured_success_stream_has_terminal_event(self):
        body = {**BODY, "start_date": "2026-10-26", "landmarks": [
            {**BODY["landmarks"][0], "s": ""}, {**BODY["landmarks"][1], "s": "18：41"},
        ]}
        req = PlanRequest.model_validate(body)
        plan, errors = normalize_candidate(req, "run-test", {"days": [
            {"day": 1, "point_ids": ["A"]}, {"day": 2, "point_ids": ["B"]},
        ]})
        with patch.object(server.agent_trace, "start_run", return_value="run-test"), \
             patch.object(server.agent_trace, "end_run_by_id"), \
             patch.object(server, "run_plan", return_value=(plan, errors, "# 计划\n")) as run:
            response = self.client.post("/api/v2/agent/plan", json=body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([lm.s for lm in run.call_args.args[0].landmarks], [None, 1121])
        self.assertEqual(run.call_args.args[0].start_date.isoformat(), "2026-10-26")
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        self.assertEqual([event["type"] for event in events], ["run_started", "plan_ready", "run_finished"])
        self.assertTrue(all(event["run_id"] == "run-test" and event["event_id"] for event in events))
        self.assertEqual(events[-1]["payload"]["status"], "success")
        self.assertEqual(events[1]["payload"]["plan"]["days"][0]["point_ids"], ["A"])
        self.assertEqual(events[1]["payload"]["plan"]["days"][1]["date"], "2026-10-27")

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

    def test_step_updates_are_streamed_before_terminal_plan(self):
        req = PlanRequest.model_validate(BODY)
        plan, errors = normalize_candidate(req, "run-test", {"days": [
            {"day": 1, "point_ids": ["A"]}, {"day": 2, "point_ids": ["B"]},
        ]})

        def run(request, run_id, *, on_progress, should_cancel, on_step):
            on_step({"id": "phase:route:1", "stage": "route", "kind": "phase", "sequence": 1,
                     "status": "completed", "summary": "已生成 2 天路线初稿"})
            return plan, errors, "# 计划"

        with patch.object(server.agent_trace, "start_run", return_value="run-test"), \
             patch.object(server.agent_trace, "end_run_by_id"), patch.object(server, "run_plan", side_effect=run):
            response = self.client.post("/api/v2/agent/plan", json=BODY)
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        self.assertEqual([event["type"] for event in events], ["run_started", "step_update", "plan_ready", "run_finished"])
        self.assertEqual(events[1]["payload"]["summary"], "已生成 2 天路线初稿")


if __name__ == "__main__":
    unittest.main()

