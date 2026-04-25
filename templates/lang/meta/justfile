# jolo meta-project tasks

# run all tests
test *args:
    uv run --with pytest pytest tests/ {{args}}

# run tests matching a keyword
test-k pattern:
    uv run --with pytest pytest tests/ -k '{{pattern}}' -v

# run tests with verbose output
test-v *args:
    uv run --with pytest pytest tests/ -v {{args}}

# lint python files
lint:
    ruff check _jolo/ jolo.py

# lint and fix
lint-fix:
    ruff check --fix _jolo/ jolo.py

# format python files
fmt:
    ruff format _jolo/ jolo.py tests/

# format check (no changes)
fmt-check:
    ruff format --check _jolo/ jolo.py tests/

# lint + format + test
check: lint fmt-check test

# worktree manager (in-container): wt new, wt ls, wt rm, wt main
wt *args:
    wt {{args}}

# build the container image
build:
    podman build --build-arg USERNAME=$(whoami) --build-arg USER_ID=$(id -u) --build-arg GROUP_ID=$(id -g) -t emacs-gui .
