import time
import unittest
from unittest.mock import MagicMock, mock_open, patch

from fastapi.testclient import TestClient

import admin_auth
import server


USERNAME = "管理员"
PASSWORD = "test-only-password-2026"
LOGIN_HEADERS = {"X-Admin-Request": "1"}
ENDPOINTS = [
    ("GET", "/api/rag/landmarks", None),
    ("GET", "/api/rag/landmark/A/chunks", None),
    ("GET", "/api/rag/query?query=bridge", None),
    ("GET", "/api/rag/pending", None),
    ("GET", "/api/rag/logs", None),
    ("GET", "/api/agent/traces", None),
    ("GET", "/api/agent/trace/run-test", None),
    ("POST", "/api/rag/pending/approve", {"id": "A", "chunks": ["approved"]}),
    ("POST", "/api/rag/pending/reject", {"id": "A"}),
    ("DELETE", "/api/rag/landmarks/A", None),
    ("POST", "/api/rag/clear", None),
    ("POST", "/api/rag/logs/clear", None),
    ("POST", "/api/agent/traces/clear", None),
]


class AdminAuthTests(unittest.TestCase):
    def setUp(self):
        self.auth = admin_auth.AdminAuth(USERNAME, PASSWORD)
        self.auth_patch = patch.object(admin_auth, "admin_auth", self.auth)
        self.auth_patch.start()
        self.addCleanup(self.auth_patch.stop)
        self.client = TestClient(server.app)
        self.addCleanup(self.client.close)

        # Every data access and file mutation is a spy; these tests never touch
        # the real knowledge base, pending queue, logs, or trace files.
        self.rag = MagicMock()
        self.rag.db.get.return_value = {"ids": ["chunk"], "documents": ["fixture"], "metadatas": [
            {"landmark_id": "A", "landmark_name": "bridge", "bangumi": "anime"},
        ]}
        self.rag.db.similarity_search.return_value = []
        self.rag.get_pending_list.return_value = [{"id": "A", "chunks": ["fixture"]}]
        self.rag.approve_pending.return_value = True
        self.rag.reject_pending.return_value = True
        self.rag.delete_landmark_chunks.return_value = True
        for target, value in [
            ("server.rag_service", self.rag),
            ("server.agent_trace.list_traces", MagicMock(return_value=[{"run_id": "run-test"}])),
            ("server.agent_trace.get_trace", MagicMock(return_value={"run_id": "run-test", "steps": []})),
            ("server.agent_trace.clear_traces", MagicMock()),
            ("server.os.remove", MagicMock()),
            ("server.open", mock_open(read_data='[{"type":"fixture"}]')),
        ]:
            patcher = patch(target, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def login(self):
        response = self.client.post("/api/admin/login", headers=LOGIN_HEADERS,
                                    json={"username": USERNAME, "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def assert_no_data_access(self):
        self.assertEqual(self.rag.mock_calls, [])
        server.agent_trace.list_traces.assert_not_called()
        server.agent_trace.get_trace.assert_not_called()
        server.agent_trace.clear_traces.assert_not_called()
        server.os.remove.assert_not_called()
        server.open.assert_not_called()

    def test_all_management_endpoints_deny_anonymous_requests_before_data_access(self):
        for method, path, body in ENDPOINTS:
            with self.subTest(method=method, path=path):
                response = self.client.request(method, path, json=body)
                self.assertEqual(response.status_code, 401, response.text)
                self.assertEqual(response.headers["cache-control"], "no-store")
        self.assert_no_data_access()

    def test_management_router_has_authentication_for_every_registered_endpoint(self):
        # Keep coverage complete when someone adds another management endpoint.
        for route in server.management_router.routes:
            self.assertTrue(any(dep.dependency is admin_auth.require_admin for dep in route.dependencies), route.path)
        self.assertEqual(len(ENDPOINTS), len(server.management_router.routes))

    def test_no_credentials_or_short_password_disable_the_entire_admin_api(self):
        for username, password in [("", ""), (USERNAME, "short"), ("", PASSWORD)]:
            with self.subTest(username=username, password_length=len(password)):
                with patch.object(admin_auth, "admin_auth", admin_auth.AdminAuth(username, password)):
                    for method, path, body in ENDPOINTS:
                        self.assertEqual(self.client.request(method, path, json=body).status_code, 503)
                    self.assertEqual(self.client.get("/api/admin/session").status_code, 503)
                    self.assertEqual(self.client.post("/api/admin/login", headers=LOGIN_HEADERS,
                        json={"username": USERNAME, "password": PASSWORD}).status_code, 503)
        self.assert_no_data_access()

    def test_login_sets_private_cookie_and_session_can_be_restored(self):
        response = self.login()
        cookie = response.headers["set-cookie"]
        for attribute in ["HttpOnly", "SameSite=strict", "Path=/api", "Max-Age=28800"]:
            self.assertIn(attribute, cookie)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn(PASSWORD, response.text)
        self.assertEqual(response.json()["username"], USERNAME)
        self.assertTrue(response.json()["csrf_token"])
        restored = self.client.get("/api/admin/session")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json(), response.json())

    def test_secure_cookie_is_enabled_for_https_deployments(self):
        self.auth.secure = True
        self.assertIn("Secure", self.login().headers["set-cookie"])

    def test_invalid_username_or_password_never_creates_session(self):
        for username, password in [("other", PASSWORD), (USERNAME, "incorrect")]:
            response = self.client.post("/api/admin/login", headers=LOGIN_HEADERS,
                                       json={"username": username, "password": password})
            self.assertEqual(response.status_code, 401)
            self.assertNotIn("set-cookie", response.headers)
        self.assertEqual(self.client.get("/api/admin/session").status_code, 401)
        self.assert_no_data_access()

    def test_login_rejects_cross_site_requests_and_missing_custom_header(self):
        for headers in [{}, {**LOGIN_HEADERS, "Sec-Fetch-Site": "cross-site", "Origin": "https://example.org"}]:
            response = self.client.post("/api/admin/login", headers=headers,
                                       json={"username": USERNAME, "password": PASSWORD})
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.auth._sessions, {})

    def test_invalid_login_input_does_not_echo_password(self):
        response = self.client.post("/api/admin/login", headers=LOGIN_HEADERS,
                                   json={"username": USERNAME, "password": "sensitive" * 130})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("sensitive", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_every_write_requires_the_session_csrf_token(self):
        self.login()
        for method, path, body in ENDPOINTS:
            if method == "GET":
                continue
            for token in ["", "forged"]:
                with self.subTest(path=path, token=token):
                    response = self.client.request(method, path, json=body, headers={"X-CSRF-Token": token})
                    self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.post("/api/admin/logout").status_code, 403)
        self.assert_no_data_access()

    def test_logged_in_admin_can_read_and_write_every_management_endpoint(self):
        csrf = self.login().json()["csrf_token"]
        for method, path, body in ENDPOINTS:
            with self.subTest(method=method, path=path):
                response = self.client.request(method, path, json=body, headers={"X-CSRF-Token": csrf})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.headers["cache-control"], "no-store")
        self.rag.get_pending_list.assert_called_once()
        self.rag.approve_pending.assert_called_once_with("A", ["approved"])
        self.rag.reject_pending.assert_called_once_with("A")
        self.rag.delete_landmark_chunks.assert_called_once_with("A")
        self.rag.clear_database.assert_called_once()
        server.agent_trace.list_traces.assert_called_once()
        server.agent_trace.get_trace.assert_called_once_with("run-test")
        server.agent_trace.clear_traces.assert_called_once()

    def test_forged_or_expired_cookie_cannot_read_or_write(self):
        data = self.login().json()
        cookie = self.client.cookies.get(admin_auth.COOKIE_NAME)
        for token in ["forged", cookie + "tampered"]:
            response = self.client.get("/api/rag/pending", headers={"Cookie": f"{admin_auth.COOKIE_NAME}={token}"})
            self.assertEqual(response.status_code, 401)
        with patch("admin_auth.time.time", return_value=data["expires_at"] + 1):
            for method, path, body in ENDPOINTS:
                self.assertEqual(self.client.request(method, path, json=body,
                    headers={"X-CSRF-Token": data["csrf_token"]}).status_code, 401)
        self.assert_no_data_access()

    def test_logout_revokes_captured_cookie_on_server(self):
        csrf = self.login().json()["csrf_token"]
        cookie = self.client.cookies.get(admin_auth.COOKIE_NAME)
        response = self.client.post("/api/admin/logout", headers={"X-CSRF-Token": csrf})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Max-Age=0", response.headers["set-cookie"])
        for method, path, body in ENDPOINTS:
            response = self.client.request(method, path, json=body, headers={
                "Cookie": f"{admin_auth.COOKIE_NAME}={cookie}", "X-CSRF-Token": csrf,
            })
            self.assertEqual(response.status_code, 401)
        self.assert_no_data_access()

    def test_csrf_token_from_another_session_cannot_authorize_writes(self):
        old_csrf = self.login().json()["csrf_token"]
        self.login()
        response = self.client.post("/api/rag/clear", headers={"X-CSRF-Token": old_csrf})
        self.assertEqual(response.status_code, 403)
        self.assert_no_data_access()

    def test_repeated_failed_logins_are_rate_limited(self):
        for _ in range(self.auth.MAX_LOGIN_ATTEMPTS):
            response = self.client.post("/api/admin/login", headers=LOGIN_HEADERS,
                                       json={"username": USERNAME, "password": "wrong"})
            self.assertEqual(response.status_code, 401)
        response = self.client.post("/api/admin/login", headers=LOGIN_HEADERS,
                                   json={"username": USERNAME, "password": PASSWORD})
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response.headers["retry-after"]), 0)
        with patch("admin_auth.time.time", return_value=time.time() + self.auth.LOGIN_WINDOW + 1):
            self.login()

    def test_planning_input_validation_remains_public(self):
        for path in ["/api/agent/plan", "/api/v2/agent/plan"]:
            response = self.client.post(path, json={"days": 0, "landmarks": []})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["code"], "INVALID_INPUT")


if __name__ == "__main__":
    unittest.main()
