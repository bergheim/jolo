#!/usr/bin/env python3
"""Tests for the peer registry (~/stash/.jolo/peers.json)."""

import datetime
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _jolo import registry


class TestRegistryPaths(unittest.TestCase):
    """Resolving the on-disk registry location."""

    def test_host_path_uses_stash_under_home(self):
        with tempfile.TemporaryDirectory() as td:
            with (
                mock.patch.dict(os.environ, {"HOME": td}, clear=False),
                mock.patch.object(
                    registry, "_CONTAINER_STASH", Path("/nonexistent/stash")
                ),
            ):
                p = registry.registry_path()
                self.assertEqual(
                    p, Path(td) / "stash" / ".jolo" / "peers.json"
                )

    def test_container_path_uses_workspaces_stash(self):
        with tempfile.TemporaryDirectory() as td:
            workspaces_stash = Path(td) / "workspaces" / "stash"
            workspaces_stash.mkdir(parents=True)
            with mock.patch.object(
                registry, "_CONTAINER_STASH", workspaces_stash
            ):
                p = registry.registry_path()
                self.assertEqual(p, workspaces_stash / ".jolo" / "peers.json")


class TestReadWrite(unittest.TestCase):
    """Round-trip registry entries."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        # Ensure reads resolve to host path under this fake HOME
        self._home_patch = mock.patch.dict(
            os.environ, {"HOME": str(self.home)}, clear=False
        )
        self._home_patch.start()
        # Disable container path (it might exist on this machine).
        self._stash_patch = mock.patch.object(
            registry, "_CONTAINER_STASH", Path("/nonexistent/stash")
        )
        self._stash_patch.start()

    def tearDown(self):
        self._stash_patch.stop()
        self._home_patch.stop()
        self.tmp.cleanup()

    def test_empty_when_missing(self):
        self.assertEqual(registry.read_all(), [])

    def test_write_then_read(self):
        entry = {
            "container": "emacs-container-main",
            "project": "emacs-container",
            "workspace": "/workspaces/emacs-container",
            "port": 4000,
            "branch": "main",
            "started_at": "2026-04-22T10:00:00Z",
        }
        registry.write_entry(entry)
        got = registry.read_all()
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["container"], "emacs-container-main")
        self.assertEqual(got[0]["port"], 4000)

    def test_write_is_idempotent_by_container_name(self):
        """Writing two entries with the same container key replaces, not appends."""
        e1 = {"container": "c1", "port": 4000}
        e2 = {"container": "c1", "port": 4001}
        registry.write_entry(e1)
        registry.write_entry(e2)
        got = registry.read_all()
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["port"], 4001)

    def test_write_multiple_containers(self):
        registry.write_entry({"container": "a", "port": 4000})
        registry.write_entry({"container": "b", "port": 4001})
        got = sorted(registry.read_all(), key=lambda e: e["container"])
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0]["container"], "a")
        self.assertEqual(got[1]["container"], "b")

    def test_remove_entry(self):
        registry.write_entry({"container": "a", "port": 4000})
        registry.write_entry({"container": "b", "port": 4001})
        registry.remove_entry("a")
        got = registry.read_all()
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["container"], "b")

    def test_remove_missing_is_noop(self):
        registry.remove_entry("does-not-exist")
        # Should not raise and file may or may not exist
        self.assertEqual(registry.read_all(), [])

    def test_write_requires_container_key(self):
        with self.assertRaises(ValueError):
            registry.write_entry({"project": "no-container-key"})

    def test_corrupt_file_reads_as_empty(self):
        """If peers.json is malformed, read_all returns [] rather than crashing."""
        path = registry.registry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json")
        self.assertEqual(registry.read_all(), [])

    def test_write_preserves_existing_when_read_corrupt(self):
        """Corrupt file should not prevent new writes (it gets overwritten)."""
        path = registry.registry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json")
        registry.write_entry({"container": "fresh", "port": 4000})
        got = registry.read_all()
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["container"], "fresh")

    def test_atomic_write_cleans_up_tmp(self):
        """No stray .tmp files after a successful write."""
        registry.write_entry({"container": "c1", "port": 4000})
        tmps = list(registry.registry_path().parent.glob("*.tmp"))
        self.assertEqual(tmps, [])


class TestPruneStale(unittest.TestCase):
    """prune_stale removes entries whose containers are no longer running."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._home_patch = mock.patch.dict(
            os.environ, {"HOME": str(self.home)}, clear=False
        )
        self._home_patch.start()
        self._stash_patch = mock.patch.object(
            registry, "_CONTAINER_STASH", Path("/nonexistent/stash")
        )
        self._stash_patch.start()

    def tearDown(self):
        self._stash_patch.stop()
        self._home_patch.stop()
        self.tmp.cleanup()

    def test_prune_removes_non_running(self):
        registry.write_entry({"container": "alive"})
        registry.write_entry({"container": "dead"})

        def is_running(name: str) -> bool:
            return name == "alive"

        pruned = registry.prune_stale(is_running=is_running)
        self.assertEqual(pruned, ["dead"])
        got = registry.read_all()
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["container"], "alive")

    def test_prune_with_all_alive_changes_nothing(self):
        registry.write_entry({"container": "a"})
        registry.write_entry({"container": "b"})
        pruned = registry.prune_stale(is_running=lambda _: True)
        self.assertEqual(pruned, [])
        self.assertEqual(len(registry.read_all()), 2)


class TestReadOnlyView(unittest.TestCase):
    """read_all returns copies, not references into internal state."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._home_patch = mock.patch.dict(
            os.environ, {"HOME": str(self.home)}, clear=False
        )
        self._home_patch.start()
        self._stash_patch = mock.patch.object(
            registry, "_CONTAINER_STASH", Path("/nonexistent/stash")
        )
        self._stash_patch.start()

    def tearDown(self):
        self._stash_patch.stop()
        self._home_patch.stop()
        self.tmp.cleanup()

    def test_mutation_of_returned_does_not_affect_disk(self):
        registry.write_entry({"container": "c1", "port": 4000})
        entries = registry.read_all()
        entries[0]["port"] = 9999
        reread = registry.read_all()
        self.assertEqual(reread[0]["port"], 4000)


class TestConcurrentWrites(unittest.TestCase):
    """flock serializes concurrent RMW cycles from separate processes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._home_patch = mock.patch.dict(
            os.environ, {"HOME": str(self.home)}, clear=False
        )
        self._home_patch.start()
        self._stash_patch = mock.patch.object(
            registry, "_CONTAINER_STASH", Path("/nonexistent/stash")
        )
        self._stash_patch.start()

    def tearDown(self):
        self._stash_patch.stop()
        self._home_patch.stop()
        self.tmp.cleanup()

    def test_parallel_writes_do_not_drop_entries(self):
        import threading

        def writer(tag: str):
            for i in range(20):
                registry.write_entry(
                    {"container": f"{tag}-{i}", "port": 4000 + i}
                )

        t1 = threading.Thread(target=writer, args=("a",))
        t2 = threading.Thread(target=writer, args=("b",))
        t3 = threading.Thread(target=writer, args=("c",))
        t1.start()
        t2.start()
        t3.start()
        t1.join()
        t2.join()
        t3.join()

        got = registry.read_all()
        names = {e["container"] for e in got}
        # All 60 unique entries should be present after parallel writes.
        self.assertEqual(len(names), 60)


class TestBuildEntry(unittest.TestCase):
    """Assembling a registry entry from running container metadata."""

    def test_minimal_fields(self):
        with mock.patch.object(registry, "_git_branch", return_value=None):
            e = registry.build_entry(
                container="c1",
                workspace=Path("/workspaces/demo"),
                port=None,
            )
        self.assertEqual(e["container"], "c1")
        self.assertEqual(e["project"], "demo")
        self.assertEqual(e["workspace"], "/workspaces/demo")
        self.assertIn("started_at", e)
        self.assertNotIn("port", e)
        self.assertNotIn("url", e)
        self.assertNotIn("branch", e)

    def test_all_fields(self):
        with mock.patch.object(registry, "_git_branch", return_value="main"):
            e = registry.build_entry(
                container="c1",
                workspace=Path("/workspaces/demo"),
                port=4123,
                host="host.tailnet.ts.net",
            )
        self.assertEqual(e["port"], 4123)
        self.assertEqual(e["branch"], "main")
        self.assertEqual(e["url"], "http://host.tailnet.ts.net:4123")

    def test_no_url_without_host(self):
        with mock.patch.object(registry, "_git_branch", return_value=None):
            e = registry.build_entry(
                container="c1",
                workspace=Path("/workspaces/demo"),
                port=4123,
            )
        self.assertNotIn("url", e)

    def test_started_at_is_iso8601_utc(self):
        with mock.patch.object(registry, "_git_branch", return_value=None):
            e = registry.build_entry(
                container="c1",
                workspace=Path("/workspaces/demo"),
                port=None,
            )
        # Should end with +00:00 (explicit UTC offset) and parse cleanly
        self.assertTrue(e["started_at"].endswith("+00:00"), e["started_at"])
        datetime.datetime.fromisoformat(e["started_at"])


if __name__ == "__main__":
    unittest.main()
