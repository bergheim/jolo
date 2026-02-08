#!/usr/bin/env python3
"""jolo - Devcontainer + Git Worktree Launcher.

A CLI tool that bootstraps devcontainer environments with git worktree support.
Target location: ~/.local/bin/jolo

Pronounced "yolo" in Norwegian. Close enough.
"""

import os
import sys

# Resolve symlink so Python finds the _jolo package next to the real file
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from _jolo import *  # noqa: F401,F403 - re-export public API for backward compat
from _jolo.commands import main

if __name__ == "__main__":
    main()
