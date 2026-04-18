#!/usr/bin/env python3
"""Tests for `jolo autonomous` — TODO-driven task dispatcher."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import jolo
    from _jolo import autonomous
except ImportError:
    jolo = None
    autonomous = None


class TestAutonomousArgParsing(unittest.TestCase):
    """CLI argument parsing for the `autonomous` subcommand."""

    def test_bare_command(self):
        args = jolo.parse_args(["autonomous"])
        self.assertEqual(args.command, "autonomous")
        self.assertFalse(args.dry_run)

    def test_dry_run(self):
        args = jolo.parse_args(["autonomous", "--dry-run"])
        self.assertTrue(args.dry_run)

    def test_agents_flag(self):
        args = jolo.parse_args(
            ["autonomous", "--agents", "claude,codex,gemini"]
        )
        self.assertEqual(args.agents, "claude,codex,gemini")

    def test_org_file_flag(self):
        args = jolo.parse_args(["autonomous", "--org-file", "other.org"])
        self.assertEqual(args.org_file, "other.org")

    def test_org_file_default(self):
        args = jolo.parse_args(["autonomous"])
        self.assertEqual(args.org_file, "docs/TODO.org")


class TestEmacsclientJSONParsing(unittest.TestCase):
    """Parsing the emacsclient `-e` response (lisp-escaped JSON string)."""

    def test_parse_empty_list(self):
        # emacsclient wraps strings in double quotes; JSON `[]` round-trips as "[]"
        raw = '"[]"\n'
        self.assertEqual(autonomous.parse_emacsclient_json(raw), [])

    def test_parse_single_item(self):
        # elisp escapes inner quotes as \"; simulate that:
        raw = (
            r'"[{\"heading\":\"Do the thing\",\"body\":\"Write tests.\"}]"'
            + "\n"
        )
        result = autonomous.parse_emacsclient_json(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["heading"], "Do the thing")
        self.assertEqual(result[0]["body"], "Write tests.")

    def test_parse_nil_result(self):
        # If the elisp function returns nil, emacsclient prints `nil`
        self.assertEqual(autonomous.parse_emacsclient_json("nil\n"), [])

    def test_parse_json_null(self):
        # Older elisp (json-encode on an empty list) produced "null"
        # instead of "[]"; parser must tolerate that.
        self.assertEqual(autonomous.parse_emacsclient_json('"null"\n'), [])

    def test_parse_embedded_newlines(self):
        # emacsclient prints the lisp-escaped JSON string; a JSON `\n` escape
        # appears in the lisp form as `\\n` (backslash-backslash-n).
        raw = r'"[{\"heading\":\"H\",\"body\":\"line1\\nline2\"}]"' + "\n"
        result = autonomous.parse_emacsclient_json(raw)
        self.assertEqual(result[0]["body"], "line1\nline2")


class TestBuildSlug(unittest.TestCase):
    """Slug generation for worktree names derived from headings."""

    def test_strips_todo_keyword(self):
        self.assertEqual(
            autonomous.build_slug("TODO Use scoped GitHub tokens"),
            "autonomous-use-scoped-github-tokens",
        )

    def test_strips_next_keyword(self):
        self.assertEqual(
            autonomous.build_slug("NEXT Refactor dispatch"),
            "autonomous-refactor-dispatch",
        )

    def test_no_keyword(self):
        self.assertEqual(
            autonomous.build_slug("Investigate egress monitoring"),
            "autonomous-investigate-egress-monitoring",
        )

    def test_truncates_long_heading(self):
        heading = "TODO " + "word " * 30
        slug = autonomous.build_slug(heading)
        # 11 ("autonomous-") + 50 cap from slugify_prompt
        self.assertLessEqual(len(slug), 11 + 50)
        self.assertTrue(slug.startswith("autonomous-"))


class TestRoundRobinAssignment(unittest.TestCase):
    """Round-robin agent assignment."""

    def test_single_agent(self):
        items = [{"heading": "a"}, {"heading": "b"}, {"heading": "c"}]
        pairs = autonomous.assign_agents(items, ["claude"])
        self.assertEqual([p[1] for p in pairs], ["claude", "claude", "claude"])

    def test_multiple_agents_cycle(self):
        items = [{"heading": "a"}, {"heading": "b"}, {"heading": "c"}]
        pairs = autonomous.assign_agents(items, ["claude", "codex"])
        self.assertEqual([p[1] for p in pairs], ["claude", "codex", "claude"])

    def test_empty_items(self):
        self.assertEqual(autonomous.assign_agents([], ["claude"]), [])

    def test_empty_agents_raises(self):
        with self.assertRaises(ValueError):
            autonomous.assign_agents([{"heading": "a"}], [])


class TestResolveAgents(unittest.TestCase):
    """Agents flag takes precedence over config default."""

    def test_flag_wins(self):
        self.assertEqual(
            autonomous.resolve_agents(
                flag="codex,gemini", config_default=["claude"]
            ),
            ["codex", "gemini"],
        )

    def test_falls_back_to_config(self):
        self.assertEqual(
            autonomous.resolve_agents(
                flag=None, config_default=["claude", "pi"]
            ),
            ["claude", "pi"],
        )

    def test_strips_whitespace(self):
        self.assertEqual(
            autonomous.resolve_agents(
                flag=" claude , codex ", config_default=["pi"]
            ),
            ["claude", "codex"],
        )

    def test_rejects_empty_list(self):
        with self.assertRaises(ValueError):
            autonomous.resolve_agents(flag="", config_default=[])


class TestGetAutonomousItems(unittest.TestCase):
    """Emacsclient-backed selection returns parsed items."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.tmpdir)
        (Path(self.tmpdir) / "docs").mkdir()
        (Path(self.tmpdir) / "docs" / "TODO.org").write_text("* TODO x\n")

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_invokes_emacsclient_with_select_function(self):
        with mock.patch("_jolo.autonomous.subprocess.run") as mock_run:
            mock_run.return_value.stdout = '"[]"'
            mock_run.return_value.returncode = 0
            autonomous.get_autonomous_items(Path("docs/TODO.org"))
            # Verify emacsclient was called with -e and the right elisp
            args = mock_run.call_args[0][0]
            self.assertEqual(args[0], "emacsclient")
            self.assertIn("-e", args)
            elisp = args[args.index("-e") + 1]
            self.assertIn("bergheim/agent-org-autonomous-select", elisp)

    def test_missing_file_returns_empty(self):
        # If the file isn't present, don't even shell out — return []
        with mock.patch("_jolo.autonomous.subprocess.run") as mock_run:
            (Path(self.tmpdir) / "docs" / "TODO.org").unlink()
            result = autonomous.get_autonomous_items(Path("docs/TODO.org"))
            self.assertEqual(result, [])
            mock_run.assert_not_called()


class TestMarkDispatched(unittest.TestCase):
    """Emacsclient-backed property setter."""

    def test_invokes_mark_function(self):
        # Elisp returns headings with the TODO keyword stripped, so
        # mark_dispatched sees the clean title.
        with mock.patch("_jolo.autonomous.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            autonomous.mark_dispatched(
                Path("docs/TODO.org"),
                "Use scoped GitHub tokens",
                "2026-04-18T12:00:00Z",
            )
            args = mock_run.call_args[0][0]
            self.assertEqual(args[0], "emacsclient")
            self.assertIn("-e", args)
            elisp = args[args.index("-e") + 1]
            self.assertIn(
                "bergheim/agent-org-autonomous-mark-dispatched", elisp
            )
            self.assertIn("2026-04-18T12:00:00Z", elisp)
            self.assertIn("Use scoped GitHub tokens", elisp)


class TestDispatchItem(unittest.TestCase):
    """Shelling out to `jolo tree` with the right args."""

    def test_invokes_jolo_tree_detached_with_prompt(self):
        with mock.patch("_jolo.autonomous.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            autonomous.dispatch_item(
                slug="autonomous-x",
                prompt="do the thing",
                agent="claude",
            )
            args = mock_run.call_args[0][0]
            self.assertEqual(args[0], "jolo")
            self.assertEqual(args[1], "tree")
            self.assertEqual(args[2], "autonomous-x")
            self.assertIn("-p", args)
            self.assertIn("do the thing", args)
            self.assertIn("--agent", args)
            self.assertIn("claude", args)

    def test_returns_true_on_success(self):
        with mock.patch("_jolo.autonomous.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            self.assertTrue(
                autonomous.dispatch_item(slug="x", prompt="y", agent="claude")
            )

    def test_returns_false_on_failure(self):
        with mock.patch("_jolo.autonomous.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            self.assertFalse(
                autonomous.dispatch_item(slug="x", prompt="y", agent="claude")
            )


class TestRunAutonomousIntegration(unittest.TestCase):
    """End-to-end orchestrator (mocked emacsclient + subprocess)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.tmpdir)
        (Path(self.tmpdir) / ".git").mkdir()
        (Path(self.tmpdir) / "docs").mkdir()
        (Path(self.tmpdir) / "docs" / "TODO.org").write_text("* TODO x\n")

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

    def _make_args(self, **overrides):
        import argparse

        ns = argparse.Namespace(
            command="autonomous",
            dry_run=False,
            agents=None,
            org_file="docs/TODO.org",
            verbose=False,
        )
        for k, v in overrides.items():
            setattr(ns, k, v)
        return ns

    def test_dry_run_does_not_dispatch_or_mark(self):
        fake_items = [
            {"heading": "TODO Do A", "body": "body A"},
            {"heading": "TODO Do B", "body": "body B"},
        ]
        with (
            mock.patch(
                "_jolo.autonomous.get_autonomous_items",
                return_value=fake_items,
            ),
            mock.patch("_jolo.autonomous.mark_dispatched") as mark,
            mock.patch("_jolo.autonomous.dispatch_item") as dispatch,
        ):
            autonomous.run_autonomous(self._make_args(dry_run=True))
            mark.assert_not_called()
            dispatch.assert_not_called()

    def test_real_run_marks_and_dispatches(self):
        fake_items = [
            {"heading": "TODO Do A", "body": "body A"},
            {"heading": "TODO Do B", "body": "body B"},
        ]
        with (
            mock.patch(
                "_jolo.autonomous.get_autonomous_items",
                return_value=fake_items,
            ),
            mock.patch("_jolo.autonomous.mark_dispatched") as mark,
            mock.patch("_jolo.autonomous.dispatch_item") as dispatch,
        ):
            autonomous.run_autonomous(self._make_args(agents="claude,codex"))
            self.assertEqual(mark.call_count, 2)
            self.assertEqual(dispatch.call_count, 2)
            # Round-robin: first claude, second codex
            self.assertEqual(
                dispatch.call_args_list[0].kwargs["agent"], "claude"
            )
            self.assertEqual(
                dispatch.call_args_list[1].kwargs["agent"], "codex"
            )

    def test_no_items_is_noop(self):
        with (
            mock.patch(
                "_jolo.autonomous.get_autonomous_items",
                return_value=[],
            ),
            mock.patch("_jolo.autonomous.mark_dispatched") as mark,
            mock.patch("_jolo.autonomous.dispatch_item") as dispatch,
        ):
            autonomous.run_autonomous(self._make_args())
            mark.assert_not_called()
            dispatch.assert_not_called()

    def test_failed_dispatch_does_not_mark(self):
        """If `jolo tree` exits non-zero, don't mark — let the next run retry."""
        fake_items = [{"heading": "Do A", "body": "body A"}]
        with (
            mock.patch(
                "_jolo.autonomous.get_autonomous_items",
                return_value=fake_items,
            ),
            mock.patch("_jolo.autonomous.dispatch_item", return_value=False),
            mock.patch("_jolo.autonomous.mark_dispatched") as mark,
        ):
            autonomous.run_autonomous(self._make_args(agents="claude"))
            mark.assert_not_called()

    def test_successful_dispatch_marks(self):
        fake_items = [{"heading": "Do A", "body": "body A"}]
        with (
            mock.patch(
                "_jolo.autonomous.get_autonomous_items",
                return_value=fake_items,
            ),
            mock.patch("_jolo.autonomous.dispatch_item", return_value=True),
            mock.patch("_jolo.autonomous.mark_dispatched") as mark,
        ):
            autonomous.run_autonomous(self._make_args(agents="claude"))
            mark.assert_called_once()


class TestRunAutonomousFromSubdir(unittest.TestCase):
    """`jolo autonomous` run from a subdirectory resolves to the git root."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        root = Path(self.tmpdir)
        (root / ".git").mkdir()
        (root / "docs").mkdir()
        (root / "docs" / "TODO.org").write_text("* TODO x :autonomous:\n")
        (root / "subdir").mkdir()
        os.chdir(root / "subdir")

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

    def _make_args(self, **overrides):
        import argparse

        ns = argparse.Namespace(
            command="autonomous",
            dry_run=True,
            agents="claude",
            org_file="docs/TODO.org",
            verbose=False,
        )
        for k, v in overrides.items():
            setattr(ns, k, v)
        return ns

    def test_scans_git_root_todo_org_not_cwd(self):
        """Caller in a subdir should still pick up the repo-root TODO.org."""
        seen_paths = []

        def fake_get(org_file):
            seen_paths.append(org_file)
            return []

        with mock.patch(
            "_jolo.autonomous.get_autonomous_items", side_effect=fake_get
        ):
            autonomous.run_autonomous(self._make_args())

        self.assertEqual(len(seen_paths), 1)
        # Must resolve to the root docs/TODO.org, not subdir/docs/TODO.org
        self.assertTrue(seen_paths[0].is_absolute())
        self.assertTrue(str(seen_paths[0]).endswith("docs/TODO.org"))
        self.assertNotIn("/subdir/", str(seen_paths[0]))


if __name__ == "__main__":
    unittest.main()
