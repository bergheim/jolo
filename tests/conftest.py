"""Suite-level git isolation.

Even if a test leaks cwd or calls ``git config --global``, the real
repo config and the user's ~/.gitconfig must stay untouched.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]


def _repo_git_config() -> Path:
    git_dir = Path(
        subprocess.check_output(
            ["git", "-C", str(_REPO), "rev-parse", "--git-common-dir"],
            text=True,
        ).strip()
    )
    if not git_dir.is_absolute():
        git_dir = _REPO / git_dir
    return git_dir / "config"


@pytest.fixture(autouse=True)
def _restore_cwd():
    orig = os.getcwd()
    yield
    os.chdir(orig)


@pytest.fixture(scope="session", autouse=True)
def _sandbox_and_guard_git_config(tmp_path_factory):
    config = _repo_git_config()
    before = config.read_bytes()

    sandbox = tmp_path_factory.mktemp("git-config")
    global_cfg = sandbox / "global"
    system_cfg = sandbox / "system"
    global_cfg.write_text("")
    system_cfg.write_text("")
    os.environ["GIT_CONFIG_GLOBAL"] = str(global_cfg)
    os.environ["GIT_CONFIG_SYSTEM"] = str(system_cfg)
    os.environ["GIT_CONFIG_NOSYSTEM"] = "1"

    yield

    after = config.read_bytes()
    assert after == before, (
        f"Test suite mutated {config}. "
        "Pass cwd= or -C to every git invocation."
    )
