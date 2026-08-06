#!/usr/bin/env python3
"""Tests for tailnet site registration (Caddy routes + Headscale records)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _jolo import tailnet

CADDY_SEED = """# Generated jolo tailnet project routes for berghome.
# Imported from /etc/caddy/Caddyfile via /etc/caddy/conf.d/*.
http://peupeuell.ts.glvortex.net {
    reverse_proxy 127.0.0.1:4252
}

http://testus4k.ts.glvortex.net {
    reverse_proxy 127.0.0.1:4452
}
"""

RECORDS_SEED = [
    {"name": "peupeuell.ts.glvortex.net", "type": "A", "value": "100.64.0.4"},
    {"name": "testus4k.ts.glvortex.net", "type": "A", "value": "100.64.0.4"},
]


class TailnetTestCase(unittest.TestCase):
    """Seeded control-plane fragments in a throwaway directory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "caddy").mkdir()
        (root / "headscale").mkdir()
        (root / "nginx").mkdir()
        (root / tailnet.CADDY_RELPATH).write_text(CADDY_SEED)
        (root / tailnet.RECORDS_RELPATH).write_text(
            json.dumps(RECORDS_SEED, indent=2) + "\n"
        )
        patcher = mock.patch.object(
            tailnet.constants, "TAILNET_CONTROL_DIR", str(root)
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def record_names(self):
        return [r["name"] for r in tailnet.read_records()]


class TestAvailability(TailnetTestCase):
    def test_available_when_both_fragments_exist(self):
        self.assertTrue(tailnet.is_available())

    def test_unavailable_when_control_dir_missing(self):
        with mock.patch.object(
            tailnet.constants, "TAILNET_CONTROL_DIR", "/nonexistent/tailnet"
        ):
            self.assertFalse(tailnet.is_available())

    def test_register_is_a_noop_without_control_plane(self):
        """Hosts outside the share must still run jolo up."""
        with mock.patch.object(
            tailnet.constants, "TAILNET_CONTROL_DIR", "/nonexistent/tailnet"
        ):
            self.assertIsNone(tailnet.register("test4k", 4676))


class TestRegister(TailnetTestCase):
    def test_adds_route_and_record(self):
        url = tailnet.register("test4k", 4676)

        self.assertEqual(url, "https://test4k.ts.glvortex.net")
        self.assertEqual(tailnet.read_routes()["test4k.ts.glvortex.net"], 4676)
        self.assertIn("test4k.ts.glvortex.net", self.record_names())

    def test_record_points_at_the_tls_router(self):
        tailnet.register("test4k", 4676)

        record = next(
            r
            for r in tailnet.read_records()
            if r["name"] == "test4k.ts.glvortex.net"
        )
        self.assertEqual(
            record,
            {
                "name": "test4k.ts.glvortex.net",
                "type": "A",
                "value": "100.64.0.4",
            },
        )

    def test_leaves_existing_entries_alone(self):
        tailnet.register("test4k", 4676)

        routes = tailnet.read_routes()
        self.assertEqual(routes["peupeuell.ts.glvortex.net"], 4252)
        self.assertEqual(routes["testus4k.ts.glvortex.net"], 4452)
        self.assertIn("peupeuell.ts.glvortex.net", self.record_names())

    def test_repeated_registration_does_not_duplicate(self):
        """Every jolo up re-registers; the fragments must not grow."""
        for _ in range(3):
            tailnet.register("test4k", 4676)

        self.assertEqual(len(tailnet.read_routes()), 3)
        self.assertEqual(len(tailnet.read_records()), 3)
        text = (Path(self.tmp.name) / tailnet.CADDY_RELPATH).read_text()
        self.assertEqual(text.count("http://test4k.ts.glvortex.net"), 1)

    def test_port_change_rewrites_the_route(self):
        tailnet.register("test4k", 4676)
        tailnet.register("test4k", 5000)

        self.assertEqual(tailnet.read_routes()["test4k.ts.glvortex.net"], 5000)
        self.assertEqual(len(tailnet.read_routes()), 3)

    def test_rejects_names_that_are_not_dns_labels(self):
        for bad in ["My_Project", "has spaces", "-leading", "trailing-", ""]:
            with self.subTest(name=bad):
                with mock.patch("sys.stderr"):
                    self.assertIsNone(tailnet.register(bad, 4676))
                self.assertEqual(len(tailnet.read_routes()), 2)

    def test_written_caddy_fragment_keeps_its_header(self):
        tailnet.register("test4k", 4676)

        text = (Path(self.tmp.name) / tailnet.CADDY_RELPATH).read_text()
        self.assertTrue(text.startswith("# Generated jolo tailnet project"))

    def test_written_records_stay_valid_json(self):
        tailnet.register("test4k", 4676)

        raw = (Path(self.tmp.name) / tailnet.RECORDS_RELPATH).read_text()
        self.assertEqual(len(json.loads(raw)), 3)


class TestUnregister(TailnetTestCase):
    def test_removes_route_and_record(self):
        self.assertTrue(tailnet.unregister("testus4k"))

        self.assertNotIn("testus4k.ts.glvortex.net", tailnet.read_routes())
        self.assertNotIn("testus4k.ts.glvortex.net", self.record_names())

    def test_keeps_other_projects(self):
        tailnet.unregister("testus4k")

        self.assertIn("peupeuell.ts.glvortex.net", tailnet.read_routes())
        self.assertIn("peupeuell.ts.glvortex.net", self.record_names())

    def test_unknown_project_reports_no_change(self):
        self.assertFalse(tailnet.unregister("never-existed"))


class TestNoPartialWrites(TailnetTestCase):
    def test_failed_write_leaves_the_old_file_intact(self):
        """Syncthing ships whatever is on disk, so writes must be atomic."""
        with mock.patch("os.replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                tailnet.register("test4k", 4676)

        self.assertEqual(
            (Path(self.tmp.name) / tailnet.CADDY_RELPATH).read_text(),
            CADDY_SEED,
        )
        leftovers = list(
            (Path(self.tmp.name) / "caddy").glob(".jolo-sites.caddy.*")
        )
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
