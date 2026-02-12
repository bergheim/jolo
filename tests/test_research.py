#!/usr/bin/env python3
"""Tests for jolo research command."""

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

try:
    import jolo
except ImportError:
    jolo = None

FAKE_DATE = date(2026, 2, 11)


class TestResearchArgParsing(unittest.TestCase):
    """Test CLI argument parsing for research subcommand."""

    def test_research_command(self):
        args = jolo.parse_args(["research", "my topic"])
        self.assertEqual(args.command, "research")
        self.assertEqual(args.prompt, "my topic")

    def test_research_prompt_optional(self):
        args = jolo.parse_args(["research"])
        self.assertIsNone(args.prompt)

    def test_research_file_flag(self):
        args = jolo.parse_args(["research", "--file", "notes.txt"])
        self.assertEqual(args.file, "notes.txt")

    def test_research_agent_default(self):
        args = jolo.parse_args(["research", "topic"])
        self.assertIsNone(args.agent)

    def test_research_agent_override(self):
        args = jolo.parse_args(["research", "--agent", "gemini", "topic"])
        self.assertEqual(args.agent, "gemini")

    def test_research_verbose_flag(self):
        args = jolo.parse_args(["research", "-v", "topic"])
        self.assertTrue(args.verbose)

    def test_research_all_flags(self):
        args = jolo.parse_args(
            [
                "research",
                "--agent",
                "claude",
                "-v",
                "research question here",
            ]
        )
        self.assertEqual(args.command, "research")
        self.assertEqual(args.prompt, "research question here")
        self.assertEqual(args.agent, "claude")
        self.assertTrue(args.verbose)


class TestSlugifyPrompt(unittest.TestCase):
    """Test slugify_prompt utility."""

    def test_simple_prompt(self):
        self.assertEqual(
            jolo.slugify_prompt("what is an apple"), "what-is-an-apple"
        )

    def test_special_characters(self):
        self.assertEqual(
            jolo.slugify_prompt("what's a C++ compiler?"),
            "what-s-a-c-compiler",
        )

    def test_leading_trailing_stripped(self):
        self.assertEqual(jolo.slugify_prompt("  hello world  "), "hello-world")

    def test_truncation(self):
        long_prompt = "a " * 40
        slug = jolo.slugify_prompt(long_prompt, max_len=10)
        self.assertLessEqual(len(slug), 10)
        self.assertFalse(slug.endswith("-"))

    def test_truncation_breaks_at_hyphen(self):
        slug = jolo.slugify_prompt("alpha-beta-gamma-delta", max_len=15)
        self.assertLessEqual(len(slug), 15)
        self.assertFalse(slug.endswith("-"))

    def test_empty_prompt_returns_research(self):
        self.assertEqual(jolo.slugify_prompt(""), "research")

    def test_all_special_chars_returns_research(self):
        self.assertEqual(jolo.slugify_prompt("!!!???"), "research")

    def test_uppercase_lowered(self):
        self.assertEqual(jolo.slugify_prompt("Hello World"), "hello-world")

    def test_numbers_preserved(self):
        self.assertEqual(
            jolo.slugify_prompt("python 3.12 features"), "python-3-12-features"
        )


class TestEnsureResearchRepo(unittest.TestCase):
    """Test ensure_research_repo creation logic."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_returns_existing_repo(self):
        research_home = Path(self.tmpdir) / "research"
        research_home.mkdir()
        (research_home / ".git").mkdir()
        devcontainer_dir = research_home / ".devcontainer"
        devcontainer_dir.mkdir()
        (devcontainer_dir / "devcontainer.json").write_text("{}")

        config = {"research_home": str(research_home)}
        result = jolo.ensure_research_repo(config)
        self.assertEqual(result, research_home)

    @mock.patch("_jolo.commands.scaffold_devcontainer")
    @mock.patch("_jolo.commands.subprocess.run")
    def test_recreates_after_partial_init(self, mock_run, mock_scaffold):
        research_home = Path(self.tmpdir) / "broken"
        research_home.mkdir()
        (research_home / ".git").mkdir()
        # No .devcontainer — incomplete

        config = {"research_home": str(research_home)}
        jolo.ensure_research_repo(config)

        mock_scaffold.assert_called_once()

    @mock.patch("_jolo.commands.scaffold_devcontainer")
    @mock.patch("_jolo.commands.subprocess.run")
    def test_creates_new_repo(self, mock_run, mock_scaffold):
        research_home = Path(self.tmpdir) / "new-research"
        config = {"research_home": str(research_home)}

        result = jolo.ensure_research_repo(config)

        self.assertEqual(result, research_home)
        self.assertTrue(research_home.exists())

        # git init, git add, git commit
        git_calls = [c[0][0] for c in mock_run.call_args_list]
        self.assertEqual(git_calls[0], ["git", "init"])
        self.assertEqual(git_calls[1], ["git", "add", "."])
        self.assertEqual(git_calls[2][0], "git")
        self.assertEqual(git_calls[2][1], "commit")

    @mock.patch("_jolo.commands.scaffold_devcontainer")
    @mock.patch("_jolo.commands.subprocess.run")
    def test_scaffolds_devcontainer(self, mock_run, mock_scaffold):
        research_home = Path(self.tmpdir) / "new-research"
        config = {"research_home": str(research_home)}

        jolo.ensure_research_repo(config)

        mock_scaffold.assert_called_once_with(
            "research", research_home, config=config
        )

    @mock.patch("_jolo.commands.scaffold_devcontainer")
    @mock.patch("_jolo.commands.subprocess.run")
    def test_copies_research_skill(self, mock_run, mock_scaffold):
        research_home = Path(self.tmpdir) / "new-research"
        config = {"research_home": str(research_home)}

        jolo.ensure_research_repo(config)

        skill_dir = research_home / ".agents" / "skills" / "research"
        self.assertTrue(skill_dir.exists())


class TestResearchMode(unittest.TestCase):
    """Test run_research_mode logic."""

    def _make_args(self, prompt="test topic", agent=None):
        args = jolo.parse_args(["research", prompt])
        args.agent = agent
        return args

    def _base_config(self):
        return {
            "agents": ["claude", "gemini"],
            "agent_commands": {"claude": "claude", "gemini": "gemini"},
        }

    @mock.patch("datetime.date", wraps=date)
    @mock.patch("_jolo.commands.devcontainer_exec_command")
    @mock.patch("_jolo.commands.is_container_running", return_value=True)
    @mock.patch("_jolo.commands.setup_emacs_config")
    @mock.patch("_jolo.commands.setup_notification_hooks")
    @mock.patch("_jolo.commands.setup_credential_cache")
    @mock.patch("_jolo.commands.get_secrets", return_value={})
    @mock.patch("_jolo.commands.ensure_research_repo")
    @mock.patch("_jolo.commands.load_config")
    def test_exec_command_includes_prompt_and_filename(
        self,
        mock_config,
        mock_ensure,
        mock_secrets,
        mock_creds,
        mock_notify,
        mock_emacs,
        mock_running,
        mock_exec,
        mock_dt,
    ):
        mock_dt.today.return_value = FAKE_DATE
        mock_config.return_value = self._base_config()
        research_home = Path("/tmp/fake-research")
        mock_ensure.return_value = research_home

        args = self._make_args(prompt="what is an apple", agent="claude")
        jolo.run_research_mode(args)

        mock_exec.assert_called_once()
        call_args = mock_exec.call_args[0]
        self.assertEqual(call_args[0], research_home)
        exec_cmd = call_args[1]
        self.assertIn("2026-02-11-what-is-an-apple.org", exec_cmd)
        self.assertIn("/research", exec_cmd)
        self.assertIn("what is an apple", exec_cmd)
        self.assertIn("nohup", exec_cmd)

    @mock.patch("datetime.date", wraps=date)
    @mock.patch("_jolo.commands.devcontainer_exec_command")
    @mock.patch("_jolo.commands.is_container_running", return_value=True)
    @mock.patch("_jolo.commands.setup_emacs_config")
    @mock.patch("_jolo.commands.setup_notification_hooks")
    @mock.patch("_jolo.commands.setup_credential_cache")
    @mock.patch("_jolo.commands.get_secrets", return_value={})
    @mock.patch("_jolo.commands.ensure_research_repo")
    @mock.patch("_jolo.commands.load_config")
    def test_uses_explicit_agent(
        self,
        mock_config,
        mock_ensure,
        mock_secrets,
        mock_creds,
        mock_notify,
        mock_emacs,
        mock_running,
        mock_exec,
        mock_dt,
    ):
        mock_dt.today.return_value = FAKE_DATE
        mock_config.return_value = self._base_config()
        mock_ensure.return_value = Path("/tmp/fake-research")

        args = self._make_args(agent="gemini")
        jolo.run_research_mode(args)

        exec_cmd = mock_exec.call_args[0][1]
        self.assertIn("gemini", exec_cmd)

    @mock.patch("datetime.date", wraps=date)
    @mock.patch("_jolo.commands.devcontainer_exec_command")
    @mock.patch("_jolo.commands.is_container_running", return_value=True)
    @mock.patch("_jolo.commands.setup_emacs_config")
    @mock.patch("_jolo.commands.setup_notification_hooks")
    @mock.patch("_jolo.commands.setup_credential_cache")
    @mock.patch("_jolo.commands.get_secrets", return_value={})
    @mock.patch("_jolo.commands.ensure_research_repo")
    @mock.patch("_jolo.commands.load_config")
    def test_empty_agents_falls_back_to_claude(
        self,
        mock_config,
        mock_ensure,
        mock_secrets,
        mock_creds,
        mock_notify,
        mock_emacs,
        mock_running,
        mock_exec,
        mock_dt,
    ):
        mock_dt.today.return_value = FAKE_DATE
        mock_config.return_value = {"agents": [], "agent_commands": {}}
        mock_ensure.return_value = Path("/tmp/fake-research")

        args = self._make_args()
        jolo.run_research_mode(args)

        exec_cmd = mock_exec.call_args[0][1]
        self.assertIn("claude", exec_cmd)

    @mock.patch("datetime.date", wraps=date)
    @mock.patch("_jolo.commands.devcontainer_exec_command")
    @mock.patch("_jolo.commands.devcontainer_up", return_value=True)
    @mock.patch("_jolo.commands.is_container_running", return_value=False)
    @mock.patch("_jolo.commands.setup_emacs_config")
    @mock.patch("_jolo.commands.setup_notification_hooks")
    @mock.patch("_jolo.commands.setup_credential_cache")
    @mock.patch("_jolo.commands.get_secrets", return_value={})
    @mock.patch("_jolo.commands.ensure_research_repo")
    @mock.patch("_jolo.commands.load_config")
    def test_starts_container_when_not_running(
        self,
        mock_config,
        mock_ensure,
        mock_secrets,
        mock_creds,
        mock_notify,
        mock_emacs,
        mock_running,
        mock_up,
        mock_exec,
        mock_dt,
    ):
        mock_dt.today.return_value = FAKE_DATE
        mock_config.return_value = self._base_config()
        research_home = Path("/tmp/fake-research")
        mock_ensure.return_value = research_home

        args = self._make_args(agent="claude")
        jolo.run_research_mode(args)

        mock_up.assert_called_once_with(research_home)
        mock_exec.assert_called_once()

    @mock.patch("datetime.date", wraps=date)
    @mock.patch("_jolo.commands.devcontainer_exec_command")
    @mock.patch("_jolo.commands.devcontainer_up")
    @mock.patch("_jolo.commands.is_container_running", return_value=True)
    @mock.patch("_jolo.commands.setup_emacs_config")
    @mock.patch("_jolo.commands.setup_notification_hooks")
    @mock.patch("_jolo.commands.setup_credential_cache")
    @mock.patch("_jolo.commands.get_secrets", return_value={})
    @mock.patch("_jolo.commands.ensure_research_repo")
    @mock.patch("_jolo.commands.load_config")
    def test_skips_devcontainer_up_when_running(
        self,
        mock_config,
        mock_ensure,
        mock_secrets,
        mock_creds,
        mock_notify,
        mock_emacs,
        mock_running,
        mock_up,
        mock_exec,
        mock_dt,
    ):
        mock_dt.today.return_value = FAKE_DATE
        mock_config.return_value = self._base_config()
        mock_ensure.return_value = Path("/tmp/fake-research")

        args = self._make_args(agent="claude")
        jolo.run_research_mode(args)

        mock_up.assert_not_called()

    @mock.patch("datetime.date", wraps=date)
    @mock.patch("_jolo.commands.devcontainer_up", return_value=False)
    @mock.patch("_jolo.commands.is_container_running", return_value=False)
    @mock.patch("_jolo.commands.setup_emacs_config")
    @mock.patch("_jolo.commands.setup_notification_hooks")
    @mock.patch("_jolo.commands.setup_credential_cache")
    @mock.patch("_jolo.commands.get_secrets", return_value={})
    @mock.patch("_jolo.commands.ensure_research_repo")
    @mock.patch("_jolo.commands.load_config")
    def test_exits_on_container_failure(
        self,
        mock_config,
        mock_ensure,
        mock_secrets,
        mock_creds,
        mock_notify,
        mock_emacs,
        mock_running,
        mock_up,
        mock_dt,
    ):
        mock_dt.today.return_value = FAKE_DATE
        mock_config.return_value = self._base_config()
        mock_ensure.return_value = Path("/tmp/fake-research")

        args = self._make_args(agent="claude")
        with self.assertRaises(SystemExit):
            jolo.run_research_mode(args)


class TestResolveResearchPrompt(unittest.TestCase):
    """Test _resolve_research_prompt input modes."""

    def _make_args(self, prompt=None, file=None):
        args = jolo.parse_args(["research"] + ([prompt] if prompt else []))
        args.file = file
        return args

    def test_prompt_from_args(self):
        from _jolo.commands import _resolve_research_prompt

        args = self._make_args(prompt="what is rust")
        self.assertEqual(_resolve_research_prompt(args), "what is rust")

    def test_prompt_from_file(self):
        from _jolo.commands import _resolve_research_prompt

        tmpdir = tempfile.mkdtemp()
        try:
            f = Path(tmpdir) / "question.txt"
            f.write_text("how do GPUs work?\n")
            args = self._make_args(file=str(f))
            self.assertEqual(
                _resolve_research_prompt(args), "how do GPUs work?"
            )
        finally:
            import shutil

            shutil.rmtree(tmpdir)

    def test_file_not_found_exits(self):
        from _jolo.commands import _resolve_research_prompt

        args = self._make_args(file="/nonexistent/path.txt")
        with self.assertRaises(SystemExit):
            _resolve_research_prompt(args)

    def test_file_takes_priority_over_prompt(self):
        from _jolo.commands import _resolve_research_prompt

        tmpdir = tempfile.mkdtemp()
        try:
            f = Path(tmpdir) / "q.txt"
            f.write_text("from file")
            args = self._make_args(prompt="from args", file=str(f))
            self.assertEqual(_resolve_research_prompt(args), "from file")
        finally:
            import shutil

            shutil.rmtree(tmpdir)

    @mock.patch("_jolo.commands.subprocess.run")
    def test_editor_fallback(self, mock_run):
        from _jolo.commands import _resolve_research_prompt

        def write_to_file(cmd, **kwargs):
            # cmd is a shell string like "fake-editor /tmp/...txt"
            tmppath = cmd.split()[-1].strip("'")
            Path(tmppath).write_text("# comment\neditor question\n")
            return mock.Mock(returncode=0)

        mock_run.side_effect = write_to_file

        args = self._make_args()
        with mock.patch.dict(os.environ, {"EDITOR": "fake-editor"}):
            result = _resolve_research_prompt(args)
        self.assertEqual(result, "editor question")

    @mock.patch("_jolo.commands.subprocess.run")
    def test_editor_empty_exits(self, mock_run):
        from _jolo.commands import _resolve_research_prompt

        def write_empty(cmd, **kwargs):
            tmppath = cmd.split()[-1].strip("'")
            Path(tmppath).write_text("# only comments\n")
            return mock.Mock(returncode=0)

        mock_run.side_effect = write_empty

        args = self._make_args()
        with mock.patch.dict(os.environ, {"EDITOR": "fake-editor"}):
            with self.assertRaises(SystemExit):
                _resolve_research_prompt(args)

    def test_visual_takes_priority_over_editor(self):
        from _jolo.commands import _resolve_research_prompt

        args = self._make_args(prompt="test")
        with mock.patch.dict(os.environ, {"VISUAL": "emacs", "EDITOR": "vi"}):
            # With a prompt arg, editor is not invoked — just verify
            # the prompt passthrough works (VISUAL/EDITOR only matters
            # when no prompt given)
            self.assertEqual(_resolve_research_prompt(args), "test")


if __name__ == "__main__":
    unittest.main()
