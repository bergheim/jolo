#!/usr/bin/env python3
"""Tests for jolo publish / unpublish (public site commands)."""

import argparse
import io
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

    def test_password_is_two_words_and_four_digits(self):
        """Typeable over the phone, from jolo's existing word lists."""
        from _jolo import constants

        adjective, noun, digits = pubsite.generate_password().split("-")

        self.assertIn(adjective, constants.ADJECTIVES)
        self.assertIn(noun, constants.NOUNS)
        self.assertRegex(digits, r"^[1-9]\d{3}$")

    def test_hashing_passes_the_secret_on_stdin_not_argv(self):
        """A password in argv leaks to the process list and shell history."""
        completed = mock.Mock(returncode=0, stdout="$2a$14$hash\n", stderr="")
        with mock.patch("subprocess.run", return_value=completed) as run:
            self.assertEqual(pubsite.hash_password("hunter2"), "$2a$14$hash")

        cmd = run.call_args[0][0]
        self.assertNotIn("hunter2", " ".join(cmd))
        # Newline-terminated: caddy reads one line and errors "EOF" without it.
        self.assertEqual(run.call_args[1]["input"], "hunter2\n")

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
        "list": False,
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
    TWO = {
        "foo.pub.glvortex.net": (4676, None),
        "bar.pub.glvortex.net": (4100, None),
    }

    def setUp(self):
        patcher = mock.patch.object(
            pubsite.sites, "is_available", return_value=True
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _patch(self, target, attr, value):
        patcher = mock.patch.object(target, attr, return_value=value)
        started = patcher.start()
        self.addCleanup(patcher.stop)
        return started

    def _run(self, routes, git_root=None, pick=None):
        """Run unpublish; exposes self.unreg and self.picker for assertions."""
        self._patch(pubsite.sites, "read_public", routes)
        self._patch(pubsite, "find_git_root", git_root)
        self.picker = self._patch(pubsite, "_fzf_pick", pick)
        self.unreg = self._patch(pubsite.sites, "unregister_public", True)
        with mock.patch("sys.stdout", new=io.StringIO()) as out:
            pubsite.run_unpublish_mode(argparse.Namespace(verbose=False))
        return out.getvalue()

    def test_unpublishes_the_current_project(self):
        project = Path("/home/tsb/dev/test4k")
        self._run({"test4k.pub.glvortex.net": (4676, None)}, git_root=project)

        self.unreg.assert_called_once_with("test4k")
        self.picker.assert_not_called()

    def test_does_not_run_full_teardown(self):
        """unregister clears the private tailnet route too; unpublish must not."""
        with mock.patch.object(pubsite.sites, "unregister") as full:
            self._run(
                {"test4k.pub.glvortex.net": (4676, None)},
                git_root=Path("/home/tsb/dev/test4k"),
            )

        full.assert_not_called()

    def test_skips_the_picker_for_a_single_published_site(self):
        self._run({"foo.pub.glvortex.net": (4676, None)})

        self.unreg.assert_called_once_with("foo")
        self.picker.assert_not_called()

    def test_picker_offers_only_published_sites(self):
        """The generic project picker lists everything jolo knows; noise here."""
        label = f"{'bar':<24} bar.pub.glvortex.net"
        self._run(self.TWO, pick=label)

        labels = self.picker.call_args[0][1]
        self.assertEqual(len(labels), 2)
        for offered in labels:
            self.assertIn(".pub.glvortex.net", offered)
        self.unreg.assert_called_once_with("bar")

    def test_says_so_when_nothing_is_published(self):
        output = self._run({})

        self.assertIn("Nothing published", output)
        self.unreg.assert_not_called()

    def test_exits_when_the_host_has_no_control_plane(self):
        """A host outside the Syncthing share must not claim a project is
        unpublished when it has no visibility into the public fragment at
        all — it could be published elsewhere."""
        with mock.patch.object(
            pubsite.sites, "is_available", return_value=False
        ):
            with mock.patch.object(pubsite.sites, "read_public") as read:
                with self.assertRaises(SystemExit):
                    pubsite.run_unpublish_mode(
                        argparse.Namespace(verbose=False)
                    )

        read.assert_not_called()


class TestListPublished(unittest.TestCase):
    ROUTES = {
        "foo.pub.glvortex.net": (4676, "$2a$14$h"),
        "demo.pub.glvortex.net": (4100, None),
    }

    def _run(self, routes, owner, running=True):
        with mock.patch.object(
            pubsite.sites, "is_available", return_value=True
        ):
            with mock.patch.object(
                pubsite.sites, "read_public", return_value=routes
            ):
                with mock.patch.object(
                    pubsite.sites, "owner_of", return_value=owner
                ):
                    with mock.patch.object(
                        pubsite, "is_container_running", return_value=running
                    ):
                        with mock.patch(
                            "sys.stdout", new=io.StringIO()
                        ) as out:
                            pubsite.run_list_published_mode()
        return out.getvalue()

    def test_lists_host_port_and_auth_state(self):
        output = self._run(self.ROUTES, Path("/dev/foo"))

        self.assertIn("foo.pub.glvortex.net", output)
        self.assertIn("4676", output)
        self.assertIn("auth", output)
        self.assertIn("NO AUTH", output)

    def test_reports_container_state(self):
        self.assertIn(
            "stopped", self._run(self.ROUTES, Path("/dev/foo"), False)
        )
        self.assertIn(
            "running", self._run(self.ROUTES, Path("/dev/foo"), True)
        )

    def test_unknown_when_no_workspace_owns_the_name(self):
        """A published site whose project directory is gone still lists."""
        self.assertIn("unknown", self._run(self.ROUTES, None))

    def test_says_so_when_nothing_is_published(self):
        self.assertIn("Nothing published", self._run({}, None))

    def test_list_flag_does_not_publish(self):
        with mock.patch.object(pubsite, "run_list_published_mode") as lister:
            with mock.patch.object(pubsite.sites, "register_public") as reg:
                pubsite.run_publish_mode(_args(list=True))

        lister.assert_called_once()
        reg.assert_not_called()


if __name__ == "__main__":
    unittest.main()
