#!/usr/bin/env python3
"""Tests for container/fetch-asset.

Drives the real script against a local HTTP server, so curl, the redirect
handling, and the magic-byte sniffing are all exercised for real. The refusal
paths are what earn their place here: every one of them must leave no file at
the destination.
"""

import http.server
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "container" / "fetch-asset"

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
)
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
GIF = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04"
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 \x18\x00\x00\x00\x30\x01\x00\x9d\x01\x2a"
SVG = b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg"></svg>'
DENIAL = (
    b"<!DOCTYPE html>\n<html><head><title>403 Forbidden</title></head>"
    b"<body><h1>Forbidden</h1><p>Scraping is not permitted.</p></body></html>"
)


AGENTS: list[str] = []


class Handler(http.server.BaseHTTPRequestHandler):
    """Serves canned responses keyed by path. Records the User-Agent seen."""

    def do_GET(self):  # noqa: N802 — BaseHTTPRequestHandler's naming
        AGENTS.append(self.headers.get("User-Agent", ""))
        routes = {
            "/good.png": (200, "image/png", PNG),
            "/good.jpg": (200, "image/jpeg", JPEG),
            "/good.gif": (200, "image/gif", GIF),
            "/good.webp": (200, "image/webp", WEBP),
            "/good.svg": (200, "image/svg+xml", SVG),
            "/denied": (403, "text/html", DENIAL),
            # The bug we actually hit: 200 OK, HTML body, .png destination.
            "/sneaky": (200, "text/html", DENIAL),
            "/empty": (200, "image/png", b""),
            "/wrong-type": (200, "image/png", JPEG),
            "/notfound": (404, "text/html", b"<html>nope</html>"),
        }
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/good.png")
            self.end_headers()
            return
        if self.path not in routes:
            self.send_error(500)
            return
        status, ctype, body = routes[self.path]
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


class FetchAssetTest(unittest.TestCase):
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

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def fetch(self, path, name):
        dest = Path(self.tmpdir.name) / name
        result = subprocess.run(
            [str(SCRIPT), f"{self.base}{path}", str(dest)],
            capture_output=True,
            text=True,
        )
        return result, dest

    def assert_refused(self, result, dest, expected_in_stderr):
        self.assertNotEqual(
            0, result.returncode, "should have exited non-zero"
        )
        self.assertIn(expected_in_stderr, result.stderr)
        self.assertFalse(dest.exists(), "must not write anything on failure")
        leftovers = list(Path(self.tmpdir.name).glob("*.fetch-asset.*"))
        self.assertEqual([], leftovers, "must not leave a temp file behind")

    def test_writes_a_valid_png(self):
        result, dest = self.fetch("/good.png", "art.png")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(PNG, dest.read_bytes())
        self.assertIn(str(dest), result.stdout)
        self.assertIn(f"{len(PNG)} bytes", result.stdout)
        self.assertIn("png", result.stdout)

    def test_accepts_each_known_format(self):
        for path, name, body in [
            ("/good.jpg", "a.jpg", JPEG),
            ("/good.gif", "a.gif", GIF),
            ("/good.webp", "a.webp", WEBP),
            ("/good.svg", "a.svg", SVG),
        ]:
            with self.subTest(name=name):
                result, dest = self.fetch(path, name)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(body, dest.read_bytes())

    def test_follows_redirects(self):
        result, dest = self.fetch("/redirect", "art.png")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(PNG, dest.read_bytes())

    def test_refuses_html_body_at_binary_extension(self):
        result, dest = self.fetch("/sneaky", "art.png")
        self.assert_refused(result, dest, "HTML page")

    def test_refuses_non_2xx(self):
        result, dest = self.fetch("/denied", "art.png")
        self.assert_refused(result, dest, "HTTP 403")

    def test_error_body_is_excerpted(self):
        result, _ = self.fetch("/notfound", "art.png")
        self.assertIn("HTTP 404", result.stderr)
        self.assertIn("nope", result.stderr)

    def test_refuses_empty_body(self):
        result, dest = self.fetch("/empty", "art.png")
        self.assert_refused(result, dest, "empty body")

    def test_refuses_type_mismatch(self):
        result, dest = self.fetch("/wrong-type", "art.png")
        self.assert_refused(result, dest, "body is jpeg")

    def test_refuses_html_at_svg_extension(self):
        result, dest = self.fetch("/sneaky", "icon.svg")
        self.assert_refused(result, dest, "HTML page")

    def test_unknown_extension_skips_the_sniff(self):
        result, dest = self.fetch("/good.png", "blob.dat")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(PNG, dest.read_bytes())

    def test_creates_missing_parent_directories(self):
        result, dest = self.fetch("/good.png", "nested/deep/art.png")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(dest.exists())

    def test_leaves_an_existing_file_alone_on_failure(self):
        dest = Path(self.tmpdir.name) / "art.png"
        dest.write_bytes(PNG)
        result, _ = self.fetch("/denied", "art.png")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(PNG, dest.read_bytes(), "must not clobber on failure")

    def test_sends_a_contact_user_agent(self):
        AGENTS.clear()
        self.fetch("/good.png", "art.png")
        self.assertTrue(AGENTS)
        agent = AGENTS[-1]
        self.assertIn("fetch-asset", agent)
        self.assertIn("mailto:", agent)

    def test_user_agent_is_overridable(self):
        AGENTS.clear()
        dest = Path(self.tmpdir.name) / "art.png"
        subprocess.run(
            [str(SCRIPT), f"{self.base}/good.png", str(dest)],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "FETCH_ASSET_UA": "custom/9.9"},
        )
        self.assertEqual("custom/9.9", AGENTS[-1])

    def test_requires_two_arguments(self):
        result = subprocess.run(
            [str(SCRIPT), "http://example.com/x.png"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("usage", result.stderr)


if __name__ == "__main__":
    unittest.main()
