#!/usr/bin/env python3
"""Tests for container/wt's create_window detach/select behavior.

The function text is lifted out of the real script and sourced against a
fake tmux that logs argv. Live tmux is not required.
"""

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "container" / "wt"


def create_window_lib():
    text = SCRIPT.read_text()
    start = text.index("window_name()")
    end = text.index("\n}\n", text.index("create_window()")) + len("\n}\n")
    return text[start:end]


class CreateWindowTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.wt_base = self.tmp / "worktrees"
        self.wt_base.mkdir()
        self.log = self.tmp / "tmux.log"
        bindir = self.tmp / "bin"
        bindir.mkdir()
        tmux = bindir / "tmux"
        tmux.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{self.log}'\n")
        tmux.chmod(tmux.stat().st_mode | stat.S_IEXEC)
        self.env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"}

    def tearDown(self):
        self._tmp.cleanup()

    def run_create(self, select, prompt=""):
        script = (
            f'WT_BASE="{self.wt_base}"\n'
            f"{create_window_lib()}\n"
            f'create_window "foo" "{prompt}" "{select}"\n'
        )
        subprocess.run(
            ["sh", "-c", script],
            check=True,
            env=self.env,
            cwd=self.tmp,
        )
        return self.log.read_text().strip()

    def test_default_is_detached(self):
        logged = self.run_create("")
        self.assertEqual(
            logged,
            f"new-window -d -n wt-foo -c {self.wt_base}/foo",
        )

    def test_select_zero_is_detached(self):
        logged = self.run_create("0")
        self.assertTrue(logged.startswith("new-window -d "), logged)

    def test_select_focuses(self):
        logged = self.run_create("1")
        self.assertEqual(
            logged,
            f"new-window -n wt-foo -c {self.wt_base}/foo",
        )
        self.assertNotIn(" -d ", f" {logged} ")

    def test_prompt_stays_detached(self):
        logged = self.run_create("0", prompt="do the thing")
        self.assertEqual(
            logged,
            f"new-window -d -n wt-foo -c {self.wt_base}/foo claude do the thing",
        )

    def test_prompt_select_has_no_dash_d(self):
        logged = self.run_create("1", prompt="do the thing")
        self.assertEqual(
            logged,
            f"new-window -n wt-foo -c {self.wt_base}/foo claude do the thing",
        )

    def test_cmd_new_wires_switch_flag(self):
        text = SCRIPT.read_text()
        self.assertIn("--switch|-s)", text)
        self.assertIn('create_window "$name" "$prompt" "$select"', text)
        self.assertIn('create_window "$name" "" 1', text)


if __name__ == "__main__":
    unittest.main()
