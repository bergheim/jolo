"""Git worktree operations for jolo."""

import shutil
import subprocess
import sys
from pathlib import Path

from _jolo.cli import find_git_root, get_container_name, verbose_cmd
from _jolo.setup import add_worktree_git_mount, scaffold_devcontainer


def get_worktree_path(project_path: str, worktree_name: str) -> Path:
    """Compute worktree path: ../PROJECT-worktrees/NAME."""
    project_path = Path(project_path.rstrip("/"))
    project_name = project_path.name
    worktrees_dir = project_path.parent / f"{project_name}-worktrees"
    return worktrees_dir / worktree_name


def validate_tree_mode() -> Path:
    """Validate that --tree mode is being run inside a git repo.

    Returns the git root path.
    """
    git_root = find_git_root()
    if git_root is None:
        sys.exit("Error: Not in a git repository. --tree requires an existing repo.")
    return git_root


def validate_create_mode(name: str) -> None:
    """Validate that --create mode is NOT being run inside a git repo."""
    git_root = find_git_root()
    if git_root is not None:
        sys.exit("Error: Already in a git repository. Use --tree for worktrees.")

    target_dir = Path.cwd() / name
    if target_dir.exists():
        sys.exit(f"Error: Directory already exists: {target_dir}")


def validate_init_mode() -> None:
    """Validate that --init mode is NOT being run inside a git repo."""
    git_root = find_git_root()
    if git_root is not None:
        sys.exit("Error: Already in a git repository. Use jolo without --init.")


def list_worktrees(git_root: Path) -> list[tuple[Path, str, str]]:
    """List git worktrees for a repository.

    Returns list of tuples: (path, commit, branch)
    """
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=git_root,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return []

    worktrees = []
    current_worktree = {}

    for line in result.stdout.strip().split("\n"):
        if not line:
            if current_worktree:
                worktrees.append(
                    (
                        Path(current_worktree.get("worktree", "")),
                        current_worktree.get("HEAD", "")[:7],
                        current_worktree.get("branch", "").replace("refs/heads/", ""),
                    )
                )
                current_worktree = {}
            continue

        if line.startswith("worktree "):
            current_worktree["worktree"] = line[9:]
        elif line.startswith("HEAD "):
            current_worktree["HEAD"] = line[5:]
        elif line.startswith("branch "):
            current_worktree["branch"] = line[7:]

    # Don't forget last worktree
    if current_worktree:
        worktrees.append(
            (
                Path(current_worktree.get("worktree", "")),
                current_worktree.get("HEAD", "")[:7],
                current_worktree.get("branch", "").replace("refs/heads/", ""),
            )
        )

    return worktrees


def find_project_workspaces(git_root: Path) -> list[tuple[Path, str]]:
    """Find all workspace directories for a project.

    Returns list of tuples: (path, type) where type is 'main' or worktree name.
    """
    project_name = git_root.name
    workspaces = [(git_root, "main")]

    # Check for worktrees directory
    worktrees_dir = git_root.parent / f"{project_name}-worktrees"
    if worktrees_dir.exists():
        worktrees = list_worktrees(git_root)
        for wt_path, _, branch in worktrees:
            if wt_path != git_root:
                workspaces.append((wt_path, branch or wt_path.name))

    return workspaces


def find_stale_worktrees(git_root: Path) -> list[tuple[Path, str]]:
    """Find worktrees that no longer exist on disk.

    Returns list of tuples: (worktree_path, branch_name)
    """
    worktrees = list_worktrees(git_root)
    stale = []

    for wt_path, _, branch in worktrees:
        if wt_path == git_root:
            continue  # Skip main repo
        if not wt_path.exists():
            stale.append((wt_path, branch))

    return stale


def remove_worktree(git_root: Path, worktree_path: Path) -> bool:
    """Remove a git worktree."""
    cmd = ["git", "worktree", "remove", "--force", str(worktree_path)]
    verbose_cmd(cmd)
    result = subprocess.run(cmd, cwd=git_root, capture_output=True, text=True)
    return result.returncode == 0


def branch_exists(git_root: Path, branch: str) -> bool:
    """Check if a branch or ref exists in the repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch], cwd=git_root, capture_output=True
    )
    return result.returncode == 0


def get_or_create_worktree(
    git_root: Path,
    worktree_name: str,
    worktree_path: Path,
    config: dict | None = None,
    from_branch: str | None = None,
) -> Path:
    """Get existing worktree or create a new one.

    Returns the worktree path. If the worktree already exists, just returns
    the path. If it doesn't exist, creates the worktree with devcontainer.

    If from_branch is specified, creates the worktree from that branch.
    """
    if worktree_path.exists():
        print(f"Using existing worktree: {worktree_path}")
        return worktree_path

    # Create worktrees directory if needed
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    # Create git worktree with new branch
    cmd = ["git", "worktree", "add", "-b", worktree_name, str(worktree_path)]
    if from_branch:
        cmd.append(from_branch)

    verbose_cmd(cmd)
    result = subprocess.run(cmd, cwd=git_root)
    if result.returncode != 0:
        sys.exit("Error: Failed to create git worktree")

    # Set up .devcontainer in worktree
    src_devcontainer = git_root / ".devcontainer"
    dst_devcontainer = worktree_path / ".devcontainer"

    if dst_devcontainer.exists():
        # Already checked out by git worktree (was committed to repo)
        pass
    elif src_devcontainer.exists():
        # Copy from main repo (not committed, just local)
        shutil.copytree(src_devcontainer, dst_devcontainer, symlinks=True)
    else:
        # Scaffold new .devcontainer
        container_name = get_container_name(str(git_root), worktree_name)
        scaffold_devcontainer(container_name, worktree_path, config=config)

    # Add mount for main repo's .git directory so worktree git operations work
    main_git_dir = git_root / ".git"
    devcontainer_json = dst_devcontainer / "devcontainer.json"
    add_worktree_git_mount(devcontainer_json, main_git_dir)

    print(f"Created worktree: {worktree_path}")
    print(f"Branch: {worktree_name}")

    return worktree_path
