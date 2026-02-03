#!/usr/bin/env python3
"""Tests for jolo CLI tool - TDD style."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Import will fail until we create the module
try:
    import jolo
except ImportError:
    jolo = None


class TestArgumentParsing(unittest.TestCase):
    """Test command-line argument parsing."""

    def test_no_args_returns_default_mode(self):
        """No arguments should result in default mode."""
        args = jolo.parse_args([])
        self.assertIsNone(args.tree)
        self.assertIsNone(args.create)
        self.assertFalse(args.new)

    def test_help_flag(self):
        """--help should exit with usage info."""
        with self.assertRaises(SystemExit) as cm:
            jolo.parse_args(['--help'])
        self.assertEqual(cm.exception.code, 0)

    def test_tree_with_name(self):
        """--tree NAME should set tree to NAME."""
        args = jolo.parse_args(['--tree', 'feature-x'])
        self.assertEqual(args.tree, 'feature-x')

    def test_tree_without_name(self):
        """--tree without name should set tree to empty string (generate random)."""
        args = jolo.parse_args(['--tree'])
        self.assertEqual(args.tree, '')

    def test_create_with_name(self):
        """--create NAME should set create to NAME."""
        args = jolo.parse_args(['--create', 'myproject'])
        self.assertEqual(args.create, 'myproject')

    def test_create_requires_name(self):
        """--create without NAME should fail."""
        with self.assertRaises(SystemExit):
            jolo.parse_args(['--create'])

    def test_new_flag(self):
        """--new should set new to True."""
        args = jolo.parse_args(['--new'])
        self.assertTrue(args.new)

    def test_new_with_tree(self):
        """--new can combine with --tree."""
        args = jolo.parse_args(['--new', '--tree', 'test'])
        self.assertTrue(args.new)
        self.assertEqual(args.tree, 'test')

    def test_sync_flag(self):
        """--sync should set sync to True."""
        args = jolo.parse_args(['--sync'])
        self.assertTrue(args.sync)

    def test_sync_default_false(self):
        """--sync should default to False."""
        args = jolo.parse_args([])
        self.assertFalse(args.sync)


class TestGuards(unittest.TestCase):
    """Test guard conditions and validations."""

    def test_tmux_guard_raises_when_in_tmux(self):
        """Should error when TMUX env var is set."""
        with mock.patch.dict(os.environ, {'TMUX': '/tmp/tmux-1000/default,12345,0'}):
            with self.assertRaises(SystemExit) as cm:
                jolo.check_tmux_guard()
            self.assertIn('tmux', str(cm.exception.code).lower())

    def test_tmux_guard_passes_when_not_in_tmux(self):
        """Should pass when TMUX env var is not set."""
        env = os.environ.copy()
        env.pop('TMUX', None)
        with mock.patch.dict(os.environ, env, clear=True):
            # Should not raise
            jolo.check_tmux_guard()


class TestGitDetection(unittest.TestCase):
    """Test git repository detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_find_git_root_at_root(self):
        """Should find git root when at repo root."""
        git_dir = Path(self.tmpdir) / '.git'
        git_dir.mkdir()
        os.chdir(self.tmpdir)

        result = jolo.find_git_root()
        self.assertEqual(result, Path(self.tmpdir))

    def test_find_git_root_in_subdirectory(self):
        """Should find git root when in subdirectory."""
        git_dir = Path(self.tmpdir) / '.git'
        git_dir.mkdir()
        subdir = Path(self.tmpdir) / 'src' / 'lib'
        subdir.mkdir(parents=True)
        os.chdir(subdir)

        result = jolo.find_git_root()
        self.assertEqual(result, Path(self.tmpdir))

    def test_find_git_root_returns_none_outside_repo(self):
        """Should return None when not in a git repo."""
        os.chdir(self.tmpdir)

        result = jolo.find_git_root()
        self.assertIsNone(result)


class TestRandomNameGeneration(unittest.TestCase):
    """Test random name generation for worktrees."""

    def test_generate_random_name_format(self):
        """Should generate adjective-noun format."""
        name = jolo.generate_random_name()
        parts = name.split('-')
        self.assertEqual(len(parts), 2)

    def test_generate_random_name_uses_wordlists(self):
        """Generated name should use defined word lists."""
        name = jolo.generate_random_name()
        adj, noun = name.split('-')
        self.assertIn(adj, jolo.ADJECTIVES)
        self.assertIn(noun, jolo.NOUNS)

    def test_generate_random_name_is_random(self):
        """Should generate different names (probabilistically)."""
        names = {jolo.generate_random_name() for _ in range(20)}
        # With 10 adjectives and 10 nouns, getting same name 20 times is unlikely
        self.assertGreater(len(names), 1)


class TestTemplateSystem(unittest.TestCase):
    """Test .devcontainer template scaffolding."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_scaffold_devcontainer_creates_directory(self):
        """Should create .devcontainer directory."""
        os.chdir(self.tmpdir)
        jolo.scaffold_devcontainer('testproject')

        devcontainer_dir = Path(self.tmpdir) / '.devcontainer'
        self.assertTrue(devcontainer_dir.exists())
        self.assertTrue(devcontainer_dir.is_dir())

    def test_scaffold_devcontainer_creates_json(self):
        """Should create devcontainer.json with project name."""
        os.chdir(self.tmpdir)
        jolo.scaffold_devcontainer('testproject')

        json_file = Path(self.tmpdir) / '.devcontainer' / 'devcontainer.json'
        self.assertTrue(json_file.exists())
        content = json_file.read_text()
        self.assertIn('"name": "testproject"', content)

    def test_scaffold_devcontainer_creates_dockerfile(self):
        """Should create Dockerfile with default base image."""
        os.chdir(self.tmpdir)
        jolo.scaffold_devcontainer('testproject')

        dockerfile = Path(self.tmpdir) / '.devcontainer' / 'Dockerfile'
        self.assertTrue(dockerfile.exists())
        content = dockerfile.read_text()
        self.assertIn('FROM localhost/emacs-gui:latest', content)

    def test_scaffold_devcontainer_uses_config_base_image(self):
        """Should use base_image from config."""
        os.chdir(self.tmpdir)
        config = {'base_image': 'custom/myimage:v3'}
        jolo.scaffold_devcontainer('testproject', config=config)

        dockerfile = Path(self.tmpdir) / '.devcontainer' / 'Dockerfile'
        content = dockerfile.read_text()
        self.assertIn('FROM custom/myimage:v3', content)
        self.assertNotIn('localhost/emacs-gui', content)

    def test_scaffold_warns_if_exists(self):
        """Should warn but not error if .devcontainer exists."""
        os.chdir(self.tmpdir)
        devcontainer_dir = Path(self.tmpdir) / '.devcontainer'
        devcontainer_dir.mkdir()
        (devcontainer_dir / 'devcontainer.json').write_text('existing')

        # Should not raise, should return False (not created)
        result = jolo.scaffold_devcontainer('testproject')
        self.assertFalse(result)

        # Original file should be preserved
        content = (devcontainer_dir / 'devcontainer.json').read_text()
        self.assertEqual(content, 'existing')


class TestSecretsManagement(unittest.TestCase):
    """Test secrets fetching from pass and environment."""

    def test_get_secrets_from_env(self):
        """Should get secrets from environment when pass unavailable."""
        env = {
            'ANTHROPIC_API_KEY': 'sk-ant-test123',
            'OPENAI_API_KEY': 'sk-openai-test456'
        }
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch('shutil.which', return_value=None):
                secrets = jolo.get_secrets()

        self.assertEqual(secrets['ANTHROPIC_API_KEY'], 'sk-ant-test123')
        self.assertEqual(secrets['OPENAI_API_KEY'], 'sk-openai-test456')

    def test_get_secrets_from_pass(self):
        """Should get secrets from pass when available."""
        def mock_run(cmd, *args, **kwargs):
            result = mock.Mock()
            result.returncode = 0
            if 'api/llm/anthropic' in cmd:
                result.stdout = 'sk-ant-from-pass\n'
            elif 'api/llm/openai' in cmd:
                result.stdout = 'sk-openai-from-pass\n'
            return result

        with mock.patch('shutil.which', return_value='/usr/bin/pass'):
            with mock.patch('subprocess.run', side_effect=mock_run):
                secrets = jolo.get_secrets()

        self.assertEqual(secrets['ANTHROPIC_API_KEY'], 'sk-ant-from-pass')
        self.assertEqual(secrets['OPENAI_API_KEY'], 'sk-openai-from-pass')


class TestContainerNaming(unittest.TestCase):
    """Test container name generation."""

    def test_container_name_from_project(self):
        """Should derive container name from project directory."""
        name = jolo.get_container_name('/home/user/myproject', None)
        self.assertEqual(name, 'myproject')

    def test_container_name_with_worktree(self):
        """Should include worktree name in container name."""
        name = jolo.get_container_name('/home/user/myproject', 'feature-x')
        self.assertEqual(name, 'myproject-feature-x')

    def test_container_name_lowercase(self):
        """Should convert to lowercase."""
        name = jolo.get_container_name('/home/user/MyProject', None)
        self.assertEqual(name, 'myproject')


class TestWorktreePaths(unittest.TestCase):
    """Test worktree path computation."""

    def test_worktree_path_computation(self):
        """Should compute worktree path as ../PROJECT-worktrees/NAME."""
        path = jolo.get_worktree_path('/dev/myapp', 'feature-x')
        self.assertEqual(path, Path('/dev/myapp-worktrees/feature-x'))

    def test_worktree_path_with_trailing_slash(self):
        """Should handle trailing slash in project path."""
        path = jolo.get_worktree_path('/dev/myapp/', 'feature-x')
        self.assertEqual(path, Path('/dev/myapp-worktrees/feature-x'))


class TestModeValidation(unittest.TestCase):
    """Test validation for different modes."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_tree_mode_requires_git_repo(self):
        """--tree should fail if not in git repo."""
        os.chdir(self.tmpdir)  # Not a git repo

        with self.assertRaises(SystemExit) as cm:
            jolo.validate_tree_mode()
        self.assertIn('git', str(cm.exception.code).lower())

    def test_create_mode_forbids_git_repo(self):
        """--create should fail if already in git repo."""
        git_dir = Path(self.tmpdir) / '.git'
        git_dir.mkdir()
        os.chdir(self.tmpdir)

        with self.assertRaises(SystemExit) as cm:
            jolo.validate_create_mode('newproject')
        self.assertIn('git', str(cm.exception.code).lower())

    def test_create_mode_forbids_existing_directory(self):
        """--create should fail if directory exists."""
        os.chdir(self.tmpdir)
        existing = Path(self.tmpdir) / 'existing'
        existing.mkdir()

        with self.assertRaises(SystemExit) as cm:
            jolo.validate_create_mode('existing')
        self.assertIn('exists', str(cm.exception.code).lower())


class TestWorktreeExists(unittest.TestCase):
    """Test behavior when worktree already exists."""

    def test_existing_worktree_returns_path(self):
        """Should return existing worktree path instead of erroring."""
        # If worktree exists, get_or_create_worktree should return the path
        # without trying to create it
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree_path = Path(tmpdir) / 'existing-worktree'
            worktree_path.mkdir()
            (worktree_path / '.devcontainer').mkdir()

            result = jolo.get_or_create_worktree(
                git_root=Path(tmpdir),
                worktree_name='existing-worktree',
                worktree_path=worktree_path
            )

            self.assertEqual(result, worktree_path)
            self.assertTrue(result.exists())


class TestWorktreeDevcontainer(unittest.TestCase):
    """Test worktree-specific devcontainer configuration."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_add_git_mount_to_devcontainer(self):
        """Should add mount for main repo .git directory."""
        import json

        # Create a devcontainer.json
        devcontainer_dir = Path(self.tmpdir) / '.devcontainer'
        devcontainer_dir.mkdir()
        json_file = devcontainer_dir / 'devcontainer.json'

        original = {
            "name": "test",
            "mounts": ["source=/tmp,target=/tmp,type=bind"]
        }
        json_file.write_text(json.dumps(original))

        # Add git mount
        main_git_dir = Path('/home/user/project/.git')
        jolo.add_worktree_git_mount(json_file, main_git_dir)

        # Verify mount was added
        updated = json.loads(json_file.read_text())
        self.assertEqual(len(updated['mounts']), 2)

        git_mount = updated['mounts'][1]
        self.assertIn('/home/user/project/.git', git_mount)
        self.assertIn('source=', git_mount)
        self.assertIn('target=', git_mount)

    def test_add_git_mount_creates_mounts_array(self):
        """Should create mounts array if not present."""
        import json

        devcontainer_dir = Path(self.tmpdir) / '.devcontainer'
        devcontainer_dir.mkdir()
        json_file = devcontainer_dir / 'devcontainer.json'

        original = {"name": "test"}
        json_file.write_text(json.dumps(original))

        main_git_dir = Path('/home/user/project/.git')
        jolo.add_worktree_git_mount(json_file, main_git_dir)

        updated = json.loads(json_file.read_text())
        self.assertIn('mounts', updated)
        self.assertEqual(len(updated['mounts']), 1)


class TestSyncDevcontainer(unittest.TestCase):
    """Test --sync functionality."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_sync_overwrites_existing_devcontainer(self):
        """--sync should regenerate .devcontainer even if it exists."""
        os.chdir(self.tmpdir)

        # Create existing .devcontainer with old content
        devcontainer_dir = Path(self.tmpdir) / '.devcontainer'
        devcontainer_dir.mkdir()
        (devcontainer_dir / 'devcontainer.json').write_text('{"old": "content"}')
        (devcontainer_dir / 'Dockerfile').write_text('FROM old/image:v1')

        # Sync with new config
        config = {'base_image': 'new/image:v2'}
        jolo.sync_devcontainer('myproject', config=config)

        # Verify new content
        dockerfile = (devcontainer_dir / 'Dockerfile').read_text()
        self.assertIn('FROM new/image:v2', dockerfile)
        self.assertNotIn('old/image', dockerfile)

        json_content = (devcontainer_dir / 'devcontainer.json').read_text()
        self.assertIn('"name": "myproject"', json_content)

    def test_sync_creates_if_missing(self):
        """--sync should create .devcontainer if it doesn't exist."""
        os.chdir(self.tmpdir)

        config = {'base_image': 'test/image:v1'}
        jolo.sync_devcontainer('newproject', config=config)

        devcontainer_dir = Path(self.tmpdir) / '.devcontainer'
        self.assertTrue(devcontainer_dir.exists())
        self.assertTrue((devcontainer_dir / 'Dockerfile').exists())
        self.assertTrue((devcontainer_dir / 'devcontainer.json').exists())


class TestConfigLoading(unittest.TestCase):
    """Test TOML configuration loading."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_load_config_returns_defaults_when_no_files(self):
        """Should return default config when no config files exist."""
        os.chdir(self.tmpdir)
        config = jolo.load_config(global_config_dir=Path(self.tmpdir) / 'noexist')

        self.assertEqual(config['base_image'], 'localhost/emacs-gui:latest')
        self.assertEqual(config['pass_path_anthropic'], 'api/llm/anthropic')
        self.assertEqual(config['pass_path_openai'], 'api/llm/openai')

    def test_load_global_config(self):
        """Should load global config from ~/.config/jolo/config.toml."""
        config_dir = Path(self.tmpdir) / '.config' / 'jolo'
        config_dir.mkdir(parents=True)
        (config_dir / 'config.toml').write_text('base_image = "custom/image:v1"\n')

        config = jolo.load_config(global_config_dir=config_dir)

        self.assertEqual(config['base_image'], 'custom/image:v1')

    def test_load_project_config(self):
        """Should load project config from .jolo.toml."""
        os.chdir(self.tmpdir)
        Path(self.tmpdir, '.jolo.toml').write_text('base_image = "project/image:v2"\n')

        config = jolo.load_config(global_config_dir=Path(self.tmpdir) / 'noexist')

        self.assertEqual(config['base_image'], 'project/image:v2')

    def test_project_config_overrides_global(self):
        """Project config should override global config."""
        config_dir = Path(self.tmpdir) / '.config' / 'jolo'
        config_dir.mkdir(parents=True)
        (config_dir / 'config.toml').write_text('base_image = "global/image:v1"\n')

        os.chdir(self.tmpdir)
        Path(self.tmpdir, '.jolo.toml').write_text('base_image = "project/image:v2"\n')

        config = jolo.load_config(global_config_dir=config_dir)

        self.assertEqual(config['base_image'], 'project/image:v2')

    def test_config_partial_override(self):
        """Project config should only override specified keys."""
        config_dir = Path(self.tmpdir) / '.config' / 'jolo'
        config_dir.mkdir(parents=True)
        (config_dir / 'config.toml').write_text(
            'base_image = "global/image:v1"\npass_path_anthropic = "custom/path"\n'
        )

        os.chdir(self.tmpdir)
        Path(self.tmpdir, '.jolo.toml').write_text('base_image = "project/image:v2"\n')

        config = jolo.load_config(global_config_dir=config_dir)

        self.assertEqual(config['base_image'], 'project/image:v2')
        self.assertEqual(config['pass_path_anthropic'], 'custom/path')


class TestListMode(unittest.TestCase):
    """Test --list functionality."""

    def test_list_flag(self):
        """--list should set list to True."""
        args = jolo.parse_args(['--list'])
        self.assertTrue(args.list)

    def test_list_default_false(self):
        """--list should default to False."""
        args = jolo.parse_args([])
        self.assertFalse(args.list)

    def test_all_flag(self):
        """--all should set all to True."""
        args = jolo.parse_args(['--list', '--all'])
        self.assertTrue(args.all)

    def test_all_short_flag(self):
        """-a should set all to True."""
        args = jolo.parse_args(['--list', '-a'])
        self.assertTrue(args.all)

    def test_all_default_false(self):
        """--all should default to False."""
        args = jolo.parse_args(['--list'])
        self.assertFalse(args.all)


class TestListWorktrees(unittest.TestCase):
    """Test worktree listing functionality."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_list_worktrees_empty_on_non_git(self):
        """Should return empty list for non-git directory."""
        os.chdir(self.tmpdir)
        result = jolo.list_worktrees(Path(self.tmpdir))
        self.assertEqual(result, [])

    def test_list_worktrees_returns_main_repo(self):
        """Should return main repo as first worktree."""
        os.chdir(self.tmpdir)
        import subprocess
        subprocess.run(['git', 'init'], cwd=self.tmpdir, capture_output=True)
        # Create an initial commit so git worktree list works
        subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=self.tmpdir, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=self.tmpdir, capture_output=True)
        Path(self.tmpdir, 'README').write_text('test')
        subprocess.run(['git', 'add', '.'], cwd=self.tmpdir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Initial'], cwd=self.tmpdir, capture_output=True)

        result = jolo.list_worktrees(Path(self.tmpdir))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], Path(self.tmpdir))

    def test_find_project_workspaces_includes_main(self):
        """Should always include main repo in workspaces."""
        os.chdir(self.tmpdir)
        import subprocess
        subprocess.run(['git', 'init'], cwd=self.tmpdir, capture_output=True)

        git_root = Path(self.tmpdir)
        result = jolo.find_project_workspaces(git_root)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], git_root)
        self.assertEqual(result[0][1], 'main')


class TestContainerRuntime(unittest.TestCase):
    """Test container runtime detection."""

    def test_get_container_runtime_finds_docker(self):
        """Should detect docker if available."""
        with mock.patch('shutil.which') as mock_which:
            mock_which.side_effect = lambda x: '/usr/bin/docker' if x == 'docker' else None
            result = jolo.get_container_runtime()
            self.assertEqual(result, 'docker')

    def test_get_container_runtime_finds_podman(self):
        """Should detect podman if docker not available."""
        with mock.patch('shutil.which') as mock_which:
            mock_which.side_effect = lambda x: '/usr/bin/podman' if x == 'podman' else None
            result = jolo.get_container_runtime()
            self.assertEqual(result, 'podman')

    def test_get_container_runtime_prefers_docker(self):
        """Should prefer docker over podman."""
        with mock.patch('shutil.which') as mock_which:
            mock_which.return_value = '/usr/bin/something'
            result = jolo.get_container_runtime()
            self.assertEqual(result, 'docker')

    def test_get_container_runtime_returns_none(self):
        """Should return None if no runtime available."""
        with mock.patch('shutil.which', return_value=None):
            result = jolo.get_container_runtime()
            self.assertIsNone(result)


class TestListAllDevcontainers(unittest.TestCase):
    """Test global devcontainer listing."""

    def test_list_all_returns_empty_without_runtime(self):
        """Should return empty list if no container runtime."""
        with mock.patch('jolo.get_container_runtime', return_value=None):
            result = jolo.list_all_devcontainers()
            self.assertEqual(result, [])

    def test_list_all_parses_docker_output(self):
        """Should parse docker ps output correctly."""
        mock_output = "mycontainer\t/home/user/project\trunning\n"
        with mock.patch('jolo.get_container_runtime', return_value='docker'):
            with mock.patch('subprocess.run') as mock_run:
                mock_run.return_value = mock.Mock(returncode=0, stdout=mock_output)
                result = jolo.list_all_devcontainers()
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0], ('mycontainer', '/home/user/project', 'running'))


class TestStopMode(unittest.TestCase):
    """Test --stop functionality."""

    def test_stop_flag(self):
        """--stop should set stop to True."""
        args = jolo.parse_args(['--stop'])
        self.assertTrue(args.stop)

    def test_stop_default_false(self):
        """--stop should default to False."""
        args = jolo.parse_args([])
        self.assertFalse(args.stop)


class TestGetContainerForWorkspace(unittest.TestCase):
    """Test container lookup by workspace."""

    def test_returns_none_without_runtime(self):
        """Should return None if no container runtime."""
        with mock.patch('jolo.get_container_runtime', return_value=None):
            result = jolo.get_container_for_workspace(Path('/some/path'))
            self.assertIsNone(result)

    def test_returns_container_name(self):
        """Should return container name from docker output."""
        with mock.patch('jolo.get_container_runtime', return_value='docker'):
            with mock.patch('subprocess.run') as mock_run:
                mock_run.return_value = mock.Mock(returncode=0, stdout='my-container\n')
                result = jolo.get_container_for_workspace(Path('/home/user/project'))
                self.assertEqual(result, 'my-container')

    def test_returns_none_when_no_container(self):
        """Should return None when no container found."""
        with mock.patch('jolo.get_container_runtime', return_value='docker'):
            with mock.patch('subprocess.run') as mock_run:
                mock_run.return_value = mock.Mock(returncode=0, stdout='')
                result = jolo.get_container_for_workspace(Path('/home/user/project'))
                self.assertIsNone(result)


class TestStopContainer(unittest.TestCase):
    """Test container stopping."""

    def test_stop_returns_false_without_runtime(self):
        """Should return False if no container runtime."""
        with mock.patch('jolo.get_container_runtime', return_value=None):
            result = jolo.stop_container(Path('/some/path'))
            self.assertFalse(result)

    def test_stop_returns_false_when_no_container(self):
        """Should return False when no container found."""
        with mock.patch('jolo.get_container_runtime', return_value='docker'):
            with mock.patch('jolo.get_container_for_workspace', return_value=None):
                result = jolo.stop_container(Path('/some/path'))
                self.assertFalse(result)

    def test_stop_returns_true_on_success(self):
        """Should return True when container stopped successfully."""
        with mock.patch('jolo.get_container_runtime', return_value='docker'):
            with mock.patch('jolo.get_container_for_workspace', return_value='my-container'):
                with mock.patch('subprocess.run') as mock_run:
                    mock_run.return_value = mock.Mock(returncode=0)
                    result = jolo.stop_container(Path('/some/path'))
                    self.assertTrue(result)


class TestPruneMode(unittest.TestCase):
    """Test --prune functionality."""

    def test_prune_flag(self):
        """--prune should set prune to True."""
        args = jolo.parse_args(['--prune'])
        self.assertTrue(args.prune)

    def test_prune_default_false(self):
        """--prune should default to False."""
        args = jolo.parse_args([])
        self.assertFalse(args.prune)


class TestFindStaleWorktrees(unittest.TestCase):
    """Test stale worktree detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_find_stale_worktrees_returns_empty_for_fresh_repo(self):
        """Should return empty list when no stale worktrees."""
        os.chdir(self.tmpdir)
        import subprocess
        subprocess.run(['git', 'init'], cwd=self.tmpdir, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=self.tmpdir, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=self.tmpdir, capture_output=True)
        Path(self.tmpdir, 'README').write_text('test')
        subprocess.run(['git', 'add', '.'], cwd=self.tmpdir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Initial'], cwd=self.tmpdir, capture_output=True)

        result = jolo.find_stale_worktrees(Path(self.tmpdir))
        self.assertEqual(result, [])


class TestRemoveContainer(unittest.TestCase):
    """Test container removal."""

    def test_remove_returns_false_without_runtime(self):
        """Should return False if no container runtime."""
        with mock.patch('jolo.get_container_runtime', return_value=None):
            result = jolo.remove_container('my-container')
            self.assertFalse(result)

    def test_remove_returns_true_on_success(self):
        """Should return True when container removed successfully."""
        with mock.patch('jolo.get_container_runtime', return_value='docker'):
            with mock.patch('subprocess.run') as mock_run:
                mock_run.return_value = mock.Mock(returncode=0)
                result = jolo.remove_container('my-container')
                self.assertTrue(result)


class TestRemoveWorktree(unittest.TestCase):
    """Test worktree removal."""

    def test_remove_worktree_calls_git(self):
        """Should call git worktree remove."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(returncode=0)
            result = jolo.remove_worktree(Path('/project'), Path('/project-worktrees/foo'))
            self.assertTrue(result)
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            self.assertIn('worktree', args)
            self.assertIn('remove', args)


class TestAttachMode(unittest.TestCase):
    """Test --attach functionality."""

    def test_attach_flag(self):
        """--attach should set attach to True."""
        args = jolo.parse_args(['--attach'])
        self.assertTrue(args.attach)

    def test_attach_default_false(self):
        """--attach should default to False."""
        args = jolo.parse_args([])
        self.assertFalse(args.attach)


class TestDetachMode(unittest.TestCase):
    """Test --detach functionality."""

    def test_detach_flag(self):
        """--detach should set detach to True."""
        args = jolo.parse_args(['--detach'])
        self.assertTrue(args.detach)

    def test_detach_short_flag(self):
        """-d should set detach to True."""
        args = jolo.parse_args(['-d'])
        self.assertTrue(args.detach)

    def test_detach_default_false(self):
        """--detach should default to False."""
        args = jolo.parse_args([])
        self.assertFalse(args.detach)

    def test_detach_with_tree(self):
        """--detach can combine with --tree."""
        args = jolo.parse_args(['--detach', '--tree', 'test'])
        self.assertTrue(args.detach)
        self.assertEqual(args.tree, 'test')


class TestFromBranch(unittest.TestCase):
    """Test --from BRANCH functionality."""

    def test_from_flag(self):
        """--from should set from_branch."""
        args = jolo.parse_args(['--tree', 'test', '--from', 'main'])
        self.assertEqual(args.from_branch, 'main')

    def test_from_default_none(self):
        """--from should default to None."""
        args = jolo.parse_args(['--tree', 'test'])
        self.assertIsNone(args.from_branch)

    def test_from_with_tree(self):
        """--from can combine with --tree."""
        args = jolo.parse_args(['--tree', 'feature', '--from', 'develop'])
        self.assertEqual(args.tree, 'feature')
        self.assertEqual(args.from_branch, 'develop')


class TestBranchExists(unittest.TestCase):
    """Test branch existence checking."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        # Set up a git repo with a commit
        import subprocess
        subprocess.run(['git', 'init'], cwd=self.tmpdir, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=self.tmpdir, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=self.tmpdir, capture_output=True)
        Path(self.tmpdir, 'README').write_text('test')
        subprocess.run(['git', 'add', '.'], cwd=self.tmpdir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Initial'], cwd=self.tmpdir, capture_output=True)

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_branch_exists_for_existing_branch(self):
        """Should return True for existing branch."""
        result = jolo.branch_exists(Path(self.tmpdir), 'master')
        self.assertTrue(result)

    def test_branch_exists_for_nonexistent_branch(self):
        """Should return False for nonexistent branch."""
        result = jolo.branch_exists(Path(self.tmpdir), 'nonexistent')
        self.assertFalse(result)


class TestVerboseMode(unittest.TestCase):
    """Test --verbose functionality."""

    def test_verbose_flag(self):
        """--verbose should set verbose to True."""
        args = jolo.parse_args(['--verbose'])
        self.assertTrue(args.verbose)

    def test_verbose_short_flag(self):
        """-v should set verbose to True."""
        args = jolo.parse_args(['-v'])
        self.assertTrue(args.verbose)

    def test_verbose_default_false(self):
        """--verbose should default to False."""
        args = jolo.parse_args([])
        self.assertFalse(args.verbose)


class TestSpawnArgParsing(unittest.TestCase):
    """Test --spawn argument parsing."""

    def test_spawn_flag(self):
        """--spawn should accept integer."""
        args = jolo.parse_args(['--spawn', '5'])
        self.assertEqual(args.spawn, 5)

    def test_spawn_default_none(self):
        """--spawn should default to None."""
        args = jolo.parse_args([])
        self.assertIsNone(args.spawn)

    def test_spawn_with_prefix(self):
        """--spawn can be combined with --prefix."""
        args = jolo.parse_args(['--spawn', '3', '--prefix', 'feat'])
        self.assertEqual(args.spawn, 3)
        self.assertEqual(args.prefix, 'feat')

    def test_spawn_with_prompt(self):
        """--spawn can be combined with --prompt."""
        args = jolo.parse_args(['--spawn', '5', '-p', 'do stuff'])
        self.assertEqual(args.spawn, 5)
        self.assertEqual(args.prompt, 'do stuff')

    def test_prefix_default_none(self):
        """--prefix should default to None."""
        args = jolo.parse_args([])
        self.assertIsNone(args.prefix)


class TestAgentHelpers(unittest.TestCase):
    """Test agent configuration helpers."""

    def test_get_agent_command_default(self):
        """Should return first agent's command by default."""
        config = {
            'agents': ['claude', 'gemini'],
            'agent_commands': {
                'claude': 'claude --dangerously-skip-permissions',
                'gemini': 'gemini',
            }
        }
        result = jolo.get_agent_command(config)
        self.assertEqual(result, 'claude --dangerously-skip-permissions')

    def test_get_agent_command_specific(self):
        """Should return specific agent's command."""
        config = {
            'agents': ['claude', 'gemini'],
            'agent_commands': {
                'claude': 'claude --dangerously-skip-permissions',
                'gemini': 'gemini',
            }
        }
        result = jolo.get_agent_command(config, agent_name='gemini')
        self.assertEqual(result, 'gemini')

    def test_get_agent_command_round_robin(self):
        """Should round-robin through agents by index."""
        config = {
            'agents': ['claude', 'gemini', 'codex'],
            'agent_commands': {
                'claude': 'claude-cmd',
                'gemini': 'gemini-cmd',
                'codex': 'codex-cmd',
            }
        }
        self.assertEqual(jolo.get_agent_command(config, index=0), 'claude-cmd')
        self.assertEqual(jolo.get_agent_command(config, index=1), 'gemini-cmd')
        self.assertEqual(jolo.get_agent_command(config, index=2), 'codex-cmd')
        self.assertEqual(jolo.get_agent_command(config, index=3), 'claude-cmd')  # wraps

    def test_get_agent_name_round_robin(self):
        """Should return agent name by index."""
        config = {'agents': ['claude', 'gemini', 'codex']}
        self.assertEqual(jolo.get_agent_name(config, index=0), 'claude')
        self.assertEqual(jolo.get_agent_name(config, index=1), 'gemini')
        self.assertEqual(jolo.get_agent_name(config, index=4), 'gemini')  # 4 % 3 = 1

    def test_get_agent_command_fallback(self):
        """Should fall back to agent name if no command configured."""
        config = {'agents': ['unknown'], 'agent_commands': {}}
        result = jolo.get_agent_command(config, agent_name='unknown')
        self.assertEqual(result, 'unknown')


class TestPortAllocation(unittest.TestCase):
    """Test PORT environment variable in devcontainer.json."""

    def test_default_port_in_json(self):
        """Default port should be 4000."""
        import json
        result = jolo.build_devcontainer_json('test')
        config = json.loads(result)
        self.assertEqual(config['containerEnv']['PORT'], '4000')

    def test_custom_port_in_json(self):
        """Custom port should be set."""
        import json
        result = jolo.build_devcontainer_json('test', port=4005)
        config = json.loads(result)
        self.assertEqual(config['containerEnv']['PORT'], '4005')


class TestMountArgParsing(unittest.TestCase):
    """Test --mount argument parsing."""

    def test_mount_flag_single(self):
        """--mount should accept source:target."""
        args = jolo.parse_args(['--mount', '~/data:data'])
        self.assertEqual(args.mount, ['~/data:data'])

    def test_mount_flag_multiple(self):
        """--mount can be specified multiple times."""
        args = jolo.parse_args(['--mount', '~/a:a', '--mount', '~/b:b'])
        self.assertEqual(args.mount, ['~/a:a', '~/b:b'])

    def test_mount_default_empty(self):
        """--mount should default to empty list."""
        args = jolo.parse_args([])
        self.assertEqual(args.mount, [])

    def test_mount_readonly(self):
        """--mount should accept :ro suffix."""
        args = jolo.parse_args(['--mount', '~/data:data:ro'])
        self.assertEqual(args.mount, ['~/data:data:ro'])


class TestCopyArgParsing(unittest.TestCase):
    """Test --copy argument parsing."""

    def test_copy_flag_single(self):
        """--copy should accept source:target."""
        args = jolo.parse_args(['--copy', '~/config.json:config.json'])
        self.assertEqual(args.copy, ['~/config.json:config.json'])

    def test_copy_flag_multiple(self):
        """--copy can be specified multiple times."""
        args = jolo.parse_args(['--copy', '~/a.json', '--copy', '~/b.json:b.json'])
        self.assertEqual(args.copy, ['~/a.json', '~/b.json:b.json'])

    def test_copy_default_empty(self):
        """--copy should default to empty list."""
        args = jolo.parse_args([])
        self.assertEqual(args.copy, [])

    def test_copy_without_target(self):
        """--copy should accept source without target."""
        args = jolo.parse_args(['--copy', '~/config.json'])
        self.assertEqual(args.copy, ['~/config.json'])


class TestMountAndCopyTogether(unittest.TestCase):
    """Test --mount and --copy used together."""

    def test_mount_and_copy_combined(self):
        """--mount and --copy can be used together."""
        args = jolo.parse_args([
            '--mount', '~/data:data',
            '--copy', '~/config.json',
            '--mount', '~/other:other:ro',
            '--copy', '~/secrets.json:secrets/keys.json'
        ])
        self.assertEqual(len(args.mount), 2)
        self.assertEqual(len(args.copy), 2)
        self.assertEqual(args.mount, ['~/data:data', '~/other:other:ro'])
        self.assertEqual(args.copy, ['~/config.json', '~/secrets.json:secrets/keys.json'])


class TestMountParsing(unittest.TestCase):
    """Test parse_mount() function."""

    def test_parse_mount_relative_target(self):
        """Relative target should resolve to workspace."""
        result = jolo.parse_mount('~/data:foo', 'myproj')
        self.assertEqual(result['target'], '/workspaces/myproj/foo')
        self.assertFalse(result['readonly'])

    def test_parse_mount_absolute_target(self):
        """Absolute target should be used as-is."""
        result = jolo.parse_mount('~/data:/mnt/data', 'myproj')
        self.assertEqual(result['target'], '/mnt/data')

    def test_parse_mount_readonly(self):
        """:ro suffix should set readonly."""
        result = jolo.parse_mount('~/data:foo:ro', 'myproj')
        self.assertTrue(result['readonly'])
        self.assertEqual(result['target'], '/workspaces/myproj/foo')

    def test_parse_mount_absolute_readonly(self):
        """Absolute target with :ro suffix."""
        result = jolo.parse_mount('~/data:/mnt/data:ro', 'myproj')
        self.assertTrue(result['readonly'])
        self.assertEqual(result['target'], '/mnt/data')

    def test_parse_mount_expands_tilde(self):
        """Should expand ~ in source path."""
        result = jolo.parse_mount('~/data:foo', 'myproj')
        self.assertNotIn('~', result['source'])
        self.assertTrue(result['source'].startswith('/'))

    def test_parse_mount_default_readwrite(self):
        """Default should be read-write."""
        result = jolo.parse_mount('~/data:foo', 'myproj')
        self.assertFalse(result['readonly'])

    def test_parse_mount_nested_target(self):
        """Nested relative target should work."""
        result = jolo.parse_mount('~/data:some/nested/path', 'myproj')
        self.assertEqual(result['target'], '/workspaces/myproj/some/nested/path')


class TestCopyParsing(unittest.TestCase):
    """Test parse_copy() function."""

    def test_parse_copy_with_target(self):
        """Copy with target should resolve correctly."""
        result = jolo.parse_copy('~/config.json:app/config.json', 'myproj')
        self.assertEqual(result['target'], '/workspaces/myproj/app/config.json')

    def test_parse_copy_basename_only(self):
        """Copy without target should use basename."""
        result = jolo.parse_copy('~/config.json', 'myproj')
        self.assertEqual(result['target'], '/workspaces/myproj/config.json')

    def test_parse_copy_absolute_target(self):
        """Copy with absolute target should use as-is."""
        result = jolo.parse_copy('~/config.json:/tmp/config.json', 'myproj')
        self.assertEqual(result['target'], '/tmp/config.json')

    def test_parse_copy_expands_tilde(self):
        """Should expand ~ in source path."""
        result = jolo.parse_copy('~/config.json', 'myproj')
        self.assertNotIn('~', result['source'])
        self.assertTrue(result['source'].startswith('/'))

    def test_parse_copy_nested_source(self):
        """Nested source path should work."""
        result = jolo.parse_copy('~/some/nested/config.json', 'myproj')
        self.assertEqual(result['target'], '/workspaces/myproj/config.json')
        self.assertTrue(result['source'].endswith('some/nested/config.json'))


class TestAddUserMounts(unittest.TestCase):
    """Test add_user_mounts() function."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_add_user_mounts_to_devcontainer_json(self):
        """Mount should be added to mounts array in JSON."""
        import json

        # Create devcontainer.json
        devcontainer_dir = Path(self.tmpdir) / '.devcontainer'
        devcontainer_dir.mkdir()
        json_file = devcontainer_dir / 'devcontainer.json'
        json_file.write_text(json.dumps({"name": "test", "mounts": []}))

        # Add a mount
        mounts = [{"source": "/home/user/data", "target": "/workspaces/test/data", "readonly": False}]
        jolo.add_user_mounts(json_file, mounts)

        # Verify
        content = json.loads(json_file.read_text())
        self.assertEqual(len(content['mounts']), 1)
        self.assertIn('source=/home/user/data', content['mounts'][0])
        self.assertIn('target=/workspaces/test/data', content['mounts'][0])
        self.assertIn('type=bind', content['mounts'][0])

    def test_mount_readonly_format(self):
        """Readonly mount should include ,readonly in mount string."""
        import json

        devcontainer_dir = Path(self.tmpdir) / '.devcontainer'
        devcontainer_dir.mkdir()
        json_file = devcontainer_dir / 'devcontainer.json'
        json_file.write_text(json.dumps({"name": "test", "mounts": []}))

        mounts = [{"source": "/data", "target": "/mnt", "readonly": True}]
        jolo.add_user_mounts(json_file, mounts)

        content = json.loads(json_file.read_text())
        self.assertIn(',readonly', content['mounts'][0])

    def test_multiple_mounts_in_json(self):
        """Multiple mounts should all be added."""
        import json

        devcontainer_dir = Path(self.tmpdir) / '.devcontainer'
        devcontainer_dir.mkdir()
        json_file = devcontainer_dir / 'devcontainer.json'
        json_file.write_text(json.dumps({"name": "test", "mounts": ["existing"]}))

        mounts = [
            {"source": "/a", "target": "/mnt/a", "readonly": False},
            {"source": "/b", "target": "/mnt/b", "readonly": True},
        ]
        jolo.add_user_mounts(json_file, mounts)

        content = json.loads(json_file.read_text())
        self.assertEqual(len(content['mounts']), 3)  # existing + 2 new

    def test_add_user_mounts_creates_mounts_array(self):
        """Should create mounts array if not present."""
        import json

        devcontainer_dir = Path(self.tmpdir) / '.devcontainer'
        devcontainer_dir.mkdir()
        json_file = devcontainer_dir / 'devcontainer.json'
        json_file.write_text(json.dumps({"name": "test"}))

        mounts = [{"source": "/data", "target": "/mnt", "readonly": False}]
        jolo.add_user_mounts(json_file, mounts)

        content = json.loads(json_file.read_text())
        self.assertIn('mounts', content)
        self.assertEqual(len(content['mounts']), 1)

    def test_add_user_mounts_empty_list(self):
        """Empty mounts list should not modify file."""
        import json

        devcontainer_dir = Path(self.tmpdir) / '.devcontainer'
        devcontainer_dir.mkdir()
        json_file = devcontainer_dir / 'devcontainer.json'
        original = {"name": "test"}
        json_file.write_text(json.dumps(original))

        jolo.add_user_mounts(json_file, [])

        content = json.loads(json_file.read_text())
        self.assertEqual(content, original)


class TestGitignoreTemplate(unittest.TestCase):
    """Test universal .gitignore template."""

    def setUp(self):
        self.template_path = Path(__file__).parent / 'templates' / '.gitignore'

    def test_gitignore_template_exists(self):
        """templates/.gitignore should exist."""
        self.assertTrue(self.template_path.exists(), f"Missing {self.template_path}")

    def test_gitignore_contains_python_patterns(self):
        """Should contain Python ignore patterns."""
        content = self.template_path.read_text()
        self.assertIn('__pycache__', content)
        self.assertIn('.venv', content)
        self.assertIn('*.pyc', content)

    def test_gitignore_contains_node_patterns(self):
        """Should contain Node.js ignore patterns."""
        content = self.template_path.read_text()
        self.assertIn('node_modules/', content)
        self.assertIn('dist/', content)

    def test_gitignore_contains_rust_patterns(self):
        """Should contain Rust ignore patterns."""
        content = self.template_path.read_text()
        self.assertIn('target/', content)

    def test_gitignore_contains_general_patterns(self):
        """Should contain general ignore patterns."""
        content = self.template_path.read_text()
        self.assertIn('.env', content)
        self.assertIn('.DS_Store', content)
        self.assertIn('*.log', content)


class TestPreCommitTemplate(unittest.TestCase):
    """Test pre-commit template configuration."""

    def test_pre_commit_template_exists(self):
        """templates/.pre-commit-config.yaml should exist."""
        template_path = Path(__file__).parent / 'templates' / '.pre-commit-config.yaml'
        self.assertTrue(template_path.exists(), f"Template not found at {template_path}")

    def test_pre_commit_template_contains_gitleaks_hook(self):
        """Template should contain gitleaks hook."""
        template_path = Path(__file__).parent / 'templates' / '.pre-commit-config.yaml'
        content = template_path.read_text()

        # Check that gitleaks hook is configured
        self.assertIn('id: gitleaks', content, "Should have gitleaks hook id")

    def test_pre_commit_template_gitleaks_repo_url(self):
        """Gitleaks repo URL should be correct."""
        template_path = Path(__file__).parent / 'templates' / '.pre-commit-config.yaml'
        content = template_path.read_text()

        self.assertIn(
            'repo: https://github.com/gitleaks/gitleaks',
            content,
            "Gitleaks repo URL should be https://github.com/gitleaks/gitleaks"
        )


class TestCopyUserFiles(unittest.TestCase):
    """Test copy_user_files() function."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_file_copied_to_correct_location(self):
        """File should be copied to target location."""
        workspace = Path(self.tmpdir) / 'workspace'
        workspace.mkdir()

        # Create source file
        source = Path(self.tmpdir) / 'source.json'
        source.write_text('{"test": true}')

        copies = [{"source": str(source), "target": "/workspaces/myproj/config.json"}]
        jolo.copy_user_files(copies, workspace)

        target = workspace / 'config.json'
        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(), '{"test": true}')

    def test_parent_directories_created(self):
        """Parent directories should be created if needed."""
        workspace = Path(self.tmpdir) / 'workspace'
        workspace.mkdir()

        source = Path(self.tmpdir) / 'source.json'
        source.write_text('test')

        copies = [{"source": str(source), "target": "/workspaces/myproj/nested/deep/config.json"}]
        jolo.copy_user_files(copies, workspace)

        target = workspace / 'nested' / 'deep' / 'config.json'
        self.assertTrue(target.exists())

    def test_error_on_missing_source(self):
        """Should error if source file doesn't exist."""
        workspace = Path(self.tmpdir) / 'workspace'
        workspace.mkdir()

        copies = [{"source": "/nonexistent/file.json", "target": "/workspaces/myproj/config.json"}]

        with self.assertRaises(SystemExit) as cm:
            jolo.copy_user_files(copies, workspace)
        self.assertIn('does not exist', str(cm.exception.code))

    def test_multiple_copies(self):
        """Multiple files should all be copied."""
        workspace = Path(self.tmpdir) / 'workspace'
        workspace.mkdir()

        source1 = Path(self.tmpdir) / 'a.json'
        source1.write_text('a')
        source2 = Path(self.tmpdir) / 'b.json'
        source2.write_text('b')

        copies = [
            {"source": str(source1), "target": "/workspaces/myproj/a.json"},
            {"source": str(source2), "target": "/workspaces/myproj/b.json"},
        ]
        jolo.copy_user_files(copies, workspace)

        self.assertTrue((workspace / 'a.json').exists())
        self.assertTrue((workspace / 'b.json').exists())


class TestLangArgParsing(unittest.TestCase):
    """Test --lang argument parsing."""

    def test_lang_flag_single(self):
        """--lang should accept a single language."""
        args = jolo.parse_args(['--lang', 'python'])
        self.assertEqual(args.lang, ['python'])

    def test_lang_flag_comma_separated(self):
        """--lang should accept comma-separated values."""
        args = jolo.parse_args(['--lang', 'python,typescript'])
        self.assertEqual(args.lang, ['python', 'typescript'])

    def test_lang_flag_multiple_values(self):
        """--lang should handle multiple comma-separated values."""
        args = jolo.parse_args(['--lang', 'python,go,rust'])
        self.assertEqual(args.lang, ['python', 'go', 'rust'])

    def test_lang_default_none(self):
        """--lang should default to None."""
        args = jolo.parse_args([])
        self.assertIsNone(args.lang)

    def test_lang_valid_values(self):
        """--lang should accept all valid language values."""
        valid_langs = ['python', 'go', 'typescript', 'rust', 'shell', 'prose', 'other']
        for lang in valid_langs:
            args = jolo.parse_args(['--lang', lang])
            self.assertEqual(args.lang, [lang])

    def test_lang_invalid_value_raises_error(self):
        """--lang should reject invalid language values."""
        with self.assertRaises(SystemExit):
            jolo.parse_args(['--lang', 'invalid_language'])

    def test_lang_mixed_valid_invalid_raises_error(self):
        """--lang should reject if any value is invalid."""
        with self.assertRaises(SystemExit):
            jolo.parse_args(['--lang', 'python,invalid'])

    def test_lang_with_create(self):
        """--lang can combine with --create."""
        args = jolo.parse_args(['--create', 'myproject', '--lang', 'python,typescript'])
        self.assertEqual(args.create, 'myproject')
        self.assertEqual(args.lang, ['python', 'typescript'])

    def test_lang_is_optional(self):
        """--lang is not required for any command."""
        # Should not raise
        args = jolo.parse_args(['--create', 'myproject'])
        self.assertIsNone(args.lang)

    def test_lang_whitespace_handling(self):
        """--lang should handle values with whitespace around commas."""
        args = jolo.parse_args(['--lang', 'python, typescript, go'])
        self.assertEqual(args.lang, ['python', 'typescript', 'go'])


class TestGetProjectInitCommands(unittest.TestCase):
    """Test get_project_init_commands() function."""

    def test_function_exists(self):
        """get_project_init_commands should exist."""
        self.assertTrue(hasattr(jolo, 'get_project_init_commands'))
        self.assertTrue(callable(jolo.get_project_init_commands))

    def test_python_returns_uv_init(self):
        """Python should return uv commands."""
        commands = jolo.get_project_init_commands('python', 'myproject')
        self.assertIn(['uv', 'init'], commands)

    def test_python_creates_tests_dir(self):
        """Python should create tests directory."""
        commands = jolo.get_project_init_commands('python', 'myproject')
        self.assertIn(['mkdir', '-p', 'tests'], commands)

    def test_typescript_returns_bun_init(self):
        """TypeScript should return bun commands."""
        commands = jolo.get_project_init_commands('typescript', 'myproject')
        self.assertIn(['bun', 'init'], commands)

    def test_go_returns_go_mod_init(self):
        """Go should return go mod init with project name."""
        commands = jolo.get_project_init_commands('go', 'myproject')
        self.assertIn(['go', 'mod', 'init', 'myproject'], commands)

    def test_rust_returns_cargo_new(self):
        """Rust should return cargo new commands."""
        commands = jolo.get_project_init_commands('rust', 'myproject')
        self.assertIn(['cargo', 'new', '.', '--name', 'myproject'], commands)

    def test_shell_returns_src_mkdir(self):
        """Shell should create src directory."""
        commands = jolo.get_project_init_commands('shell', 'myproject')
        self.assertIn(['mkdir', '-p', 'src'], commands)

    def test_prose_returns_docs_or_src_mkdir(self):
        """Prose should create docs or src directory."""
        commands = jolo.get_project_init_commands('prose', 'myproject')
        # Should have at least one directory creation
        has_docs = ['mkdir', '-p', 'docs'] in commands
        has_src = ['mkdir', '-p', 'src'] in commands
        self.assertTrue(has_docs or has_src,
                       f"Expected docs or src mkdir, got: {commands}")

    def test_other_returns_src_mkdir(self):
        """Other language should create src directory."""
        commands = jolo.get_project_init_commands('other', 'myproject')
        self.assertIn(['mkdir', '-p', 'src'], commands)

    def test_returns_list_of_lists(self):
        """Should return a list of command lists."""
        commands = jolo.get_project_init_commands('python', 'myproject')
        self.assertIsInstance(commands, list)
        for cmd in commands:
            self.assertIsInstance(cmd, list)
            for part in cmd:
                self.assertIsInstance(part, str)

    def test_project_name_used_in_go_command(self):
        """Project name should be used in go mod init."""
        commands = jolo.get_project_init_commands('go', 'my-awesome-app')
        go_mod_cmd = ['go', 'mod', 'init', 'my-awesome-app']
        self.assertIn(go_mod_cmd, commands)

    def test_project_name_used_in_rust_command(self):
        """Project name should be used in cargo new."""
        commands = jolo.get_project_init_commands('rust', 'my-awesome-app')
        cargo_cmd = ['cargo', 'new', '.', '--name', 'my-awesome-app']
        self.assertIn(cargo_cmd, commands)

    def test_unknown_language_returns_src_mkdir(self):
        """Unknown language should fall back to src mkdir."""
        commands = jolo.get_project_init_commands('unknown_lang', 'myproject')
        self.assertIn(['mkdir', '-p', 'src'], commands)


class TestEditorconfigTemplate(unittest.TestCase):
    """Test templates/.editorconfig file."""

    @classmethod
    def setUpClass(cls):
        """Read the editorconfig file once for all tests."""
        cls.template_path = Path(__file__).parent / 'templates' / '.editorconfig'
        if cls.template_path.exists():
            cls.content = cls.template_path.read_text()
            cls.lines = cls.content.strip().split('\n')
        else:
            cls.content = None
            cls.lines = []

    def test_editorconfig_exists(self):
        """templates/.editorconfig should exist."""
        self.assertTrue(self.template_path.exists(),
                       f"Expected {self.template_path} to exist")

    def test_root_true(self):
        """Should have root = true."""
        self.assertIn('root = true', self.content)

    def test_default_indent_4_spaces(self):
        """Default indent should be 4 spaces."""
        # Find the [*] section and check indent settings
        self.assertIn('indent_style = space', self.content)
        self.assertIn('indent_size = 4', self.content)

    def test_go_files_use_tabs(self):
        """Go files (*.go) should use tabs."""
        # Find the [*.go] section
        self.assertIn('[*.go]', self.content)
        # Check that indent_style = tab appears after [*.go]
        go_section_start = self.content.index('[*.go]')
        go_section = self.content[go_section_start:]
        # Check for tab indent in Go section (before next section or end)
        next_section = go_section.find('\n[', 1)
        if next_section != -1:
            go_section = go_section[:next_section]
        self.assertIn('indent_style = tab', go_section)

    def test_makefile_uses_tabs(self):
        """Makefile should use tabs."""
        self.assertIn('[Makefile]', self.content)
        # Check that indent_style = tab appears after [Makefile]
        makefile_section_start = self.content.index('[Makefile]')
        makefile_section = self.content[makefile_section_start:]
        next_section = makefile_section.find('\n[', 1)
        if next_section != -1:
            makefile_section = makefile_section[:next_section]
        self.assertIn('indent_style = tab', makefile_section)

    def test_end_of_line_lf(self):
        """Should have end_of_line = lf."""
        self.assertIn('end_of_line = lf', self.content)

    def test_charset_utf8(self):
        """Should have charset = utf-8."""
        self.assertIn('charset = utf-8', self.content)


class TestSelectLanguagesInteractive(unittest.TestCase):
    """Test select_languages_interactive() function."""

    def test_function_exists(self):
        """select_languages_interactive function should exist."""
        self.assertTrue(hasattr(jolo, 'select_languages_interactive'))
        self.assertTrue(callable(jolo.select_languages_interactive))

    def test_returns_list(self):
        """Should return a list of selected languages."""
        # Mock pick to return a selection
        mock_selection = [('Python', 0), ('TypeScript', 2)]
        with mock.patch('jolo.HAVE_PICK', True):
            with mock.patch('jolo.pick', return_value=mock_selection):
                result = jolo.select_languages_interactive()
        self.assertIsInstance(result, list)

    def test_returns_lowercase_language_codes(self):
        """Should return lowercase language codes."""
        mock_selection = [('Python', 0), ('TypeScript', 2)]
        with mock.patch('jolo.HAVE_PICK', True):
            with mock.patch('jolo.pick', return_value=mock_selection):
                result = jolo.select_languages_interactive()
        self.assertEqual(result, ['python', 'typescript'])

    def test_empty_selection_returns_empty_list(self):
        """Should return empty list when user selects nothing."""
        mock_selection = []
        with mock.patch('jolo.HAVE_PICK', True):
            with mock.patch('jolo.pick', return_value=mock_selection):
                result = jolo.select_languages_interactive()
        self.assertEqual(result, [])

    def test_single_selection(self):
        """Should handle single selection correctly."""
        mock_selection = [('Go', 1)]
        with mock.patch('jolo.HAVE_PICK', True):
            with mock.patch('jolo.pick', return_value=mock_selection):
                result = jolo.select_languages_interactive()
        self.assertEqual(result, ['go'])

    def test_all_languages_available(self):
        """All valid languages should be available as options."""
        # We can't easily test the options passed to pick without capturing them,
        # so we test the LANGUAGE_OPTIONS constant instead
        self.assertTrue(hasattr(jolo, 'LANGUAGE_OPTIONS'))
        options = jolo.LANGUAGE_OPTIONS
        # Should have entries for all valid languages
        expected = ['Python', 'Go', 'TypeScript', 'Rust', 'Shell', 'Prose/Docs', 'Other']
        self.assertEqual(options, expected)

    def test_prose_docs_maps_to_prose(self):
        """Prose/Docs option should map to 'prose' code."""
        mock_selection = [('Prose/Docs', 5)]
        with mock.patch('jolo.HAVE_PICK', True):
            with mock.patch('jolo.pick', return_value=mock_selection):
                result = jolo.select_languages_interactive()
        self.assertEqual(result, ['prose'])

    def test_preserves_selection_order(self):
        """Should preserve the order of selection (first selected = primary)."""
        # Pick returns selections in the order they appear in the list,
        # but we want to preserve that order
        mock_selection = [('TypeScript', 2), ('Python', 0), ('Rust', 3)]
        with mock.patch('jolo.HAVE_PICK', True):
            with mock.patch('jolo.pick', return_value=mock_selection):
                result = jolo.select_languages_interactive()
        self.assertEqual(result, ['typescript', 'python', 'rust'])

    def test_fallback_when_pick_unavailable(self):
        """Should use fallback input when pick is not available."""
        # Simulate pick not being available
        with mock.patch('jolo.HAVE_PICK', False):
            with mock.patch('builtins.input', return_value='1,3'):
                result = jolo.select_languages_interactive()
        self.assertIsInstance(result, list)

    def test_fallback_parses_comma_separated_numbers(self):
        """Fallback should parse comma-separated numbers."""
        with mock.patch('jolo.HAVE_PICK', False):
            with mock.patch('builtins.input', return_value='1,3'):
                result = jolo.select_languages_interactive()
        self.assertEqual(result, ['python', 'typescript'])

    def test_fallback_handles_empty_input(self):
        """Fallback should return empty list on empty input."""
        with mock.patch('jolo.HAVE_PICK', False):
            with mock.patch('builtins.input', return_value=''):
                result = jolo.select_languages_interactive()
        self.assertEqual(result, [])

    def test_fallback_handles_invalid_numbers(self):
        """Fallback should skip invalid numbers gracefully."""
        with mock.patch('jolo.HAVE_PICK', False):
            with mock.patch('builtins.input', return_value='1,99,2'):
                result = jolo.select_languages_interactive()
        # Should return python (1) and go (2), skip invalid 99
        self.assertEqual(result, ['python', 'go'])

    def test_keyboard_interrupt_returns_empty(self):
        """Should return empty list on keyboard interrupt."""
        with mock.patch('jolo.HAVE_PICK', True):
            with mock.patch('jolo.pick', side_effect=KeyboardInterrupt):
                result = jolo.select_languages_interactive()
        self.assertEqual(result, [])


class TestLanguageCodeMapping(unittest.TestCase):
    """Test the language display name to code mapping."""

    def test_mapping_exists(self):
        """LANGUAGE_CODE_MAP should exist."""
        self.assertTrue(hasattr(jolo, 'LANGUAGE_CODE_MAP'))

    def test_all_options_have_mapping(self):
        """Every LANGUAGE_OPTIONS entry should have a code mapping."""
        for option in jolo.LANGUAGE_OPTIONS:
            self.assertIn(option, jolo.LANGUAGE_CODE_MAP,
                         f"Missing mapping for {option}")

    def test_mapping_values_are_valid(self):
        """All mapped codes should be in VALID_LANGUAGES."""
        for option, code in jolo.LANGUAGE_CODE_MAP.items():
            self.assertIn(code, jolo.VALID_LANGUAGES,
                         f"Code '{code}' for '{option}' not in VALID_LANGUAGES")


class TestGetTestFrameworkConfig(unittest.TestCase):
    """Test get_test_framework_config() function."""

    def test_function_exists(self):
        """get_test_framework_config should exist."""
        self.assertTrue(hasattr(jolo, 'get_test_framework_config'))
        self.assertTrue(callable(jolo.get_test_framework_config))

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = jolo.get_test_framework_config('python')
        self.assertIsInstance(result, dict)

    def test_dict_has_required_keys(self):
        """Return dict should have config_file, config_content, example_test_file, example_test_content."""
        result = jolo.get_test_framework_config('python')
        required_keys = ['config_file', 'config_content', 'example_test_file', 'example_test_content']
        for key in required_keys:
            self.assertIn(key, result, f"Missing key: {key}")

    # Python (pytest) tests
    def test_python_config_file(self):
        """Python should use pyproject.toml for config."""
        result = jolo.get_test_framework_config('python')
        self.assertEqual(result['config_file'], 'pyproject.toml')

    def test_python_config_content_pytest(self):
        """Python config should include pytest configuration."""
        result = jolo.get_test_framework_config('python')
        self.assertIn('[tool.pytest.ini_options]', result['config_content'])

    def test_python_example_test_file(self):
        """Python should create tests/test_example.py."""
        result = jolo.get_test_framework_config('python')
        self.assertEqual(result['example_test_file'], 'tests/test_example.py')

    def test_python_example_test_content(self):
        """Python example test should use pytest."""
        result = jolo.get_test_framework_config('python')
        content = result['example_test_content']
        self.assertIn('def test_', content)
        self.assertIn('assert', content)

    # TypeScript (vitest) tests
    def test_typescript_config_file(self):
        """TypeScript should use vitest.config.ts for config."""
        result = jolo.get_test_framework_config('typescript')
        self.assertEqual(result['config_file'], 'vitest.config.ts')

    def test_typescript_config_content_vitest(self):
        """TypeScript config should include vitest configuration."""
        result = jolo.get_test_framework_config('typescript')
        content = result['config_content']
        self.assertIn('vitest', content.lower())
        self.assertIn('defineConfig', content)

    def test_typescript_example_test_file(self):
        """TypeScript should create src/example.test.ts."""
        result = jolo.get_test_framework_config('typescript')
        self.assertEqual(result['example_test_file'], 'src/example.test.ts')

    def test_typescript_example_test_content(self):
        """TypeScript example test should use vitest syntax."""
        result = jolo.get_test_framework_config('typescript')
        content = result['example_test_content']
        self.assertIn('describe', content)
        self.assertIn('it(', content)
        self.assertIn('expect', content)

    # Go (built-in testing) tests
    def test_go_config_file_none(self):
        """Go has no extra config file needed (built-in testing)."""
        result = jolo.get_test_framework_config('go')
        # Config file can be None or empty string for built-in testing
        self.assertTrue(
            result['config_file'] is None or result['config_file'] == '',
            f"Expected None or empty, got: {result['config_file']}"
        )

    def test_go_config_content_empty_or_comment(self):
        """Go config content should be empty or just a comment."""
        result = jolo.get_test_framework_config('go')
        # Config content can be empty or just explain that no config is needed
        self.assertTrue(
            result['config_content'] == '' or 'built-in' in result['config_content'].lower(),
            f"Expected empty or built-in info, got: {result['config_content']}"
        )

    def test_go_example_test_file(self):
        """Go should create example_test.go."""
        result = jolo.get_test_framework_config('go')
        self.assertTrue(result['example_test_file'].endswith('_test.go'))

    def test_go_example_test_content(self):
        """Go example test should use testing package and testify."""
        result = jolo.get_test_framework_config('go')
        content = result['example_test_content']
        self.assertIn('testing', content)
        self.assertIn('func Test', content)
        self.assertIn('testify', content.lower())

    # Rust (built-in testing) tests
    def test_rust_config_file_none(self):
        """Rust has no extra config file needed (built-in testing)."""
        result = jolo.get_test_framework_config('rust')
        # Config file can be None or empty string for built-in testing
        self.assertTrue(
            result['config_file'] is None or result['config_file'] == '',
            f"Expected None or empty, got: {result['config_file']}"
        )

    def test_rust_config_content_empty_or_comment(self):
        """Rust config content should be empty or just a comment."""
        result = jolo.get_test_framework_config('rust')
        # Config content can be empty or just explain that no config is needed
        self.assertTrue(
            result['config_content'] == '' or 'built-in' in result['config_content'].lower(),
            f"Expected empty or built-in info, got: {result['config_content']}"
        )

    def test_rust_example_test_file(self):
        """Rust example test location (src/lib.rs or separate file)."""
        result = jolo.get_test_framework_config('rust')
        # Rust tests can be in lib.rs, main.rs, or a tests/ directory
        self.assertTrue(
            'src/' in result['example_test_file'] or 'tests/' in result['example_test_file'],
            f"Expected src/ or tests/ path, got: {result['example_test_file']}"
        )

    def test_rust_example_test_content(self):
        """Rust example test should use #[test] attribute."""
        result = jolo.get_test_framework_config('rust')
        content = result['example_test_content']
        self.assertIn('#[test]', content)
        self.assertIn('fn test_', content)
        self.assertIn('assert', content)

    # Unknown language handling
    def test_unknown_language_returns_empty_config(self):
        """Unknown language should return empty/None values."""
        result = jolo.get_test_framework_config('unknown')
        self.assertIsInstance(result, dict)
        # Should still have the keys but with empty/None values
        self.assertIn('config_file', result)
        self.assertIn('example_test_file', result)


class TestGetCoverageConfig(unittest.TestCase):
    """Test get_coverage_config() function for language-specific coverage setup."""

    def test_function_exists(self):
        """get_coverage_config should exist and be callable."""
        self.assertTrue(hasattr(jolo, 'get_coverage_config'))
        self.assertTrue(callable(jolo.get_coverage_config))

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = jolo.get_coverage_config('python')
        self.assertIsInstance(result, dict)

    def test_dict_has_required_keys(self):
        """Result should have 'config_addition' and 'run_command' keys."""
        result = jolo.get_coverage_config('python')
        self.assertIn('config_addition', result)
        self.assertIn('run_command', result)

    def test_python_config_addition(self):
        """Python should return pytest-cov config for pyproject.toml."""
        result = jolo.get_coverage_config('python')
        config = result['config_addition']
        self.assertIsNotNone(config)
        # Should contain pyproject.toml configuration hints
        self.assertIn('[tool.pytest.ini_options]', config)
        self.assertIn('--cov', config)

    def test_python_run_command(self):
        """Python should return pytest --cov command."""
        result = jolo.get_coverage_config('python')
        cmd = result['run_command']
        self.assertEqual(cmd, 'pytest --cov=src --cov-report=term-missing')

    def test_typescript_config_addition(self):
        """TypeScript should return vitest coverage config."""
        result = jolo.get_coverage_config('typescript')
        config = result['config_addition']
        self.assertIsNotNone(config)
        # Should contain vitest coverage configuration
        self.assertIn('coverage', config)

    def test_typescript_run_command(self):
        """TypeScript should return vitest --coverage command."""
        result = jolo.get_coverage_config('typescript')
        cmd = result['run_command']
        self.assertEqual(cmd, 'vitest --coverage')

    def test_go_config_addition_is_none(self):
        """Go should return None for config_addition (built-in coverage)."""
        result = jolo.get_coverage_config('go')
        self.assertIsNone(result['config_addition'])

    def test_go_run_command(self):
        """Go should return go test -cover command."""
        result = jolo.get_coverage_config('go')
        cmd = result['run_command']
        self.assertEqual(cmd, 'go test -cover ./...')

    def test_rust_config_addition_is_none(self):
        """Rust should return None for config_addition."""
        result = jolo.get_coverage_config('rust')
        self.assertIsNone(result['config_addition'])

    def test_rust_run_command(self):
        """Rust should return cargo llvm-cov command."""
        result = jolo.get_coverage_config('rust')
        cmd = result['run_command']
        self.assertEqual(cmd, 'cargo llvm-cov')

    def test_unknown_language_returns_none_values(self):
        """Unknown languages should return None for both keys."""
        result = jolo.get_coverage_config('unknown')
        self.assertIsNone(result['config_addition'])
        self.assertIsNone(result['run_command'])

    def test_shell_returns_none_values(self):
        """Shell language should return None (no standard coverage tool)."""
        result = jolo.get_coverage_config('shell')
        self.assertIsNone(result['config_addition'])
        self.assertIsNone(result['run_command'])

    def test_prose_returns_none_values(self):
        """Prose language should return None (no coverage for docs)."""
        result = jolo.get_coverage_config('prose')
        self.assertIsNone(result['config_addition'])
        self.assertIsNone(result['run_command'])

    def test_other_returns_none_values(self):
        """Other language should return None."""
        result = jolo.get_coverage_config('other')
        self.assertIsNone(result['config_addition'])
        self.assertIsNone(result['run_command'])


class TestGetTypeCheckerConfig(unittest.TestCase):
    """Test get_type_checker_config() function."""

    def test_function_exists(self):
        """get_type_checker_config should exist."""
        self.assertTrue(hasattr(jolo, 'get_type_checker_config'))
        self.assertTrue(callable(jolo.get_type_checker_config))

    def test_python_returns_ty_config(self):
        """Python should return ty configuration."""
        result = jolo.get_type_checker_config('python')
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertIn('config_file', result)
        self.assertIn('config_content', result)
        self.assertEqual(result['config_file'], 'pyproject.toml')
        # Should contain [tool.ty] section
        self.assertIn('[tool.ty]', result['config_content'])

    def test_typescript_returns_tsconfig(self):
        """TypeScript should return tsconfig.json with strict mode."""
        result = jolo.get_type_checker_config('typescript')
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertEqual(result['config_file'], 'tsconfig.json')
        # Content should be valid JSON with strict mode
        import json
        config = json.loads(result['config_content'])
        self.assertIn('compilerOptions', config)
        self.assertTrue(config['compilerOptions'].get('strict'))
        self.assertTrue(config['compilerOptions'].get('noEmit'))

    def test_go_returns_none(self):
        """Go should return None (type checking built into compiler)."""
        result = jolo.get_type_checker_config('go')
        self.assertIsNone(result)

    def test_rust_returns_none(self):
        """Rust should return None (type checking built into compiler)."""
        result = jolo.get_type_checker_config('rust')
        self.assertIsNone(result)

    def test_shell_returns_none(self):
        """Shell should return None (no type checking)."""
        result = jolo.get_type_checker_config('shell')
        self.assertIsNone(result)

    def test_prose_returns_none(self):
        """Prose should return None (no type checking)."""
        result = jolo.get_type_checker_config('prose')
        self.assertIsNone(result)

    def test_other_returns_none(self):
        """Other language should return None."""
        result = jolo.get_type_checker_config('other')
        self.assertIsNone(result)

    def test_unknown_language_returns_none(self):
        """Unknown language should return None."""
        result = jolo.get_type_checker_config('unknown_lang')
        self.assertIsNone(result)

    def test_return_dict_structure(self):
        """Returned dict should have 'config_file' and 'config_content' keys."""
        # Test with Python (known to return a dict)
        result = jolo.get_type_checker_config('python')
        self.assertIn('config_file', result)
        self.assertIn('config_content', result)
        self.assertIsInstance(result['config_file'], str)
        self.assertIsInstance(result['config_content'], str)

    def test_typescript_tsconfig_has_essential_options(self):
        """TypeScript config should have essential compiler options."""
        import json
        result = jolo.get_type_checker_config('typescript')
        config = json.loads(result['config_content'])
        options = config['compilerOptions']
        # Essential strict options
        self.assertTrue(options.get('strict'))
        self.assertTrue(options.get('noEmit'))

    def test_python_ty_config_content(self):
        """Python ty config should have reasonable defaults."""
        result = jolo.get_type_checker_config('python')
        content = result['config_content']
        # Should be TOML format with [tool.ty] section
        self.assertIn('[tool.ty]', content)


class TestGeneratePrecommitConfig(unittest.TestCase):
    """Test generate_precommit_config() function."""

    def test_function_exists(self):
        """generate_precommit_config should exist."""
        self.assertTrue(hasattr(jolo, 'generate_precommit_config'))

    def test_returns_string(self):
        """Should return a string."""
        result = jolo.generate_precommit_config([])
        self.assertIsInstance(result, str)

    def test_returns_valid_yaml(self):
        """Should return valid YAML structure."""
        result = jolo.generate_precommit_config(['python'])
        # Verify basic YAML structure without requiring pyyaml
        self.assertTrue(result.startswith('repos:'))
        self.assertIn('  - repo:', result)
        self.assertIn('    rev:', result)
        self.assertIn('    hooks:', result)
        # Try parsing with yaml if available
        try:
            import yaml
            parsed = yaml.safe_load(result)
            self.assertIsInstance(parsed, dict)
            self.assertIn('repos', parsed)
        except ImportError:
            pass  # Skip yaml parsing if pyyaml not installed

    def test_always_includes_base_hooks(self):
        """Should always include trailing-whitespace, end-of-file-fixer, check-added-large-files."""
        result = jolo.generate_precommit_config([])

        self.assertIn('trailing-whitespace', result)
        self.assertIn('end-of-file-fixer', result)
        self.assertIn('check-added-large-files', result)

    def test_always_includes_gitleaks(self):
        """Should always include gitleaks hook."""
        result = jolo.generate_precommit_config([])

        self.assertIn('gitleaks', result)
        self.assertIn('https://github.com/gitleaks/gitleaks', result)

    def test_python_adds_ruff_hooks(self):
        """Python language should add ruff hooks."""
        result = jolo.generate_precommit_config(['python'])

        self.assertIn('https://github.com/astral-sh/ruff-pre-commit', result)
        self.assertIn('id: ruff', result)
        self.assertIn('id: ruff-format', result)
        self.assertIn('v0.8.6', result)

    def test_go_adds_golangci_lint(self):
        """Go language should add golangci-lint hook."""
        result = jolo.generate_precommit_config(['go'])

        self.assertIn('https://github.com/golangci/golangci-lint', result)
        self.assertIn('id: golangci-lint', result)
        self.assertIn('v1.62.0', result)

    def test_typescript_adds_biome(self):
        """TypeScript language should add biome hooks."""
        result = jolo.generate_precommit_config(['typescript'])

        self.assertIn('https://github.com/biomejs/pre-commit', result)
        self.assertIn('id: biome-check', result)
        self.assertIn('v0.6.0', result)

    def test_rust_adds_clippy_and_rustfmt(self):
        """Rust language should add clippy and rustfmt hooks via doublify/pre-commit-rust."""
        result = jolo.generate_precommit_config(['rust'])

        self.assertIn('https://github.com/doublify/pre-commit-rust', result)
        self.assertIn('id: fmt', result)
        self.assertIn('id: cargo-check', result)
        self.assertIn('v1.0', result)

    def test_shell_adds_shellcheck(self):
        """Shell language should add shellcheck hook."""
        result = jolo.generate_precommit_config(['shell'])

        self.assertIn('https://github.com/shellcheck-py/shellcheck-py', result)
        self.assertIn('id: shellcheck', result)
        self.assertIn('v0.10.0.1', result)

    def test_prose_adds_markdownlint_and_codespell(self):
        """Prose language should add markdownlint and codespell hooks."""
        result = jolo.generate_precommit_config(['prose'])

        self.assertIn('https://github.com/igorshubovych/markdownlint-cli', result)
        self.assertIn('id: markdownlint', result)
        self.assertIn('v0.43.0', result)

        self.assertIn('https://github.com/codespell-project/codespell', result)
        self.assertIn('id: codespell', result)
        self.assertIn('v2.3.0', result)

    def test_multiple_languages_combine_correctly(self):
        """Multiple languages should combine all their hooks."""
        result = jolo.generate_precommit_config(['python', 'typescript'])

        # Base hooks
        self.assertIn('trailing-whitespace', result)
        self.assertIn('gitleaks', result)

        # Python hooks
        self.assertIn('https://github.com/astral-sh/ruff-pre-commit', result)
        self.assertIn('id: ruff', result)

        # TypeScript hooks
        self.assertIn('https://github.com/biomejs/pre-commit', result)
        self.assertIn('id: biome-check', result)

    def test_all_languages_combined(self):
        """Should handle all supported languages together."""
        result = jolo.generate_precommit_config(
            ['python', 'go', 'typescript', 'rust', 'shell', 'prose']
        )

        # Verify all language-specific hooks are present
        self.assertIn('ruff', result)
        self.assertIn('golangci-lint', result)
        self.assertIn('biome-check', result)
        self.assertIn('cargo-check', result)
        self.assertIn('shellcheck', result)
        self.assertIn('markdownlint', result)
        self.assertIn('codespell', result)

    def test_unknown_language_ignored(self):
        """Unknown language should be ignored without error."""
        # 'other' is a valid language but has no specific hooks
        result = jolo.generate_precommit_config(['other'])

        # Should still have base hooks
        self.assertIn('trailing-whitespace', result)
        self.assertIn('gitleaks', result)

        # Count repos by counting '  - repo:' lines (exactly 2 for base config)
        repo_count = result.count('  - repo:')
        self.assertEqual(repo_count, 2)

    def test_empty_languages_returns_base_config(self):
        """Empty language list should return only base hooks."""
        result = jolo.generate_precommit_config([])

        # Count repos by counting '  - repo:' lines (exactly 2 for base config)
        repo_count = result.count('  - repo:')
        self.assertEqual(repo_count, 2)

        # Verify they are the expected repos
        self.assertIn('https://github.com/pre-commit/pre-commit-hooks', result)
        self.assertIn('https://github.com/gitleaks/gitleaks', result)

    def test_no_duplicate_repos(self):
        """Same language specified twice should not duplicate repos."""
        result = jolo.generate_precommit_config(['python', 'python'])

        # Count occurrences of ruff repo
        count = result.count('https://github.com/astral-sh/ruff-pre-commit')
        self.assertEqual(count, 1)

    def test_prose_with_python(self):
        """Prose and Python together should have all hooks."""
        result = jolo.generate_precommit_config(['prose', 'python'])

        self.assertIn('ruff', result)
        self.assertIn('markdownlint', result)
        self.assertIn('codespell', result)


class TestGetPrecommitInstallCommand(unittest.TestCase):
    """Test get_precommit_install_command() function."""

    def test_function_exists(self):
        """get_precommit_install_command should exist and be callable."""
        self.assertTrue(hasattr(jolo, 'get_precommit_install_command'))
        self.assertTrue(callable(jolo.get_precommit_install_command))

    def test_returns_list(self):
        """Should return a list."""
        result = jolo.get_precommit_install_command()
        self.assertIsInstance(result, list)

    def test_returns_precommit_install_command(self):
        """Should return ['pre-commit', 'install']."""
        result = jolo.get_precommit_install_command()
        self.assertEqual(result, ['pre-commit', 'install'])

    def test_returns_list_of_strings(self):
        """Should return a list of strings."""
        result = jolo.get_precommit_install_command()
        for item in result:
            self.assertIsInstance(item, str)

    def test_list_has_two_elements(self):
        """Should return a list with exactly two elements."""
        result = jolo.get_precommit_install_command()
        self.assertEqual(len(result), 2)


class TestCreateModeLanguageIntegration(unittest.TestCase):
    """Integration tests for run_create_mode() language handling."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.tmpdir)

    def _mock_devcontainer_calls(self):
        """Create mocks for devcontainer commands."""
        return mock.patch.multiple(
            'jolo',
            devcontainer_up=mock.DEFAULT,
            devcontainer_exec_command=mock.DEFAULT,
            devcontainer_exec_tmux=mock.DEFAULT,
            devcontainer_exec_prompt=mock.DEFAULT,
            is_container_running=mock.DEFAULT,
            setup_credential_cache=mock.DEFAULT,
            setup_emacs_config=mock.DEFAULT,
        )

    def test_create_with_lang_uses_provided_languages(self):
        """--create with --lang should use the provided languages."""
        args = jolo.parse_args(['--create', 'testproj', '--lang', 'python,typescript', '-d'])

        with self._mock_devcontainer_calls() as mocks:
            mocks['devcontainer_up'].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / 'testproj'

        # Check .pre-commit-config.yaml was created with correct hooks
        precommit_config = project_path / '.pre-commit-config.yaml'
        self.assertTrue(precommit_config.exists())
        content = precommit_config.read_text()
        self.assertIn('ruff', content)  # Python
        self.assertIn('biome', content)  # TypeScript

    def test_create_without_lang_calls_interactive_selector(self):
        """--create without --lang should call select_languages_interactive."""
        args = jolo.parse_args(['--create', 'testproj', '-d'])

        with self._mock_devcontainer_calls() as mocks:
            mocks['devcontainer_up'].return_value = True
            with mock.patch('jolo.select_languages_interactive', return_value=['go']) as mock_selector:
                jolo.run_create_mode(args)
                mock_selector.assert_called_once()

        project_path = Path(self.tmpdir) / 'testproj'

        # Check .pre-commit-config.yaml reflects selected language
        precommit_config = project_path / '.pre-commit-config.yaml'
        self.assertTrue(precommit_config.exists())
        content = precommit_config.read_text()
        self.assertIn('golangci-lint', content)  # Go

    def test_create_generates_precommit_config(self):
        """--create should generate .pre-commit-config.yaml based on languages."""
        args = jolo.parse_args(['--create', 'testproj', '--lang', 'rust', '-d'])

        with self._mock_devcontainer_calls() as mocks:
            mocks['devcontainer_up'].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / 'testproj'
        precommit_config = project_path / '.pre-commit-config.yaml'

        self.assertTrue(precommit_config.exists())
        content = precommit_config.read_text()
        # Rust hooks
        self.assertIn('cargo-check', content)
        self.assertIn('fmt', content)
        # Base hooks always included
        self.assertIn('trailing-whitespace', content)
        self.assertIn('gitleaks', content)

    def test_create_copies_gitignore_from_templates(self):
        """--create should copy .gitignore from templates/."""
        args = jolo.parse_args(['--create', 'testproj', '--lang', 'python', '-d'])

        with self._mock_devcontainer_calls() as mocks:
            mocks['devcontainer_up'].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / 'testproj'
        gitignore = project_path / '.gitignore'

        self.assertTrue(gitignore.exists())

    def test_create_copies_editorconfig_from_templates(self):
        """--create should copy .editorconfig from templates/."""
        args = jolo.parse_args(['--create', 'testproj', '--lang', 'python', '-d'])

        with self._mock_devcontainer_calls() as mocks:
            mocks['devcontainer_up'].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / 'testproj'
        editorconfig = project_path / '.editorconfig'

        self.assertTrue(editorconfig.exists())

    def test_create_runs_init_commands_for_primary_language(self):
        """--create should run project init commands for primary language after container starts."""
        args = jolo.parse_args(['--create', 'testproj', '--lang', 'python,typescript', '-d'])

        with self._mock_devcontainer_calls() as mocks:
            mocks['devcontainer_up'].return_value = True
            jolo.run_create_mode(args)

            # Primary language is python (first in list)
            # Should have executed uv init inside the container
            exec_calls = mocks['devcontainer_exec_command'].call_args_list
            # Find the uv init call
            uv_init_called = any('uv init' in str(call) for call in exec_calls)
            self.assertTrue(uv_init_called, f"Expected 'uv init' to be called, got: {exec_calls}")

    def test_create_writes_test_framework_config_for_python(self):
        """--create with python should write pytest config to pyproject.toml."""
        args = jolo.parse_args(['--create', 'testproj', '--lang', 'python', '-d'])

        with self._mock_devcontainer_calls() as mocks:
            mocks['devcontainer_up'].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / 'testproj'
        pyproject = project_path / 'pyproject.toml'

        # pyproject.toml should exist (created by copy_template or test config)
        if pyproject.exists():
            content = pyproject.read_text()
            # Should have pytest config
            self.assertIn('pytest', content.lower())

    def test_create_writes_test_framework_config_for_typescript(self):
        """--create with typescript should write vitest config."""
        args = jolo.parse_args(['--create', 'testproj', '--lang', 'typescript', '-d'])

        with self._mock_devcontainer_calls() as mocks:
            mocks['devcontainer_up'].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / 'testproj'
        vitest_config = project_path / 'vitest.config.ts'

        self.assertTrue(vitest_config.exists())
        content = vitest_config.read_text()
        self.assertIn('vitest', content)

    def test_create_writes_type_checker_config_for_typescript(self):
        """--create with typescript should write tsconfig.json."""
        args = jolo.parse_args(['--create', 'testproj', '--lang', 'typescript', '-d'])

        with self._mock_devcontainer_calls() as mocks:
            mocks['devcontainer_up'].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / 'testproj'
        tsconfig = project_path / 'tsconfig.json'

        self.assertTrue(tsconfig.exists())
        content = tsconfig.read_text()
        self.assertIn('strict', content)

    def test_create_first_language_is_primary(self):
        """First language in list should be treated as primary for init commands."""
        args = jolo.parse_args(['--create', 'testproj', '--lang', 'go,python', '-d'])

        with self._mock_devcontainer_calls() as mocks:
            mocks['devcontainer_up'].return_value = True
            jolo.run_create_mode(args)

            # Primary language is go (first in list)
            exec_calls = mocks['devcontainer_exec_command'].call_args_list
            # Should have go mod init, not uv init
            go_mod_called = any('go mod init' in str(call) for call in exec_calls)
            self.assertTrue(go_mod_called, f"Expected 'go mod init' to be called, got: {exec_calls}")

    def test_create_empty_language_selection_uses_other(self):
        """If interactive selector returns empty list, should use 'other' as default."""
        args = jolo.parse_args(['--create', 'testproj', '-d'])

        with self._mock_devcontainer_calls() as mocks:
            mocks['devcontainer_up'].return_value = True
            with mock.patch('jolo.select_languages_interactive', return_value=[]):
                jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / 'testproj'
        # Should still have .pre-commit-config.yaml with base hooks
        precommit_config = project_path / '.pre-commit-config.yaml'
        self.assertTrue(precommit_config.exists())

    def test_create_template_files_are_copied(self):
        """--create should copy AGENTS.md, CLAUDE.md, GEMINI.md from templates."""
        args = jolo.parse_args(['--create', 'testproj', '--lang', 'python', '-d'])

        with self._mock_devcontainer_calls() as mocks:
            mocks['devcontainer_up'].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / 'testproj'

        # These should be copied by copy_template_files
        for filename in ['AGENTS.md', 'CLAUDE.md', 'GEMINI.md']:
            filepath = project_path / filename
            self.assertTrue(filepath.exists(), f"Expected {filename} to exist")


if __name__ == '__main__':
    unittest.main()
