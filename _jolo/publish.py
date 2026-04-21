"""jolo publish — flip a project to public-notes mode.

Moves docs/PROJECT.org to the repo root, initializes a nested git repo
inside docs/, updates the outer .gitignore so docs/ is no longer tracked,
and (optionally) rewrites outer history with git-filter-repo to remove
pre-existing memory/notes files.

Force-push of the scrubbed history is NOT automated — it is destructive
and left to the user as an explicit manual step.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from _jolo import cli

# Paths removed from outer git history when --scrub is requested.
# docs/PROJECT.org is intentionally NOT in this list — it is moved to
# the repo root so the public repo keeps its architecture doc.
KILL_LIST_PATHS = [
    ".claude/MEMORY.md",
    ".codex/MEMORY.md",
    ".gemini/MEMORY.md",
    ".pi/MEMORY.md",
    "docs/MEMORY.org",
    "docs/TODO.org",
    "docs/RESEARCH.org",
    "docs/TROUBLESHOOTING.org",
    "docs/ARCHIVE.org",
    "docs/notes/",
    "docs/research/",
    "docs/superpowers/",
]
KILL_LIST_GLOBS = [
    "docs/2026-*.org",
    "docs/2027-*.org",
]

# gitignore lines that the scrub workflow may have inserted — superseded
# by a single `docs/` entry once publish runs.
LEGACY_SCRUB_LINES = frozenset(
    {
        "docs/MEMORY.org",
        "docs/TODO.org",
        "docs/RESEARCH.org",
        "docs/TROUBLESHOOTING.org",
        "docs/ARCHIVE.org",
        "docs/notes/",
        "docs/research/",
        "docs/superpowers/",
        "docs/2026-*.org",
        "docs/2027-*.org",
    }
)

PUBLISH_GITIGNORE_MARKER = (
    "# Public-notes mode — docs/ is a separate private git repo"
)
PUBLISH_GITIGNORE_BLOCK = f"""
# =============================================================================
{PUBLISH_GITIGNORE_MARKER}
# =============================================================================

docs/
"""


def run_publish_mode(args) -> None:
    """Flip the current project into public-notes mode."""
    git_root = cli.find_git_root()
    if git_root is None:
        print("ERROR: not in a git repository", file=sys.stderr)
        sys.exit(1)

    docs_dir = git_root / "docs"
    docs_git = docs_dir / ".git"

    if docs_git.exists():
        print(
            f"ERROR: {docs_git} already exists — project is already in "
            "public-notes mode",
            file=sys.stderr,
        )
        sys.exit(1)

    if not docs_dir.exists():
        print(
            f"ERROR: {docs_dir} does not exist — nothing to publish",
            file=sys.stderr,
        )
        sys.exit(1)

    if outer_repo_dirty(git_root):
        print(
            "ERROR: outer repo has uncommitted changes. Commit or stash "
            "before publishing.",
            file=sys.stderr,
        )
        sys.exit(1)

    plan = build_plan(git_root, docs_dir, scrub=args.scrub)
    print_plan(plan, dry_run=args.dry_run)
    if args.dry_run:
        return

    if not args.yes and not confirm("\nProceed? [y/N] "):
        print("Cancelled.")
        return

    if args.scrub:
        if not shutil.which("git-filter-repo"):
            print(
                "ERROR: git-filter-repo is not installed. "
                "Install it or re-run with --scrub disabled (default).",
                file=sys.stderr,
            )
            sys.exit(1)
        if not confirm_scrub(args.yes):
            print("Scrub cancelled; aborting publish.")
            return
        backup_dir = backup_docs(docs_dir)
        try:
            run_filter_repo(git_root)
        finally:
            restore_docs(backup_dir, docs_dir)

    move_project_org(docs_dir, git_root)
    untrack_docs_from_outer(git_root)
    init_notes_repo(docs_dir)
    update_outer_gitignore(git_root)
    commit_outer(git_root, scrubbed=args.scrub)

    print("\nPublish complete.")
    if args.scrub:
        print(
            "\n⚠ Next step (manual, destructive): force-push the scrubbed "
            "history when you are ready:\n"
            "\n  git push --force --all"
            "\n  git push --force --tags"
        )
    else:
        print("\nOuter repo updated. Push when ready:\n\n  git push")

    print(
        f"\nNotes repo ({docs_dir}) has no remote yet. Add one with:\n"
        "\n  cd docs && git remote add origin <url>"
        " && git push -u origin main"
    )


# ---------------------------------------------------------------------------
# Helpers (module-level so tests can call them without a full CLI namespace)


def outer_repo_dirty(git_root: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(git_root), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(result.stdout.strip())


def build_plan(git_root: Path, docs_dir: Path, *, scrub: bool) -> dict:
    project_org = docs_dir / "PROJECT.org"
    return {
        "git_root": git_root,
        "docs_dir": docs_dir,
        "scrub": scrub,
        "move_project_org": project_org.exists()
        and not (git_root / "PROJECT.org").exists(),
        "project_org_conflict": project_org.exists()
        and (git_root / "PROJECT.org").exists(),
    }


def print_plan(plan: dict, *, dry_run: bool) -> None:
    print(f"Publish project at {plan['git_root']}:")
    print(f"  - scrub history:        {'yes' if plan['scrub'] else 'no'}")
    if plan["move_project_org"]:
        print("  - move docs/PROJECT.org → PROJECT.org")
    elif plan["project_org_conflict"]:
        print(
            "  - docs/PROJECT.org present but PROJECT.org already exists; "
            "you will need to merge them manually"
        )
    else:
        print("  - docs/PROJECT.org: not present")
    print(f"  - init nested git repo in {plan['docs_dir']}")
    print(f"  - update {plan['git_root'] / '.gitignore'}")
    if dry_run:
        print("\n--dry-run: no changes made.")


def confirm(prompt: str) -> bool:
    try:
        response = input(prompt).strip().lower()
    except EOFError:
        response = ""
    return response == "y"


def confirm_scrub(yes_flag: bool) -> bool:
    """Scrub requires an explicit YES even under --yes — it is destructive."""
    if yes_flag:
        print(
            "History scrub is destructive and rewrites every commit on every "
            "branch. --yes does not auto-confirm this step."
        )
    print("\nKill list paths (removed from ALL history):")
    for p in KILL_LIST_PATHS:
        print(f"  {p}")
    for g in KILL_LIST_GLOBS:
        print(f"  {g}")
    try:
        response = input('\nType "YES" to confirm scrub: ').strip()
    except EOFError:
        response = ""
    return response == "YES"


def backup_docs(docs_dir: Path) -> Path:
    """git-filter-repo does a hard reset after rewriting — back docs/ up first."""
    backup = Path(f"/tmp/jolo-publish-docs-{docs_dir.name}-{_timestamp()}")
    shutil.copytree(str(docs_dir), str(backup))
    return backup


def restore_docs(backup: Path, docs_dir: Path) -> None:
    if not backup.exists():
        return
    if docs_dir.exists():
        shutil.rmtree(str(docs_dir))
    shutil.move(str(backup), str(docs_dir))


def run_filter_repo(git_root: Path) -> None:
    cmd = [
        "git",
        "-C",
        str(git_root),
        "filter-repo",
        "--force",
        "--invert-paths",
    ]
    for path in KILL_LIST_PATHS:
        cmd += ["--path", path]
    for glob in KILL_LIST_GLOBS:
        cmd += ["--path-glob", glob]
    subprocess.run(cmd, check=True)


def move_project_org(docs_dir: Path, git_root: Path) -> None:
    src = docs_dir / "PROJECT.org"
    if not src.exists():
        return
    dst = git_root / "PROJECT.org"
    if dst.exists():
        print(
            f"WARN: {dst} already exists; leaving {src} in place. "
            "Merge the two manually if desired."
        )
        return
    shutil.move(str(src), str(dst))
    print(f"Moved {src.relative_to(git_root)} → {dst.relative_to(git_root)}")


def init_notes_repo(docs_dir: Path) -> None:
    subprocess.run(
        ["git", "-C", str(docs_dir), "init", "-q", "-b", "main"], check=True
    )
    # The nested repo inherits no config from the outer repo. Force signing
    # off here because we generate the initial commit unattended; a user
    # with global commit.gpgsign=true would otherwise see an interactive
    # prompt or a signing failure. Users who want signing on their notes
    # repo can re-enable it after the fact.
    subprocess.run(
        ["git", "-C", str(docs_dir), "config", "commit.gpgsign", "false"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(docs_dir), "config", "tag.gpgsign", "false"],
        check=True,
    )
    subprocess.run(["git", "-C", str(docs_dir), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(docs_dir),
            "commit",
            "-q",
            "-m",
            "initial notes snapshot",
        ],
        check=True,
    )


def untrack_docs_from_outer(git_root: Path) -> None:
    """Remove any previously-tracked docs/* paths from the outer index.

    `.gitignore` does not untrack already-tracked files. Without this step,
    a project whose docs/ used to be tracked would keep those files in the
    outer history after publish — exactly the leak the flip is meant to
    prevent. `--ignore-unmatch` makes this a no-op if nothing under docs/
    is currently indexed.
    """
    subprocess.run(
        [
            "git",
            "-C",
            str(git_root),
            "rm",
            "-r",
            "--cached",
            "--quiet",
            "--ignore-unmatch",
            "docs/",
        ],
        check=True,
    )


def update_outer_gitignore(git_root: Path) -> None:
    gitignore = git_root / ".gitignore"
    existing = gitignore.read_text() if gitignore.exists() else ""
    if PUBLISH_GITIGNORE_MARKER in existing:
        return
    kept_lines = [
        line
        for line in existing.splitlines()
        if line.strip() not in LEGACY_SCRUB_LINES
    ]
    content = "\n".join(kept_lines).rstrip() + "\n" + PUBLISH_GITIGNORE_BLOCK
    gitignore.write_text(content)


def commit_outer(git_root: Path, *, scrubbed: bool) -> None:
    # Stage explicit paths rather than `git add -A`. Once docs/ is both
    # gitignored and has a nested .git dir, `add -A` is safe in theory
    # (gitignore blocks recursion) but relies on two rules aligning — any
    # bug there and we could end up adding docs as a submodule pointer or
    # re-staging private files. Explicit is cheap and auditable.
    subprocess.run(
        ["git", "-C", str(git_root), "add", ".gitignore"], check=True
    )
    # Pick up tracked-file deletions (notably docs/PROJECT.org removed by
    # the move) and modifications. `-u` does not add new untracked files.
    subprocess.run(["git", "-C", str(git_root), "add", "-u"], check=True)
    if (git_root / "PROJECT.org").exists():
        subprocess.run(
            ["git", "-C", str(git_root), "add", "PROJECT.org"], check=True
        )
    diff = subprocess.run(
        ["git", "-C", str(git_root), "diff", "--cached", "--quiet"]
    )
    if diff.returncode == 0:
        return  # nothing to commit
    msg = (
        "chore(publish): flip to public-notes mode (post-scrub)"
        if scrubbed
        else "chore(publish): flip to public-notes mode"
    )
    subprocess.run(
        ["git", "-C", str(git_root), "commit", "-q", "-m", msg], check=True
    )


def _timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
