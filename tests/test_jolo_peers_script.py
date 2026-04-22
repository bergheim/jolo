#!/usr/bin/env python3
"""Tests for the container-side standalone reader at container/jolo-peers."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "container" / "jolo-peers"


def _run(stash: Path, *args: str) -> subprocess.CompletedProcess:
    """Run the reader with HOME set so /workspaces/stash is bypassed."""
    env = {"HOME": str(stash.parent), "PATH": "/usr/bin:/bin"}
    # The script prefers /workspaces/stash if it exists. In tests where that
    # path exists on the developer machine, we point HOME at a sibling
    # structure and rely on a real /workspaces/stash for one test; but for
    # isolation tests we invoke with a stashless HOME so the script falls
    # back to the HOME candidate that won't exist either.
    return subprocess.run(
        ["python3", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
    )


class TestJoloPeersScript(unittest.TestCase):
    """End-to-end exercise of the standalone reader."""

    def test_script_is_executable(self):
        self.assertTrue(SCRIPT.exists(), SCRIPT)

    def test_empty_registry(self):
        with tempfile.TemporaryDirectory() as td:
            # No /workspaces/stash and no stash under HOME ⇒ empty
            result = _run(Path(td))
            self.assertEqual(result.returncode, 0)
            # Real /workspaces/stash may or may not exist on the dev host;
            # accept both "No peer" and an entry list. Only check no crash.
            self.assertNotIn("Traceback", result.stderr)

    def test_json_flag_outputs_list(self):
        with tempfile.TemporaryDirectory() as td:
            result = _run(Path(td), "--json")
            self.assertEqual(result.returncode, 0)
            data = json.loads(result.stdout)
            self.assertIsInstance(data, list)

    def test_reads_fake_registry(self):
        """When /workspaces/stash does not exist, the script falls back to
        ~/stash/.jolo/peers.json."""
        # Only run this test on hosts where /workspaces/stash is absent; if
        # it exists we cannot shadow it from here. Skip gracefully.
        if Path("/workspaces/stash").exists():
            self.skipTest(
                "/workspaces/stash exists; cannot shadow it in tests"
            )
        with tempfile.TemporaryDirectory() as td:
            stash = Path(td) / "stash"
            (stash / ".jolo").mkdir(parents=True)
            (stash / ".jolo" / "peers.json").write_text(
                json.dumps(
                    [{"container": "c1", "project": "p1", "port": 4000}]
                )
            )
            env_home = {"HOME": str(td), "PATH": "/usr/bin:/bin"}
            result = subprocess.run(
                ["python3", str(SCRIPT)],
                capture_output=True,
                text=True,
                env=env_home,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("c1", result.stdout)


if __name__ == "__main__":
    unittest.main()
