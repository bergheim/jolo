#!/usr/bin/env python3
"""Tests for container/jolo-open."""

import http.server
import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "container" / "jolo-open"


class Handler(http.server.BaseHTTPRequestHandler):
    last_body = b""
    last_auth = ""

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        Handler.last_body = self.rfile.read(length)
        Handler.last_auth = self.headers.get("Authorization", "")
        if self.path != "/md":
            self.send_error(404)
            return
        payload = json.dumps(
            {
                "url": "https://example.com",
                "filter": "fit",
                "markdown": "# hi",
                "success": True,
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        pass


class JoloOpenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True
        )
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def run_script(self, *args, env=None):
        return subprocess.run(
            [str(SCRIPT), *args],
            capture_output=True,
            text=True,
            env=env,
        )

    def test_cats_a_relative_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.html"
            path.write_text("hello\n")
            result = self.run_script(str(path))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("hello\n", result.stdout)

    def test_cats_a_file_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.html"
            path.write_text("via-url\n")
            result = self.run_script(f"file://{path}")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("via-url\n", result.stdout)

    def test_http_posts_fit_markdown(self):
        env = {
            "CRAWL4AI_URL": self.base,
            "CRAWL4AI_API_TOKEN": "tok",
            "PATH": "/usr/bin:/bin",
        }
        result = self.run_script("https://example.com", env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("# hi\n", result.stdout)
        posted = json.loads(Handler.last_body)
        self.assertEqual({"url": "https://example.com", "f": "fit"}, posted)
        self.assertEqual("Bearer tok", Handler.last_auth)

    def test_missing_arg_is_nonzero(self):
        result = self.run_script()
        self.assertNotEqual(0, result.returncode)
