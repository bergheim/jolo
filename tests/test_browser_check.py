#!/usr/bin/env python3
"""Tests for container/browser-check.js.

Drives the real script against file:// fixtures, so the viewport contexts and
the in-page overflow walk are exercised for real. The suppression cases carry
their weight here: an overflow report that cries wolf on skip links, off-canvas
drawers and deliberate scroll boxes is one nobody will run twice.
"""

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "container" / "browser-check.js"

# One genuine offender (.card), surrounded by patterns that look like overflow
# and are not: a visually-hidden skip link, a fixed off-canvas drawer, a
# clipped carousel over a 2000px track, and a table scrolling in its own box.
WIDE = """<!doctype html><meta charset=utf-8><title>Wide</title>
<style>body{margin:0}
.card{width:500px}
a.sr-only{position:absolute;left:-10000px;width:200px;height:20px}
nav#drawer{position:fixed;left:-320px;width:320px;height:100px}
#carousel{overflow:hidden;width:100%}
#track{width:2000px;height:40px}
.scroller{overflow-x:auto;max-width:100%}
.scroller table{width:1400px}
</style>
<a class="sr-only" href="#main">Skip to content</a>
<nav id="drawer">off-canvas</nav>
<div id="carousel"><div id="track"></div></div>
<div class="scroller"><table><tr><td>wide but scrolls in its own box</td></tr></table></div>
<div class="card">I do not fit on a phone.</div>
"""

NARROW = """<!doctype html><meta charset=utf-8><title>Fine</title>
<style>body{margin:0}img{max-width:100%}</style>
<h1>Nothing here overflows</h1><p>Just text in a normal flow.</p>
"""


def node_env():
    """The wrapper baked into the image resolves playwright via NODE_PATH."""
    env = os.environ.copy()
    wrapper = Path.home() / ".local" / "bin" / "browser-check"
    if wrapper.exists():
        match = re.search(r"NODE_PATH=(\S+)", wrapper.read_text())
        if match:
            env["NODE_PATH"] = match.group(1)
    return env


class BrowserCheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls._tmp.name)
        (cls.dir / "wide.html").write_text(WIDE)
        (cls.dir / "narrow.html").write_text(NARROW)
        cls.env = node_env()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def run_check(self, page, *args):
        url = f"file://{self.dir / page}"
        return subprocess.run(
            ["node", str(SCRIPT), url, *args],
            capture_output=True,
            text=True,
            env=self.env,
            cwd=self.dir,
            timeout=120,
        )

    def test_overflow_exits_1_and_names_the_element(self):
        result = self.run_check("wide.html", "--overflow", "--width", "320")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("div.card", result.stdout)

    def test_overflow_ignores_decoys(self):
        """Only the real offender is reported, once."""
        result = self.run_check(
            "wide.html", "--overflow", "--width", "320", "--json"
        )
        viewport = json.loads(result.stdout)["viewports"][0]
        selectors = [o["selector"] for o in viewport["overflow"]["offenders"]]
        self.assertEqual(selectors, ["div.card"])

    def test_wide_enough_viewport_exits_0(self):
        result = self.run_check("wide.html", "--overflow", "--width", "900")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_clean_page_exits_0(self):
        result = self.run_check("narrow.html", "--overflow", "--width", "320")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_navigation_failure_is_not_a_pass(self):
        """A dead target must not report 'no overflow' and exit clean."""
        result = subprocess.run(
            [
                "node",
                str(SCRIPT),
                f"file://{self.dir}/does-not-exist.html",
                "--overflow",
                "--width",
                "320",
                "--timeout",
                "5000",
                "--wait",
                "0",
            ],
            capture_output=True,
            text=True,
            env=self.env,
            cwd=self.dir,
            timeout=120,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_multiple_widths_suffix_the_output(self):
        result = self.run_check(
            "narrow.html",
            "--screenshot",
            "--width",
            "320,390,430",
            "--output",
            "shots/p.png",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for width in (320, 390, 430):
            self.assertTrue((self.dir / "shots" / f"p-{width}.png").exists())

    def test_single_width_writes_output_verbatim(self):
        result = self.run_check(
            "narrow.html",
            "--screenshot",
            "--width",
            "390",
            "--output",
            "one.png",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.dir / "one.png").exists())

    def test_repeated_width_flag(self):
        self.run_check(
            "narrow.html",
            "--screenshot",
            "--width",
            "320",
            "--width",
            "768",
            "--output",
            "rep.png",
        )
        self.assertTrue((self.dir / "rep-320.png").exists())
        self.assertTrue((self.dir / "rep-768.png").exists())

    def test_url_after_a_valued_flag(self):
        """`--width 320 <url>` must not treat the operand as the target."""
        result = subprocess.run(
            [
                "node",
                str(SCRIPT),
                "--width",
                "320",
                "--describe",
                f"file://{self.dir / 'narrow.html'}",
            ],
            capture_output=True,
            text=True,
            env=self.env,
            cwd=self.dir,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("narrow.html", result.stdout)
        self.assertNotIn("Navigating to 320", result.stdout)

    def test_json_reports_per_width_viewports(self):
        result = self.run_check(
            "wide.html", "--overflow", "--width", "320,900", "--json"
        )
        payload = json.loads(result.stdout)
        self.assertEqual(
            [v["width"] for v in payload["viewports"]], [320, 900]
        )
        self.assertTrue(
            payload["viewports"][0]["overflow"]["documentOverflows"]
        )
        self.assertFalse(
            payload["viewports"][1]["overflow"]["documentOverflows"]
        )

    def test_invalid_arguments_are_rejected(self):
        for args in (
            ["--width", "abc"],
            ["--width", "0"],
            ["--width"],
            ["--height", "900"],
            ["--pdf", "--width", "320,430"],
        ):
            with self.subTest(args=args):
                result = self.run_check("narrow.html", *args)
                self.assertEqual(
                    result.returncode, 2, result.stdout + result.stderr
                )
                self.assertIn("error:", result.stderr)


if __name__ == "__main__":
    unittest.main()
