#!/usr/bin/env python3
"""Tests for jolo preview / publish (public site commands)."""

import argparse
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import jolo
from _jolo import pubsite


class TestArgs(unittest.TestCase):
    def test_preview_command(self):
        args = jolo.parse_args(["preview"])
        self.assertEqual(args.command, "preview")
        self.assertFalse(args.no_auth)
        self.assertFalse(args.rotate)

    def test_preview_flags(self):
        args = jolo.parse_args(["preview", "--no-auth", "--rotate"])
        self.assertTrue(args.no_auth)
        self.assertTrue(args.rotate)

    def test_unpreview_command(self):
        args = jolo.parse_args(["unpreview"])
        self.assertEqual(args.command, "unpreview")

    def test_publish_command(self):
        args = jolo.parse_args(["publish"])
        self.assertEqual(args.command, "publish")
        self.assertFalse(args.list)

    def test_unpublish_command(self):
        args = jolo.parse_args(["unpublish"])
        self.assertEqual(args.command, "unpublish")


class TestPassword(unittest.TestCase):
    def test_generated_passwords_differ(self):
        # Only 100 combinations, so two draws collide 1% of the time.
        self.assertGreater(
            len({pubsite.generate_password() for _ in range(50)}), 1
        )

    def test_password_is_two_words(self):
        """Typeable over the phone, from jolo's existing word lists."""
        from _jolo import constants

        adjective, noun = pubsite.generate_password().split("-")

        self.assertIn(adjective, constants.ADJECTIVES)
        self.assertIn(noun, constants.NOUNS)

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
    return argparse.Namespace(command="preview", **defaults)


class TestPreviewMode(unittest.TestCase):
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
            mock.patch.object(pubsite.sites, "read_previews", return_value={}),
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

    def test_previews_with_auth_by_default(self):
        with mock.patch.object(
            pubsite.sites, "register_preview", return_value="https://x"
        ) as reg:
            pubsite.run_preview_mode(_args())

        reg.assert_called_once_with("test4k", 4676, "$2a$14$h")

    def test_copies_the_preview_url_to_the_clipboard(self):
        with mock.patch.object(
            pubsite.sites, "register_preview", return_value="https://x"
        ):
            with mock.patch.object(pubsite, "clipboard_copy") as copy:
                pubsite.run_preview_mode(_args())

        copy.assert_called_once_with("https://x")

    def test_no_auth_requires_typed_confirmation(self):
        with mock.patch("builtins.input", return_value="no"):
            with mock.patch.object(pubsite.sites, "register_preview") as reg:
                with self.assertRaises(SystemExit):
                    pubsite.run_preview_mode(_args(no_auth=True))

        reg.assert_not_called()

    def test_no_auth_proceeds_on_yes(self):
        with mock.patch("builtins.input", return_value="y"):
            with mock.patch.object(
                pubsite.sites, "register_preview", return_value="https://x"
            ) as reg:
                pubsite.run_preview_mode(_args(no_auth=True))

        reg.assert_called_once_with("test4k", 4676, None)

    def test_refuses_when_another_workspace_owns_the_name(self):
        with mock.patch.object(
            pubsite.sites, "owner_of", return_value=Path("/elsewhere/test4k")
        ):
            with mock.patch.object(pubsite.sites, "register_preview") as reg:
                with self.assertRaises(SystemExit):
                    pubsite.run_preview_mode(_args())

        reg.assert_not_called()

    def test_repreview_keeps_the_existing_hash(self):
        existing = {"test4k.dev.glvortex.net": (4100, "$2a$14$old")}
        with mock.patch.object(
            pubsite.sites, "read_previews", return_value=existing
        ):
            with mock.patch.object(
                pubsite.sites, "register_preview", return_value="https://x"
            ) as reg:
                pubsite.run_preview_mode(_args())

        reg.assert_called_once_with("test4k", 4676, "$2a$14$old")

    def test_rotate_replaces_the_hash(self):
        existing = {"test4k.dev.glvortex.net": (4100, "$2a$14$old")}
        with mock.patch.object(
            pubsite.sites, "read_previews", return_value=existing
        ):
            with mock.patch.object(
                pubsite.sites, "register_preview", return_value="https://x"
            ) as reg:
                pubsite.run_preview_mode(_args(rotate=True))

        reg.assert_called_once_with("test4k", 4676, "$2a$14$h")

    def test_exits_when_the_host_has_no_control_plane(self):
        with mock.patch.object(
            pubsite.sites, "is_available", return_value=False
        ):
            with self.assertRaises(SystemExit):
                pubsite.run_preview_mode(_args())


class TestUnpreviewMode(unittest.TestCase):
    TWO = {
        "foo.dev.glvortex.net": (4676, None),
        "bar.dev.glvortex.net": (4100, None),
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
        """Run unpreview; exposes self.unreg and self.picker for assertions."""
        self._patch(pubsite.sites, "read_previews", routes)
        self._patch(pubsite, "find_git_root", git_root)
        self.picker = self._patch(pubsite, "_fzf_pick", pick)
        self.unreg = self._patch(pubsite.sites, "unregister_preview", True)
        with mock.patch("sys.stdout", new=io.StringIO()) as out:
            pubsite.run_unpreview_mode(argparse.Namespace(verbose=False))
        return out.getvalue()

    def test_unpreviews_the_current_project(self):
        project = Path("/home/tsb/dev/test4k")
        self._run({"test4k.dev.glvortex.net": (4676, None)}, git_root=project)

        self.unreg.assert_called_once_with("test4k")
        self.picker.assert_not_called()

    def test_does_not_run_full_teardown(self):
        """unregister clears the private tailnet route too; unpreview must not."""
        with mock.patch.object(pubsite.sites, "unregister") as full:
            self._run(
                {"test4k.dev.glvortex.net": (4676, None)},
                git_root=Path("/home/tsb/dev/test4k"),
            )

        full.assert_not_called()

    def test_skips_the_picker_for_a_single_previewed_site(self):
        self._run({"foo.dev.glvortex.net": (4676, None)})

        self.unreg.assert_called_once_with("foo")
        self.picker.assert_not_called()

    def test_picker_offers_only_previewed_sites(self):
        """The generic project picker lists everything jolo knows; noise here."""
        label = f"{'bar':<24} bar.dev.glvortex.net"
        self._run(self.TWO, pick=label)

        labels = self.picker.call_args[0][1]
        self.assertEqual(len(labels), 2)
        for offered in labels:
            self.assertIn(".dev.glvortex.net", offered)
        self.unreg.assert_called_once_with("bar")

    def test_says_so_when_nothing_is_previewed(self):
        output = self._run({})

        self.assertIn("No previews", output)
        self.unreg.assert_not_called()

    def test_exits_when_the_host_has_no_control_plane(self):
        """A host outside the Syncthing share must not claim a project is
        unpreviewed when it has no visibility into the dev fragment at
        all — it could be previewed elsewhere."""
        with mock.patch.object(
            pubsite.sites, "is_available", return_value=False
        ):
            with mock.patch.object(pubsite.sites, "read_previews") as read:
                with self.assertRaises(SystemExit):
                    pubsite.run_unpreview_mode(
                        argparse.Namespace(verbose=False)
                    )

        read.assert_not_called()


class TestListPreviews(unittest.TestCase):
    ROUTES = {
        "foo.dev.glvortex.net": (4676, "$2a$14$h"),
        "demo.dev.glvortex.net": (4100, None),
    }

    def _run(self, routes, owner, running=True):
        with mock.patch.object(
            pubsite.sites, "is_available", return_value=True
        ):
            with mock.patch.object(
                pubsite.sites, "read_previews", return_value=routes
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
                            pubsite.run_list_previews_mode()
        return out.getvalue()

    def test_lists_host_port_and_auth_state(self):
        output = self._run(self.ROUTES, Path("/dev/foo"))

        self.assertIn("foo.dev.glvortex.net", output)
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
        """A previewed site whose project directory is gone still lists."""
        self.assertIn("unknown", self._run(self.ROUTES, None))

    def test_says_so_when_nothing_is_previewed(self):
        self.assertIn("No previews", self._run({}, None))

    def test_list_flag_does_not_preview(self):
        with mock.patch.object(pubsite, "run_list_previews_mode") as lister:
            with mock.patch.object(pubsite.sites, "register_preview") as reg:
                pubsite.run_preview_mode(_args(list=True))

        lister.assert_called_once()
        reg.assert_not_called()


def _pub_args(**kw):
    defaults = {"list": False, "verbose": False}
    defaults.update(kw)
    return argparse.Namespace(command="publish", **defaults)


class TestPublishMode(unittest.TestCase):
    """Static release: build in the container, rsync dist/ to the host."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / "test4k"
        (self.project / "dist").mkdir(parents=True)
        (self.project / "dist" / "index.html").write_text("hi")
        self.patches = [
            mock.patch.object(
                pubsite, "pick_project", return_value=self.project
            ),
            mock.patch.object(
                pubsite.sites, "is_available", return_value=True
            ),
            mock.patch.object(
                pubsite.sites, "owner_of", return_value=self.project
            ),
            mock.patch.object(pubsite, "_build_in_container"),
            mock.patch.object(pubsite, "clipboard_copy"),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_rsyncs_dist_to_the_publish_host(self):
        completed = mock.Mock(returncode=0)
        with mock.patch.object(
            pubsite.subprocess, "run", return_value=completed
        ) as run:
            pubsite.run_publish_mode(_pub_args())

        self.assertEqual(
            run.call_args[0][0],
            [
                "rsync",
                "-a",
                "--delete",
                f"{self.project}/dist/",
                "burial:/srv/www/test4k.pub.glvortex.net/",
            ],
        )

    def test_honors_the_jolo_toml_name_override(self):
        """A dotted directory name publishes under its .jolo.toml name."""
        (self.project / ".jolo.toml").write_text('name = "glvortex"\n')
        with mock.patch.object(
            pubsite.sites, "owner_of", return_value=self.project
        ):
            completed = mock.Mock(returncode=0)
            with mock.patch.object(
                pubsite.subprocess, "run", return_value=completed
            ) as run:
                pubsite.run_publish_mode(_pub_args())

        self.assertEqual(
            run.call_args[0][0][-1],
            "burial:/srv/www/glvortex.pub.glvortex.net/",
        )

    def test_exits_when_the_build_leaves_no_dist(self):
        (self.project / "dist" / "index.html").unlink()
        (self.project / "dist").rmdir()
        with mock.patch.object(pubsite.subprocess, "run") as run:
            with self.assertRaises(SystemExit):
                pubsite.run_publish_mode(_pub_args())

        run.assert_not_called()

    def test_exits_when_rsync_fails(self):
        completed = mock.Mock(returncode=1)
        with mock.patch.object(
            pubsite.subprocess, "run", return_value=completed
        ):
            with self.assertRaises(SystemExit):
                pubsite.run_publish_mode(_pub_args())

    def test_refuses_when_another_workspace_owns_the_name(self):
        with mock.patch.object(
            pubsite.sites, "owner_of", return_value=Path("/elsewhere/test4k")
        ):
            with mock.patch.object(pubsite.subprocess, "run") as run:
                with self.assertRaises(SystemExit):
                    pubsite.run_publish_mode(_pub_args())

        run.assert_not_called()

    def test_rejects_names_that_sanitize_to_nothing(self):
        bad = Path(self.tmp.name) / "___"
        bad.mkdir()
        with mock.patch.object(pubsite, "pick_project", return_value=bad):
            with mock.patch.object(pubsite.subprocess, "run") as run:
                with self.assertRaises(SystemExit):
                    pubsite.run_publish_mode(_pub_args())

        run.assert_not_called()

    def test_exits_when_the_host_has_no_control_plane(self):
        with mock.patch.object(
            pubsite.sites, "is_available", return_value=False
        ):
            with self.assertRaises(SystemExit):
                pubsite.run_publish_mode(_pub_args())

    def test_list_flag_does_not_publish(self):
        with mock.patch.object(pubsite, "run_list_released_mode") as lister:
            with mock.patch.object(pubsite.subprocess, "run") as run:
                pubsite.run_publish_mode(_pub_args(list=True))

        lister.assert_called_once()
        run.assert_not_called()


class TestBuildInContainer(unittest.TestCase):
    def setUp(self):
        self.project = Path("/home/tsb/dev/test4k")
        for target, attr, value in [
            (pubsite, "get_container_runtime", "podman"),
            (pubsite, "get_container_for_workspace", "test4k"),
            (pubsite, "is_container_running", True),
        ]:
            patcher = mock.patch.object(target, attr, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_runs_just_publish_in_the_project_workspace(self):
        completed = mock.Mock(returncode=0)
        with mock.patch.object(
            pubsite.subprocess, "run", return_value=completed
        ) as run:
            pubsite._build_in_container(self.project)

        cmd = run.call_args[0][0]
        self.assertEqual(cmd[0], "podman")
        self.assertEqual(cmd[1], "exec")
        self.assertIn("-w", cmd)
        self.assertIn("/workspaces/test4k", cmd)
        self.assertEqual(cmd[-2:], ["just", "publish"])

    def test_exits_when_the_build_fails(self):
        completed = mock.Mock(returncode=1)
        with mock.patch.object(
            pubsite.subprocess, "run", return_value=completed
        ):
            with self.assertRaises(SystemExit):
                pubsite._build_in_container(self.project)

    def test_exits_without_a_running_container(self):
        with mock.patch.object(
            pubsite, "is_container_running", return_value=False
        ):
            with mock.patch.object(pubsite.subprocess, "run") as run:
                with self.assertRaises(SystemExit):
                    pubsite._build_in_container(self.project)

        run.assert_not_called()


class TestReleasedSites(unittest.TestCase):
    LS = "test4k.pub.glvortex.net\nlost+found\ndemo.pub.glvortex.net\n"

    def _ls(self, stdout, returncode=0):
        return mock.Mock(returncode=returncode, stdout=stdout, stderr="")

    def test_lists_only_release_dirs(self):
        with mock.patch.object(
            pubsite.subprocess, "run", return_value=self._ls(self.LS)
        ) as run:
            with mock.patch("sys.stdout", new=io.StringIO()) as out:
                pubsite.run_list_released_mode()

        self.assertEqual(
            run.call_args[0][0], ["ssh", "burial", "ls", "-1", "/srv/www"]
        )
        self.assertIn("https://test4k.pub.glvortex.net", out.getvalue())
        self.assertIn("https://demo.pub.glvortex.net", out.getvalue())
        self.assertNotIn("lost+found", out.getvalue())

    def test_says_so_when_nothing_is_released(self):
        with mock.patch.object(
            pubsite.subprocess, "run", return_value=self._ls("")
        ):
            with mock.patch("sys.stdout", new=io.StringIO()) as out:
                pubsite.run_list_released_mode()

        self.assertIn("Nothing published", out.getvalue())

    def test_exits_when_ssh_fails(self):
        with mock.patch.object(
            pubsite.subprocess, "run", return_value=self._ls("", 255)
        ):
            with self.assertRaises(SystemExit):
                pubsite.run_list_released_mode()


class TestUnpublishMode(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(
            pubsite.sites, "is_available", return_value=True
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, returncode):
        completed = mock.Mock(returncode=returncode)
        with mock.patch.object(
            pubsite, "find_git_root", return_value=Path("/dev/test4k")
        ):
            with mock.patch.object(
                pubsite.subprocess, "run", return_value=completed
            ) as run:
                with mock.patch("sys.stdout", new=io.StringIO()) as out:
                    pubsite.run_unpublish_mode(
                        argparse.Namespace(verbose=False)
                    )
        self.cmd = run.call_args[0][0]
        return out.getvalue()

    def test_removes_the_exact_release_dir(self):
        output = self._run(0)

        self.assertEqual(self.cmd[:2], ["ssh", "burial"])
        self.assertIn(
            "test -d /srv/www/test4k.pub.glvortex.net "
            "&& rm -rf /srv/www/test4k.pub.glvortex.net",
            self.cmd[2],
        )
        self.assertIn("Unpublished: test4k.pub.glvortex.net", output)

    def test_reports_when_nothing_was_released(self):
        self.assertIn("Not published", self._run(1))

    def test_exits_when_ssh_fails(self):
        with self.assertRaises(SystemExit):
            self._run(255)

    def test_exits_when_the_host_has_no_control_plane(self):
        with mock.patch.object(
            pubsite.sites, "is_available", return_value=False
        ):
            with mock.patch.object(pubsite.subprocess, "run") as run:
                with self.assertRaises(SystemExit):
                    pubsite.run_unpublish_mode(
                        argparse.Namespace(verbose=False)
                    )

        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
