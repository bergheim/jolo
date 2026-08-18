"""Always-restore cwd helpers for unittest.

``tearDown`` is skipped when ``setUp`` raises. ``addCleanup`` is not.
A later test that runs ``git config``/``git init`` without ``cwd=`` then
hits whatever repo the leaked cwd walks up to — including this one.
"""

from __future__ import annotations

import os
import shutil
import tempfile


def isolate_cwd(test, path=None) -> str:
    """chdir to ``path`` (or a fresh tmpdir) and always restore."""
    orig = os.getcwd()
    if path is None:
        path = tempfile.mkdtemp()
        test.addCleanup(shutil.rmtree, path)
    test.addCleanup(os.chdir, orig)
    os.chdir(path)
    return path


def tracked_tmpdir(test) -> str:
    """Fresh tmpdir plus cwd restore, without changing cwd yet.

    Tests that chdir in the method body still get restored if they fail.
    """
    orig = os.getcwd()
    path = tempfile.mkdtemp()
    test.addCleanup(shutil.rmtree, path)
    test.addCleanup(os.chdir, orig)
    return path
