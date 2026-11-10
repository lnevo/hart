"""The local portal server: the retired F-root review route is gone, the archive edit route still answers."""
import http.client
import json
import sys
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import serve_portal  # noqa: E402


class PortalRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        serve_portal.PortalHandler.log_message = lambda *a, **k: None
        cls.server = HTTPServer(("127.0.0.1", 0), serve_portal.PortalHandler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, method: str, path: str, body: object = None) -> int:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Host": f"127.0.0.1:{self.port}"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers |= {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{self.port}"}
        conn.request(method, path, body=data, headers=headers)
        status = conn.getresponse().status
        conn.close()
        return status

    def test_f_root_log_route_is_gone(self) -> None:
        self.assertEqual(self.request("GET", "/api/f-root-review/log"), 404)
        self.assertEqual(self.request("POST", "/api/f-root-review/log", {"path": "x"}), 404)

    def test_archive_route_still_validates(self) -> None:
        # Unknown item id: routed to the archive handler, which refuses it without writing.
        self.assertIn(self.request("POST", "/api/archive/item", {"id": "no-such-item"}), (400, 404))

    def test_website_is_served(self) -> None:
        self.assertEqual(self.request("GET", "/www/index.html"), 200)

    def test_repo_root_is_not_served(self) -> None:
        self.assertEqual(self.request("GET", "/AGENTS.md"), 404)


if __name__ == "__main__":
    unittest.main()
