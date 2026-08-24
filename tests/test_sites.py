#!/usr/bin/env python3
"""Tests for site registration on tailnet and public internet (Caddy routes + Headscale records)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _jolo import sites

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

PUB_SEED = """# Generated jolo public project routes for berghome.
# Imported from /etc/caddy/Caddyfile via /etc/caddy/conf.d/*.
demo.pub.glvortex.net {
    basic_auth {
        tsb $2a$14$abcdefghijklmnopqrstuv
    }
    reverse_proxy 127.0.0.1:4100
}

open.pub.glvortex.net {
    reverse_proxy 127.0.0.1:4200
}
"""


class SitesTestCase(unittest.TestCase):
    """Seeded control-plane fragments in a throwaway directory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "caddy").mkdir()
        (root / "headscale").mkdir()
        (root / sites.CADDY_RELPATH).write_text(CADDY_SEED)
        (root / sites.RECORDS_RELPATH).write_text(
            json.dumps(RECORDS_SEED, indent=2) + "\n"
        )
        (root / sites.PUB_RELPATH).write_text(PUB_SEED)
        patcher = mock.patch.object(
            sites.constants, "TAILNET_CONTROL_DIR", str(root)
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def record_names(self):
        return [r["name"] for r in sites.read_records()]


class TestAvailability(SitesTestCase):
    def test_available_when_both_fragments_exist(self):
        self.assertTrue(sites.is_available())

    def test_unavailable_when_control_dir_missing(self):
        with mock.patch.object(
            sites.constants, "TAILNET_CONTROL_DIR", "/nonexistent/tailnet"
        ):
            self.assertFalse(sites.is_available())

    def test_register_is_a_noop_without_control_plane(self):
        """Hosts outside the share must still run jolo up."""
        with mock.patch.object(
            sites.constants, "TAILNET_CONTROL_DIR", "/nonexistent/tailnet"
        ):
            self.assertIsNone(sites.register_tailnet("test4k", 4676))


class TestRegister(SitesTestCase):
    def test_adds_route_and_record_pointing_at_the_tls_router(self):
        url = sites.register_tailnet("test4k", 4676)

        self.assertEqual(url, "https://test4k.ts.glvortex.net")
        self.assertEqual(sites.read_routes()["test4k.ts.glvortex.net"], 4676)
        record = next(
            r
            for r in sites.read_records()
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
        sites.register_tailnet("test4k", 4676)

        routes = sites.read_routes()
        self.assertEqual(routes["peupeuell.ts.glvortex.net"], 4252)
        self.assertEqual(routes["testus4k.ts.glvortex.net"], 4452)
        self.assertIn("peupeuell.ts.glvortex.net", self.record_names())

    def test_repeated_registration_does_not_duplicate(self):
        """Every jolo up re-registers; the fragments must not grow."""
        for _ in range(3):
            sites.register_tailnet("test4k", 4676)

        self.assertEqual(len(sites.read_routes()), 3)
        self.assertEqual(len(sites.read_records()), 3)
        text = (Path(self.tmp.name) / sites.CADDY_RELPATH).read_text()
        self.assertEqual(text.count("http://test4k.ts.glvortex.net"), 1)

    def test_port_change_rewrites_the_route(self):
        sites.register_tailnet("test4k", 4676)
        sites.register_tailnet("test4k", 5000)

        self.assertEqual(sites.read_routes()["test4k.ts.glvortex.net"], 5000)
        self.assertEqual(len(sites.read_routes()), 3)

    def test_rejects_names_that_are_not_dns_labels(self):
        for bad in ["My_Project", "has spaces", "-leading", "trailing-", ""]:
            with self.subTest(name=bad):
                with mock.patch("sys.stderr"):
                    self.assertIsNone(sites.register_tailnet(bad, 4676))
                self.assertEqual(len(sites.read_routes()), 2)

    def test_written_caddy_fragment_keeps_its_header(self):
        sites.register_tailnet("test4k", 4676)

        text = (Path(self.tmp.name) / sites.CADDY_RELPATH).read_text()
        self.assertTrue(text.startswith("# Generated jolo tailnet project"))


class TestUnregister(SitesTestCase):
    def test_removes_route_and_record(self):
        self.assertTrue(sites.unregister("testus4k"))

        self.assertNotIn("testus4k.ts.glvortex.net", sites.read_routes())
        self.assertNotIn("testus4k.ts.glvortex.net", self.record_names())

    def test_keeps_other_projects(self):
        sites.unregister("testus4k")

        self.assertIn("peupeuell.ts.glvortex.net", sites.read_routes())
        self.assertIn("peupeuell.ts.glvortex.net", self.record_names())

    def test_unknown_project_reports_no_change(self):
        self.assertFalse(sites.unregister("never-existed"))


class TestNoPartialWrites(SitesTestCase):
    def test_failed_write_leaves_the_old_file_intact(self):
        """Syncthing ships whatever is on disk, so writes must be atomic."""
        with mock.patch("os.replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                sites.register_tailnet("test4k", 4676)

        self.assertEqual(
            (Path(self.tmp.name) / sites.CADDY_RELPATH).read_text(),
            CADDY_SEED,
        )
        leftovers = list(
            (Path(self.tmp.name) / "caddy").glob(".jolo-sites.caddy.*")
        )
        self.assertEqual(leftovers, [])


class TestPublicRoutes(SitesTestCase):
    def test_parses_authed_and_open_routes(self):
        routes = sites.read_public()

        self.assertEqual(
            routes["demo.pub.glvortex.net"],
            (4100, "$2a$14$abcdefghijklmnopqrstuv"),
        )
        self.assertEqual(routes["open.pub.glvortex.net"], (4200, None))

    def test_register_adds_an_authed_block(self):
        url = sites.register_public("test4k", 4676, "$2a$14$hash")

        self.assertEqual(url, "https://test4k.pub.glvortex.net")
        self.assertEqual(
            sites.read_public()["test4k.pub.glvortex.net"],
            (4676, "$2a$14$hash"),
        )
        text = (Path(self.tmp.name) / sites.PUB_RELPATH).read_text()
        self.assertIn("basic_auth {", text)

    def test_register_without_a_hash_omits_basic_auth(self):
        sites.register_public("test4k", 4676, None)

        text = (Path(self.tmp.name) / sites.PUB_RELPATH).read_text()
        block = text.split("test4k.pub.glvortex.net {")[1].split("}")[0]
        self.assertNotIn("basic_auth", block)

    def test_repeated_registration_does_not_duplicate(self):
        for _ in range(3):
            sites.register_public("test4k", 4676, "$2a$14$hash")

        self.assertEqual(len(sites.read_public()), 3)

    def test_port_change_rewrites_the_block(self):
        sites.register_public("test4k", 4676, "$2a$14$hash")
        sites.register_public("test4k", 5000, "$2a$14$hash")

        self.assertEqual(
            sites.read_public()["test4k.pub.glvortex.net"],
            (5000, "$2a$14$hash"),
        )

    def test_rejects_names_that_are_not_dns_labels(self):
        with mock.patch("sys.stderr"):
            self.assertIsNone(sites.register_public("My_Project", 4676, None))

        self.assertEqual(len(sites.read_public()), 2)

    def test_unregister_clears_public_tailnet_and_dns(self):
        sites.register_public("testus4k", 4676, "$2a$14$hash")

        self.assertTrue(sites.unregister("testus4k"))

        self.assertNotIn("testus4k.pub.glvortex.net", sites.read_public())
        self.assertNotIn("testus4k.ts.glvortex.net", sites.read_routes())
        self.assertNotIn("testus4k.ts.glvortex.net", self.record_names())

    def test_unregister_leaves_other_public_projects(self):
        sites.unregister("demo")

        self.assertNotIn("demo.pub.glvortex.net", sites.read_public())
        self.assertIn("open.pub.glvortex.net", sites.read_public())

    def test_read_public_is_empty_without_a_public_fragment(self):
        """No `is_available()` guard on the read side: a host that never
        published anything simply has no file yet."""
        Path(self.tmp.name, sites.PUB_RELPATH).unlink()

        self.assertEqual(sites.read_public(), {})

    def test_unregister_public_leaves_the_tailnet_site_alone(self):
        sites.register_public("testus4k", 4676, "$2a$14$hash")

        self.assertTrue(sites.unregister_public("testus4k"))

        self.assertNotIn("testus4k.pub.glvortex.net", sites.read_public())
        self.assertIn("testus4k.ts.glvortex.net", sites.read_routes())
        self.assertIn("testus4k.ts.glvortex.net", self.record_names())


class TestSetPortRepointsPublicRoute(SitesTestCase):
    """`container.set_port` is the single choke point for port changes —
    it must re-point an existing public route so a recycled port never
    silently serves a different project to the internet."""

    def _write_devcontainer(self, workspace_dir: Path, port: int) -> None:
        devc = workspace_dir / ".devcontainer"
        devc.mkdir(parents=True)
        (devc / "devcontainer.json").write_text(
            json.dumps(
                {
                    "containerEnv": {"PORT": str(port)},
                    "runArgs": ["-p", f"{port}:{port}"],
                },
                indent=4,
            )
            + "\n"
        )

    def test_port_change_repoints_the_public_route(self):
        from _jolo import container

        workspace_dir = Path(self.tmp.name) / "workspace" / "demo"
        self._write_devcontainer(workspace_dir, 4100)

        container.set_port(workspace_dir, 5000)

        self.assertEqual(
            sites.read_public()["demo.pub.glvortex.net"],
            (5000, "$2a$14$abcdefghijklmnopqrstuv"),
        )

    def test_port_change_does_not_publish_an_unpublished_project(self):
        from _jolo import container

        workspace_dir = Path(self.tmp.name) / "workspace" / "peupeuell"
        self._write_devcontainer(workspace_dir, 4252)

        container.set_port(workspace_dir, 5000)

        self.assertNotIn("peupeuell.pub.glvortex.net", sites.read_public())


class TestResolveSiteUrlRepointsPublicRoute(SitesTestCase):
    """`commands._resolve_site_url` runs on every container start, so it is
    the other choke point (besides `jolo port`) that must self-heal a stale
    public route left over from a port change."""

    def test_repoints_a_published_projects_route(self):
        from _jolo import commands

        workspace_dir = Path(self.tmp.name) / "workspace" / "demo"
        devc = workspace_dir / ".devcontainer"
        devc.mkdir(parents=True)
        (devc / "devcontainer.json").write_text(
            json.dumps(
                {"containerEnv": {"PORT": "5000"}},
                indent=4,
            )
            + "\n"
        )

        commands._resolve_site_url(workspace_dir)

        self.assertEqual(
            sites.read_public()["demo.pub.glvortex.net"],
            (5000, "$2a$14$abcdefghijklmnopqrstuv"),
        )

    def test_hidden_dir_registers_slug(self):
        from _jolo import commands

        workspace_dir = Path(self.tmp.name) / "workspace" / ".pi"
        devc = workspace_dir / ".devcontainer"
        devc.mkdir(parents=True)
        (devc / "devcontainer.json").write_text(
            json.dumps({"containerEnv": {"PORT": "4324"}}, indent=4) + "\n"
        )

        url = commands._resolve_site_url(workspace_dir)

        self.assertEqual(url, "https://pi.ts.glvortex.net")
        self.assertEqual(sites.read_routes()["pi.ts.glvortex.net"], 4324)


class TestOwnership(SitesTestCase):
    def test_owner_is_the_registered_workspace_with_that_name(self):
        paths = [(Path("/home/tsb/dev/test4k"), 1.0)]
        with mock.patch.object(
            sites.registry, "known_paths", return_value=paths
        ):
            self.assertEqual(
                sites.owner_of("test4k"), Path("/home/tsb/dev/test4k")
            )

    def test_owner_is_none_for_an_unknown_name(self):
        with mock.patch.object(sites.registry, "known_paths", return_value=[]):
            self.assertIsNone(sites.owner_of("test4k"))

    def test_owner_matches_slugged_hidden_dir(self):
        path = Path(self.tmp.name) / ".pi"
        path.mkdir()
        with mock.patch.object(
            sites.registry, "known_paths", return_value=[(path, 1.0)]
        ):
            self.assertEqual(sites.owner_of("pi"), path)


if __name__ == "__main__":
    unittest.main()
