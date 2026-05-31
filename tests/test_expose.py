#!/usr/bin/env python3
"""Tests for jolo expose (public dev-server slot via socat)."""

import unittest
from pathlib import Path
from unittest import mock

import jolo
from _jolo import constants, expose


class TestExposeArgParsing(unittest.TestCase):
    def test_expose_command(self):
        args = jolo.parse_args(["expose"])
        self.assertEqual(args.command, "expose")


class TestExposeRun(unittest.TestCase):
    def _run(self, *, port=4464, listening=True):
        with (
            mock.patch.object(
                expose, "pick_project", return_value=Path("/p/myapp")
            ),
            mock.patch.object(
                expose, "read_port_from_devcontainer", return_value=port
            ),
            mock.patch.object(
                expose, "_port_listening", return_value=listening
            ),
            mock.patch.object(expose.subprocess, "run") as run,
        ):
            expose.run_expose_mode(mock.Mock())
            return run

    def test_forwards_slot_to_project_port(self):
        run = self._run(port=4464)
        cmd = run.call_args[0][0]
        slot = constants.EXPOSE_SLOT_PORT
        self.assertEqual(cmd[0], "socat")
        self.assertIn(f"TCP-LISTEN:{slot},bind=127.0.0.1,fork,reuseaddr", cmd)
        self.assertIn("TCP:127.0.0.1:4464", cmd)

    def test_missing_port_exits(self):
        with (
            mock.patch.object(
                expose, "pick_project", return_value=Path("/p/x")
            ),
            mock.patch.object(
                expose, "read_port_from_devcontainer", return_value=None
            ),
        ):
            with self.assertRaises(SystemExit):
                expose.run_expose_mode(mock.Mock())


if __name__ == "__main__":
    unittest.main()
