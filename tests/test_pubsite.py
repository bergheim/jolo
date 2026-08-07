#!/usr/bin/env python3
"""Tests for jolo publish / unpublish (public site commands)."""

import argparse
import unittest
from pathlib import Path
from unittest import mock

import jolo
from _jolo import pubsite


class TestArgs(unittest.TestCase):
    def test_publish_command(self):
        args = jolo.parse_args(["publish"])
        self.assertEqual(args.command, "publish")
        self.assertFalse(args.no_auth)
        self.assertFalse(args.rotate)

    def test_publish_flags(self):
        args = jolo.parse_args(["publish", "--no-auth", "--rotate"])
        self.assertTrue(args.no_auth)
        self.assertTrue(args.rotate)

    def test_unpublish_command(self):
        args = jolo.parse_args(["unpublish"])
        self.assertEqual(args.command, "unpublish")


class TestPassword(unittest.TestCase):
    def test_generated_passwords_differ(self):
        self.assertNotEqual(
            pubsite.generate_password(), pubsite.generate_password()
        )

    def test_hashing_passes_the_secret_on_stdin_not_argv(self):
        """A password in argv leaks to the process list and shell history."""
        completed = mock.Mock(returncode=0, stdout="$2a$14$hash\n", stderr="")
        with mock.patch("subprocess.run", return_value=completed) as run:
            self.assertEqual(pubsite.hash_password("hunter2"), "$2a$14$hash")

        cmd = run.call_args[0][0]
        self.assertNotIn("hunter2", " ".join(cmd))
        self.assertEqual(run.call_args[1]["input"], "hunter2")

    def test_hashing_exits_on_nonzero_returncode(self):
        completed = mock.Mock(returncode=1, stdout="", stderr="boom")
        with mock.patch("subprocess.run", return_value=completed):
            with self.assertRaises(SystemExit):
                pubsite.hash_password("hunter2")

    def test_hashing_exits_cleanly_when_caddy_is_missing(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            with self.assertRaises(SystemExit):
                pubsite.hash_password("hunter2")


def _args(**kw):
    defaults = {
        "no_auth": False,
        "rotate": False,
        "yes": False,
        "verbose": False,
    }
    defaults.update(kw)
    return argparse.Namespace(command="publish", **defaults)


class TestPublishMode(unittest.TestCase):
    def setUp(self):
        self.project = Path("/home/tsb/dev/test4k")
        self.patches = [
            mock.patch.object(
                pubsite, "pick_project", return_value=self.project
            ),
            mock.patch.object(
                pubsite, "read_port_from_devcontainer", return_value=4676
            ),
            mock.patch.object(
                pubsite.sites, "is_available", return_value=True
            ),
            mock.patch.object(pubsite.sites, "read_public", return_value={}),
            mock.patch.object(
                pubsite.sites, "owner_of", return_value=self.project
            ),
            mock.patch.object(
                pubsite, "hash_password", return_value="$2a$14$h"
            ),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_publishes_with_auth_by_default(self):
        with mock.patch.object(
            pubsite.sites, "register_public", return_value="https://x"
        ) as reg:
            pubsite.run_publish_mode(_args())

        reg.assert_called_once_with("test4k", 4676, "$2a$14$h")

    def test_no_auth_requires_typed_confirmation(self):
        with mock.patch("builtins.input", return_value="no"):
            with mock.patch.object(pubsite.sites, "register_public") as reg:
                with self.assertRaises(SystemExit):
                    pubsite.run_publish_mode(_args(no_auth=True))

        reg.assert_not_called()

    def test_no_auth_proceeds_on_yes(self):
        with mock.patch("builtins.input", return_value="YES"):
            with mock.patch.object(
                pubsite.sites, "register_public", return_value="https://x"
            ) as reg:
                pubsite.run_publish_mode(_args(no_auth=True))

        reg.assert_called_once_with("test4k", 4676, None)

    def test_refuses_when_another_workspace_owns_the_name(self):
        with mock.patch.object(
            pubsite.sites, "owner_of", return_value=Path("/elsewhere/test4k")
        ):
            with mock.patch.object(pubsite.sites, "register_public") as reg:
                with self.assertRaises(SystemExit):
                    pubsite.run_publish_mode(_args())

        reg.assert_not_called()

    def test_republish_keeps_the_existing_hash(self):
        existing = {"test4k.pub.glvortex.net": (4100, "$2a$14$old")}
        with mock.patch.object(
            pubsite.sites, "read_public", return_value=existing
        ):
            with mock.patch.object(
                pubsite.sites, "register_public", return_value="https://x"
            ) as reg:
                pubsite.run_publish_mode(_args())

        reg.assert_called_once_with("test4k", 4676, "$2a$14$old")

    def test_rotate_replaces_the_hash(self):
        existing = {"test4k.pub.glvortex.net": (4100, "$2a$14$old")}
        with mock.patch.object(
            pubsite.sites, "read_public", return_value=existing
        ):
            with mock.patch.object(
                pubsite.sites, "register_public", return_value="https://x"
            ) as reg:
                pubsite.run_publish_mode(_args(rotate=True))

        reg.assert_called_once_with("test4k", 4676, "$2a$14$h")

    def test_exits_when_the_host_has_no_control_plane(self):
        with mock.patch.object(
            pubsite.sites, "is_available", return_value=False
        ):
            with self.assertRaises(SystemExit):
                pubsite.run_publish_mode(_args())


class TestUnpublishMode(unittest.TestCase):
    def test_unpublishes_the_current_project(self):
        project = Path("/home/tsb/dev/test4k")
        with mock.patch.object(
            pubsite.sites, "is_available", return_value=True
        ):
            with mock.patch.object(
                pubsite, "pick_project", return_value=project
            ):
                with mock.patch.object(
                    pubsite.sites, "unregister_public", return_value=True
                ) as unreg_pub:
                    with mock.patch.object(
                        pubsite.sites, "unregister"
                    ) as unreg:
                        pubsite.run_unpublish_mode(
                            argparse.Namespace(verbose=False)
                        )

        unreg_pub.assert_called_once_with("test4k")
        unreg.assert_not_called()

    def test_exits_when_the_host_has_no_control_plane(self):
        """A host outside the Syncthing share must not claim a project is
        unpublished when it has no visibility into the public fragment at
        all — it could be published elsewhere."""
        with mock.patch.object(
            pubsite.sites, "is_available", return_value=False
        ):
            with mock.patch.object(pubsite, "pick_project") as pick:
                with self.assertRaises(SystemExit):
                    pubsite.run_unpublish_mode(
                        argparse.Namespace(verbose=False)
                    )

        pick.assert_not_called()


if __name__ == "__main__":
    unittest.main()
