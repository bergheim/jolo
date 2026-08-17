"""Tests for container/agent-meta — agent/model/session identity resolver."""

import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "container" / "agent-meta"


def run(env: dict, *args: str) -> str:
    result = subprocess.run(
        [str(SCRIPT), *args],
        env={"PATH": "/usr/bin:/bin", **env},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def claude_home(tmp_path: Path, session: str, model: str) -> Path:
    transcript_dir = tmp_path / ".claude" / "projects" / "-workspaces-proj"
    transcript_dir.mkdir(parents=True)
    lines = [
        json.dumps({"type": "assistant", "message": {"model": "older-model"}}),
        json.dumps({"type": "assistant", "message": {"model": model}}),
    ]
    (transcript_dir / f"{session}.jsonl").write_text("\n".join(lines) + "\n")
    return tmp_path


def test_claude_env_resolves_model_effort_and_session(tmp_path):
    home = claude_home(tmp_path, "sess-uuid-1", "claude-fable-5")
    out = run(
        {
            "HOME": str(home),
            "CLAUDE_CODE_SESSION_ID": "sess-uuid-1",
            "CLAUDE_EFFORT": "high",
        }
    )
    assert out == "claude/claude-fable-5 (high)\nsess-uuid-1\n"


def test_claude_without_effort_or_transcript(tmp_path):
    out = run({"HOME": str(tmp_path), "CLAUDE_CODE_SESSION_ID": "sess-uuid-2"})
    assert out == "claude/unknown\nsess-uuid-2\n"


def test_explicit_override_wins(tmp_path):
    out = run(
        {
            "HOME": str(tmp_path),
            "CLAUDE_CODE_SESSION_ID": "sess-x",
            "AGENT_META_NAME": "codex/gpt-5.2",
            "AGENT_META_SESSION": "codex-sess-9",
        }
    )
    assert out == "codex/gpt-5.2\ncodex-sess-9\n"


def test_unknown_agent_falls_back(tmp_path):
    out = run({"HOME": str(tmp_path)})
    assert out == "unknown\n\n"


def test_elisp_form_with_session(tmp_path):
    home = claude_home(tmp_path, "sess-uuid-3", "claude-fable-5")
    out = run(
        {"HOME": str(home), "CLAUDE_CODE_SESSION_ID": "sess-uuid-3"},
        "--elisp",
    )
    assert out == '"claude/claude-fable-5" "sess-uuid-3"\n'


def test_elisp_form_without_session(tmp_path):
    out = run({"HOME": str(tmp_path)}, "--elisp")
    assert out == '"unknown" nil\n'
