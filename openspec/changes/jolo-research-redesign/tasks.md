## 1. Add config and helper

- [ ] 1.1 Add `"research_home": "~/jolo/research"` to `DEFAULT_CONFIG` in `_jolo/constants.py`
- [ ] 1.2 Add `slugify_prompt(prompt, max_len=50)` to `_jolo/cli.py` — lowercase, non-alnum to hyphens, collapse, truncate, fallback to "research"
- [ ] 1.3 Export `slugify_prompt` from `_jolo/__init__.py`

## 2. Add ensure_research_repo()

- [ ] 2.1 Add `ensure_research_repo(config)` to `_jolo/commands.py` — expand path, return if `.git` exists, otherwise: `mkdir -p`, `git init`, `scaffold_devcontainer("research", ...)`, copy research skill from templates, initial commit
- [ ] 2.2 Export `ensure_research_repo` from `_jolo/__init__.py`

## 3. Rewrite run_research_mode()

- [ ] 3.1 Remove `validate_tree_mode()` call, replace with `ensure_research_repo(config)`
- [ ] 3.2 Pick agent: `--agent` override, round-robin from config, or fallback "claude"
- [ ] 3.3 Generate filename: `date.today().isoformat()-slugify_prompt(args.prompt).org`
- [ ] 3.4 Run credential/hook/emacs setup on research repo (idempotent)
- [ ] 3.5 Start container if not running: `is_container_running()` check, then `devcontainer_up()`
- [ ] 3.6 Build prompt: `/research Write findings to {filename}. Question: {args.prompt}`
- [ ] 3.7 Fire and forget: `devcontainer_exec_command()` with `nohup agent -p "..." &`
- [ ] 3.8 Handle `--topic` ntfy override (patch `devcontainer.json` before first container start)
- [ ] 3.9 Print confirmation with agent name and filename

## 4. Delete old machinery

- [ ] 4.1 Delete `_spawn_research_watcher()` from `_jolo/commands.py`
- [ ] 4.2 Delete research mode block from `container/tmux-layout.sh` (RESEARCH_FILE detection, RESEARCH_MODE flag, wrapper script, minimal YAML config)
- [ ] 4.3 Remove watcher-related imports if now unused (`shlex` may still be used elsewhere)

## 5. Update research skill template

- [ ] 5.1 Update `templates/.agents/skills/research/SKILL.md` — if prompt specifies a filename, write to that file instead of `RESEARCH.org`. Each file is standalone with `#+TITLE:` (question) and `#+PROPERTY: PROMPT` (original prompt)
- [ ] 5.2 Update `templates/.agents/skills/research/agents/openai.yaml` default_prompt

## 6. Update tests

- [ ] 6.1 Rewrite `tests/test_research.py` — mock `ensure_research_repo`, `is_container_running`, `devcontainer_up`, `devcontainer_exec_command` instead of worktree/watcher mocks
- [ ] 6.2 Test: `slugify_prompt` with various inputs (spaces, punctuation, long strings, empty)
- [ ] 6.3 Test: `ensure_research_repo` creates repo on first run, reuses on second
- [ ] 6.4 Test: exec command includes correct agent, filename, and prompt
- [ ] 6.5 Test: container started only if not already running
- [ ] 6.6 Test: agent selection (explicit, round-robin, empty fallback)
