"""Tests for container/org-backfill — one-time CREATED/SESSION_ID backfill."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "container" / "org-backfill"

HEADER = "#+TODO: TODO(t) INPROGRESS(i) | DONE(d) CANCELLED(c)\n\n"


def run(path: Path) -> str:
    result = subprocess.run(
        [str(SCRIPT), str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def git(repo: Path, *args: str, date: str | None = None) -> None:
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    if date:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    subprocess.run(
        ["git", "-C", str(repo), *args],
        env={"PATH": "/usr/bin:/bin", **env},
        capture_output=True,
        check=True,
    )


def test_created_derived_from_first_git_commit(tmp_path):
    git(tmp_path, "init", "-q")
    todo = tmp_path / "TODO.org"
    todo.write_text(HEADER + "* TODO Old task\nBody.\n")
    git(tmp_path, "add", ".")
    git(
        tmp_path, "commit", "-q", "-m", "add", date="2026-03-05T14:30:00+00:00"
    )
    todo.write_text(todo.read_text() + "* TODO Newer task\n")
    git(tmp_path, "add", ".")
    git(
        tmp_path,
        "commit",
        "-q",
        "-m",
        "more",
        date="2026-04-10T09:00:00+00:00",
    )

    run(todo)
    content = todo.read_text()
    assert ":CREATED:  [2026-03-05 Thu" in content.split("* TODO Newer")[0]
    assert ":CREATED:  [2026-04-10 Fri" in content.split("* TODO Newer")[1]


def test_falls_back_to_id_timestamp_without_git(tmp_path):
    todo = tmp_path / "TODO.org"
    todo.write_text(
        HEADER
        + "* TODO Task\n:PROPERTIES:\n:ID: 20260421T100425Z-7e8902\n:END:\n"
    )
    run(todo)
    assert ":CREATED:  [2026-04-21 Tue 10:04]" in todo.read_text()


def test_falls_back_to_epoch_when_nothing_known(tmp_path):
    todo = tmp_path / "TODO.org"
    todo.write_text(HEADER + "* TODO Mystery task\n")
    run(todo)
    assert ":CREATED:  [1970-01-01 Thu 00:00]" in todo.read_text()


def test_strips_session_id_lines(tmp_path):
    todo = tmp_path / "TODO.org"
    todo.write_text(
        HEADER
        + "* TODO Task\n:PROPERTIES:\n:ID: aaa\n:SESSION_ID: 20260520T122632Z-803519\n:END:\n"
    )
    run(todo)
    content = todo.read_text()
    assert "SESSION_ID" not in content
    assert ":ID: aaa" in content


def test_existing_created_untouched_and_idempotent(tmp_path):
    todo = tmp_path / "TODO.org"
    todo.write_text(
        HEADER
        + "* TODO Task\n:PROPERTIES:\n:CREATED: [2025-01-01 Wed 12:00]\n:END:\n"
    )
    run(todo)
    first = todo.read_text()
    assert first.count("CREATED") == 1
    assert "[2025-01-01 Wed 12:00]" in first
    run(todo)
    assert todo.read_text() == first


def test_falls_back_to_earliest_worklog_mention(tmp_path):
    project = tmp_path / "myproj"
    (project / "docs").mkdir(parents=True)
    todo = project / "docs" / "TODO.org"
    todo.write_text(HEADER + "* TODO Wire the thing\n")
    worklog = tmp_path / "worklog.org"
    worklog.write_text(
        "* [2026-06-02 Tue 09:15] [myproj] INPROGRESS  Wire the thing\n"
        ":PROPERTIES:\n:PROJECT:    myproj\n:END:\n"
        "* [2026-05-01 Fri 08:00] [myproj] INPROGRESS  Wire the thing\n"
        ":PROPERTIES:\n:PROJECT:    myproj\n:END:\n"
        "* [2026-04-01 Wed 08:00] [otherproj] INPROGRESS  Wire the thing\n"
        ":PROPERTIES:\n:PROJECT:    otherproj\n:END:\n"
    )
    subprocess.run(
        [str(SCRIPT), "--worklog", str(worklog), str(todo)],
        capture_output=True,
        text=True,
        check=True,
    )
    # Earliest mention for THIS project wins; other projects are ignored.
    assert ":CREATED:  [2026-05-01 Fri 08:00]" in todo.read_text()


def test_missing_id_is_generated_from_created_stamp(tmp_path):
    todo = tmp_path / "TODO.org"
    todo.write_text(HEADER + "* TODO Task\n")
    run(todo)
    content = todo.read_text()
    # Same shape agent-org-task-create produces: UTC stamp + random hex suffix,
    # with the timestamp part matching the (epoch) CREATED fallback.
    assert ":ID: 19700101T000000Z-" in content
    assert content.index(":ID:") < content.index(":CREATED:")


def test_done_entries_and_non_todo_headings(tmp_path):
    todo = tmp_path / "TODO.org"
    todo.write_text(HEADER + "* Tasks\n** DONE Finished thing\n")
    run(todo)
    content = todo.read_text()
    # Plain headings get nothing; TODO-keyword entries at any level do.
    assert content.count(":CREATED:") == 1
    assert content.index(":CREATED:") > content.index("DONE Finished")
