#!/usr/bin/env python3
"""Tests for `jolo autonomous` — TODO-driven task dispatcher."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import jolo
from _jolo import autonomous


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

    def test_emacsclient_failure_raises(self):
        """Failure must surface, not silently look like an empty queue."""
        with mock.patch("_jolo.autonomous.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = (
                "symbol's function definition is void"
            )
            mock_run.return_value.stdout = ""
            with self.assertRaises(autonomous.EmacsClientError):
                autonomous.get_autonomous_items(Path("docs/TODO.org"))


class TestMarkDispatched(unittest.TestCase):
    """Emacsclient-backed property setter."""

    def test_invokes_mark_function_with_position(self):
        # Mark by opaque buffer position, not heading, so duplicate-titled
        # items can't clobber each other's DISPATCHED state.
        with mock.patch("_jolo.autonomous.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            autonomous.mark_dispatched(
                Path("docs/TODO.org"),
                4242,
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
            self.assertIn("4242", elisp)


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

    def test_passes_cwd_to_subprocess(self):
        """jolo tree must run from the repo root so it loads .jolo.toml."""
        with mock.patch("_jolo.autonomous.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            autonomous.dispatch_item(
                slug="x", prompt="y", agent="claude", cwd=Path("/some/root")
            )
            self.assertEqual(
                mock_run.call_args.kwargs.get("cwd"), Path("/some/root")
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
            {"heading": "TODO Do A", "body": "body A", "position": 100},
            {"heading": "TODO Do B", "body": "body B", "position": 200},
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
            {"heading": "TODO Do A", "body": "body A", "position": 100},
            {"heading": "TODO Do B", "body": "body B", "position": 200},
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
            # Round-robin is a property of the item index, not the iteration
            # order: item 0 gets agent[0], item 1 gets agent[1].
            prompts_to_agents = {
                call.kwargs["prompt"]: call.kwargs["agent"]
                for call in dispatch.call_args_list
            }
            self.assertEqual(prompts_to_agents["body A"], "claude")
            self.assertEqual(prompts_to_agents["body B"], "codex")

    def test_marks_applied_in_reverse_position_order(self):
        """Later positions must be marked first so earlier edits don't shift them."""
        fake_items = [
            {"heading": "A", "body": "", "position": 100},
            {"heading": "B", "body": "", "position": 200},
            {"heading": "C", "body": "", "position": 300},
        ]
        with (
            mock.patch(
                "_jolo.autonomous.get_autonomous_items",
                return_value=fake_items,
            ),
            mock.patch("_jolo.autonomous.dispatch_item", return_value=True),
            mock.patch("_jolo.autonomous.mark_dispatched") as mark,
        ):
            autonomous.run_autonomous(self._make_args(agents="claude"))
            positions = [call.args[1] for call in mark.call_args_list]
            self.assertEqual(positions, [300, 200, 100])

    def test_slugs_include_run_timestamp_suffix(self):
        """Retries pick up a fresh worktree by run-timestamp, not the old one."""
        fake_items = [
            {"heading": "Do A", "body": "body A", "position": 10},
        ]
        with (
            mock.patch(
                "_jolo.autonomous.get_autonomous_items",
                return_value=fake_items,
            ),
            mock.patch(
                "_jolo.autonomous.dispatch_item", return_value=True
            ) as dispatch,
            mock.patch("_jolo.autonomous.mark_dispatched"),
        ):
            autonomous.run_autonomous(self._make_args(agents="claude"))
            slug = dispatch.call_args.kwargs["slug"]
            # suffix is YYYYMMDDTHHMMSS — 15 chars after a `-`
            self.assertRegex(slug, r"^autonomous-do-a-\d{8}T\d{6}$")

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
        fake_items = [{"heading": "Do A", "body": "body A", "position": 10}]
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

    def test_successful_dispatch_marks_by_position(self):
        """Mark uses the opaque position field, not the heading, as identity."""
        fake_items = [{"heading": "Do A", "body": "body A", "position": 42}]
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
            call_args = mark.call_args
            # mark_dispatched(org_file, position, timestamp) — assert the
            # middle arg is our opaque identity (42), not the heading.
            self.assertEqual(call_args.args[1], 42)


class TestUniqueSlugs(unittest.TestCase):
    """Collision-free worktree slugs even when headings repeat."""

    def test_single_heading_passes_through(self):
        self.assertEqual(
            autonomous._unique_slugs([{"heading": "Do A"}]),
            ["autonomous-do-a"],
        )

    def test_duplicate_headings_get_counter_suffix(self):
        items = [
            {"heading": "Do A"},
            {"heading": "Do A"},
            {"heading": "Do B"},
            {"heading": "Do A"},
        ]
        self.assertEqual(
            autonomous._unique_slugs(items),
            [
                "autonomous-do-a",
                "autonomous-do-a-2",
                "autonomous-do-b",
                "autonomous-do-a-3",
            ],
        )

    def test_suffix_appended_to_every_slug(self):
        items = [{"heading": "Do A"}, {"heading": "Do A"}]
        self.assertEqual(
            autonomous._unique_slugs(items, suffix="20260419T102120"),
            [
                "autonomous-do-a-20260419T102120",
                "autonomous-do-a-2-20260419T102120",
            ],
        )


class TestRunAutonomousSurfacesEmacsClientError(unittest.TestCase):
    """Setup errors (daemon down, helper missing) must fail loud."""

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

    def _make_args(self):
        import argparse

        return argparse.Namespace(
            command="autonomous",
            dry_run=False,
            agents="claude",
            org_file="docs/TODO.org",
            verbose=False,
        )

    def test_selector_failure_exits_non_zero(self):
        with mock.patch(
            "_jolo.autonomous.get_autonomous_items",
            side_effect=autonomous.EmacsClientError("daemon down"),
        ):
            with self.assertRaises(SystemExit) as ctx:
                autonomous.run_autonomous(self._make_args())
            self.assertNotEqual(ctx.exception.code, 0)


class TestRunAutonomousLoadsConfigFromGitRoot(unittest.TestCase):
    """`.jolo.toml` at the repo root must be honored when run from subdirs."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        root = Path(self.tmpdir)
        (root / ".git").mkdir()
        (root / "docs").mkdir()
        (root / "docs" / "TODO.org").write_text("* TODO x :autonomous:\n")
        (root / ".jolo.toml").write_text('agents = ["codex"]\n')
        (root / "subdir").mkdir()
        os.chdir(root / "subdir")

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

    def _make_args(self):
        import argparse

        return argparse.Namespace(
            command="autonomous",
            dry_run=True,
            agents=None,
            org_file="docs/TODO.org",
            verbose=False,
        )

    def test_repo_config_wins_from_subdir(self):
        with (
            mock.patch(
                "_jolo.autonomous.get_autonomous_items",
                return_value=[{"heading": "X", "body": "", "position": 1}],
            ),
            mock.patch(
                "_jolo.autonomous.dispatch_item", return_value=True
            ) as dispatch,
            mock.patch("builtins.print"),
        ):
            autonomous.run_autonomous(self._make_args())
            # dry_run=True so dispatch isn't called; assert agents came from
            # repo config by switching to real-run mode via another args obj.

        # Real-run variant to observe agent selection:
        import argparse

        real_args = argparse.Namespace(
            command="autonomous",
            dry_run=False,
            agents=None,
            org_file="docs/TODO.org",
            verbose=False,
        )
        with (
            mock.patch(
                "_jolo.autonomous.get_autonomous_items",
                return_value=[{"heading": "X", "body": "b", "position": 1}],
            ),
            mock.patch(
                "_jolo.autonomous.dispatch_item", return_value=True
            ) as dispatch,
            mock.patch("_jolo.autonomous.mark_dispatched"),
        ):
            autonomous.run_autonomous(real_args)
            self.assertEqual(dispatch.call_args.kwargs["agent"], "codex")


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
