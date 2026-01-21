#!/usr/bin/env python3
"""Tests for yolo CLI tool - TDD style."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Import will fail until we create the module
try:
    import yolo
except ImportError:
    yolo = None


class TestArgumentParsing(unittest.TestCase):
    """Test command-line argument parsing."""

    def test_no_args_returns_default_mode(self):
        """No arguments should result in default mode."""
        args = yolo.parse_args([])
        self.assertIsNone(args.tree)
        self.assertIsNone(args.create)
        self.assertFalse(args.new)

    def test_help_flag(self):
        """--help should exit with usage info."""
        with self.assertRaises(SystemExit) as cm:
            yolo.parse_args(['--help'])
        self.assertEqual(cm.exception.code, 0)

    def test_tree_with_name(self):
        """--tree NAME should set tree to NAME."""
        args = yolo.parse_args(['--tree', 'feature-x'])
        self.assertEqual(args.tree, 'feature-x')

    def test_tree_without_name(self):
        """--tree without name should set tree to empty string (generate random)."""
        args = yolo.parse_args(['--tree'])
        self.assertEqual(args.tree, '')

    def test_create_with_name(self):
        """--create NAME should set create to NAME."""
        args = yolo.parse_args(['--create', 'myproject'])
        self.assertEqual(args.create, 'myproject')

    def test_create_requires_name(self):
        """--create without NAME should fail."""
        with self.assertRaises(SystemExit):
            yolo.parse_args(['--create'])

    def test_new_flag(self):
        """--new should set new to True."""
        args = yolo.parse_args(['--new'])
        self.assertTrue(args.new)

    def test_new_with_tree(self):
        """--new can combine with --tree."""
        args = yolo.parse_args(['--new', '--tree', 'test'])
        self.assertTrue(args.new)
        self.assertEqual(args.tree, 'test')

    def test_sync_flag(self):
        """--sync should set sync to True."""
        args = yolo.parse_args(['--sync'])
        self.assertTrue(args.sync)

    def test_sync_default_false(self):
        """--sync should default to False."""
        args = yolo.parse_args([])
        self.assertFalse(args.sync)


class TestGuards(unittest.TestCase):
    """Test guard conditions and validations."""

    def test_tmux_guard_raises_when_in_tmux(self):
        """Should error when TMUX env var is set."""
        with mock.patch.dict(os.environ, {'TMUX': '/tmp/tmux-1000/default,12345,0'}):
            with self.assertRaises(SystemExit) as cm:
                yolo.check_tmux_guard()
            self.assertIn('tmux', str(cm.exception.code).lower())

    def test_tmux_guard_passes_when_not_in_tmux(self):
        """Should pass when TMUX env var is not set."""
        env = os.environ.copy()
        env.pop('TMUX', None)
        with mock.patch.dict(os.environ, env, clear=True):
            # Should not raise
            yolo.check_tmux_guard()


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

        result = yolo.find_git_root()
        self.assertEqual(result, Path(self.tmpdir))

    def test_find_git_root_in_subdirectory(self):
        """Should find git root when in subdirectory."""
        git_dir = Path(self.tmpdir) / '.git'
        git_dir.mkdir()
        subdir = Path(self.tmpdir) / 'src' / 'lib'
        subdir.mkdir(parents=True)
        os.chdir(subdir)

        result = yolo.find_git_root()
        self.assertEqual(result, Path(self.tmpdir))

    def test_find_git_root_returns_none_outside_repo(self):
        """Should return None when not in a git repo."""
        os.chdir(self.tmpdir)

        result = yolo.find_git_root()
        self.assertIsNone(result)


class TestRandomNameGeneration(unittest.TestCase):
    """Test random name generation for worktrees."""

    def test_generate_random_name_format(self):
        """Should generate adjective-noun format."""
        name = yolo.generate_random_name()
        parts = name.split('-')
        self.assertEqual(len(parts), 2)

    def test_generate_random_name_uses_wordlists(self):
        """Generated name should use defined word lists."""
        name = yolo.generate_random_name()
        adj, noun = name.split('-')
        self.assertIn(adj, yolo.ADJECTIVES)
        self.assertIn(noun, yolo.NOUNS)

    def test_generate_random_name_is_random(self):
        """Should generate different names (probabilistically)."""
        names = {yolo.generate_random_name() for _ in range(20)}
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
        yolo.scaffold_devcontainer('testproject')

        devcontainer_dir = Path(self.tmpdir) / '.devcontainer'
        self.assertTrue(devcontainer_dir.exists())
        self.assertTrue(devcontainer_dir.is_dir())

    def test_scaffold_devcontainer_creates_json(self):
        """Should create devcontainer.json with project name."""
        os.chdir(self.tmpdir)
        yolo.scaffold_devcontainer('testproject')

        json_file = Path(self.tmpdir) / '.devcontainer' / 'devcontainer.json'
        self.assertTrue(json_file.exists())
        content = json_file.read_text()
        self.assertIn('"name": "testproject"', content)

    def test_scaffold_devcontainer_creates_dockerfile(self):
        """Should create Dockerfile with default base image."""
        os.chdir(self.tmpdir)
        yolo.scaffold_devcontainer('testproject')

        dockerfile = Path(self.tmpdir) / '.devcontainer' / 'Dockerfile'
        self.assertTrue(dockerfile.exists())
        content = dockerfile.read_text()
        self.assertIn('FROM localhost/emacs-gui:latest', content)

    def test_scaffold_devcontainer_uses_config_base_image(self):
        """Should use base_image from config."""
        os.chdir(self.tmpdir)
        config = {'base_image': 'custom/myimage:v3'}
        yolo.scaffold_devcontainer('testproject', config=config)

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
        result = yolo.scaffold_devcontainer('testproject')
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
                secrets = yolo.get_secrets()

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
                secrets = yolo.get_secrets()

        self.assertEqual(secrets['ANTHROPIC_API_KEY'], 'sk-ant-from-pass')
        self.assertEqual(secrets['OPENAI_API_KEY'], 'sk-openai-from-pass')


class TestContainerNaming(unittest.TestCase):
    """Test container name generation."""

    def test_container_name_from_project(self):
        """Should derive container name from project directory."""
        name = yolo.get_container_name('/home/user/myproject', None)
        self.assertEqual(name, 'myproject')

    def test_container_name_with_worktree(self):
        """Should include worktree name in container name."""
        name = yolo.get_container_name('/home/user/myproject', 'feature-x')
        self.assertEqual(name, 'myproject-feature-x')

    def test_container_name_lowercase(self):
        """Should convert to lowercase."""
        name = yolo.get_container_name('/home/user/MyProject', None)
        self.assertEqual(name, 'myproject')


class TestWorktreePaths(unittest.TestCase):
    """Test worktree path computation."""

    def test_worktree_path_computation(self):
        """Should compute worktree path as ../PROJECT-worktrees/NAME."""
        path = yolo.get_worktree_path('/dev/myapp', 'feature-x')
        self.assertEqual(path, Path('/dev/myapp-worktrees/feature-x'))

    def test_worktree_path_with_trailing_slash(self):
        """Should handle trailing slash in project path."""
        path = yolo.get_worktree_path('/dev/myapp/', 'feature-x')
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
            yolo.validate_tree_mode()
        self.assertIn('git', str(cm.exception.code).lower())

    def test_create_mode_forbids_git_repo(self):
        """--create should fail if already in git repo."""
        git_dir = Path(self.tmpdir) / '.git'
        git_dir.mkdir()
        os.chdir(self.tmpdir)

        with self.assertRaises(SystemExit) as cm:
            yolo.validate_create_mode('newproject')
        self.assertIn('git', str(cm.exception.code).lower())

    def test_create_mode_forbids_existing_directory(self):
        """--create should fail if directory exists."""
        os.chdir(self.tmpdir)
        existing = Path(self.tmpdir) / 'existing'
        existing.mkdir()

        with self.assertRaises(SystemExit) as cm:
            yolo.validate_create_mode('existing')
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

            result = yolo.get_or_create_worktree(
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
        yolo.add_worktree_git_mount(json_file, main_git_dir)

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
        yolo.add_worktree_git_mount(json_file, main_git_dir)

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
        yolo.sync_devcontainer('myproject', config=config)

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
        yolo.sync_devcontainer('newproject', config=config)

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
        config = yolo.load_config(global_config_dir=Path(self.tmpdir) / 'noexist')

        self.assertEqual(config['base_image'], 'localhost/emacs-gui:latest')
        self.assertEqual(config['pass_path_anthropic'], 'api/llm/anthropic')
        self.assertEqual(config['pass_path_openai'], 'api/llm/openai')

    def test_load_global_config(self):
        """Should load global config from ~/.config/yolo/config.toml."""
        config_dir = Path(self.tmpdir) / '.config' / 'yolo'
        config_dir.mkdir(parents=True)
        (config_dir / 'config.toml').write_text('base_image = "custom/image:v1"\n')

        config = yolo.load_config(global_config_dir=config_dir)

        self.assertEqual(config['base_image'], 'custom/image:v1')

    def test_load_project_config(self):
        """Should load project config from .yolo.toml."""
        os.chdir(self.tmpdir)
        Path(self.tmpdir, '.yolo.toml').write_text('base_image = "project/image:v2"\n')

        config = yolo.load_config(global_config_dir=Path(self.tmpdir) / 'noexist')

        self.assertEqual(config['base_image'], 'project/image:v2')

    def test_project_config_overrides_global(self):
        """Project config should override global config."""
        config_dir = Path(self.tmpdir) / '.config' / 'yolo'
        config_dir.mkdir(parents=True)
        (config_dir / 'config.toml').write_text('base_image = "global/image:v1"\n')

        os.chdir(self.tmpdir)
        Path(self.tmpdir, '.yolo.toml').write_text('base_image = "project/image:v2"\n')

        config = yolo.load_config(global_config_dir=config_dir)

        self.assertEqual(config['base_image'], 'project/image:v2')

    def test_config_partial_override(self):
        """Project config should only override specified keys."""
        config_dir = Path(self.tmpdir) / '.config' / 'yolo'
        config_dir.mkdir(parents=True)
        (config_dir / 'config.toml').write_text(
            'base_image = "global/image:v1"\npass_path_anthropic = "custom/path"\n'
        )

        os.chdir(self.tmpdir)
        Path(self.tmpdir, '.yolo.toml').write_text('base_image = "project/image:v2"\n')

        config = yolo.load_config(global_config_dir=config_dir)

        self.assertEqual(config['base_image'], 'project/image:v2')
        self.assertEqual(config['pass_path_anthropic'], 'custom/path')


class TestListMode(unittest.TestCase):
    """Test --list functionality."""

    def test_list_flag(self):
        """--list should set list to True."""
        args = yolo.parse_args(['--list'])
        self.assertTrue(args.list)

    def test_list_default_false(self):
        """--list should default to False."""
        args = yolo.parse_args([])
        self.assertFalse(args.list)

    def test_all_flag(self):
        """--all should set all to True."""
        args = yolo.parse_args(['--list', '--all'])
        self.assertTrue(args.all)

    def test_all_short_flag(self):
        """-a should set all to True."""
        args = yolo.parse_args(['--list', '-a'])
        self.assertTrue(args.all)

    def test_all_default_false(self):
        """--all should default to False."""
        args = yolo.parse_args(['--list'])
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
        result = yolo.list_worktrees(Path(self.tmpdir))
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

        result = yolo.list_worktrees(Path(self.tmpdir))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], Path(self.tmpdir))

    def test_find_project_workspaces_includes_main(self):
        """Should always include main repo in workspaces."""
        os.chdir(self.tmpdir)
        import subprocess
        subprocess.run(['git', 'init'], cwd=self.tmpdir, capture_output=True)

        git_root = Path(self.tmpdir)
        result = yolo.find_project_workspaces(git_root)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], git_root)
        self.assertEqual(result[0][1], 'main')


class TestContainerRuntime(unittest.TestCase):
    """Test container runtime detection."""

    def test_get_container_runtime_finds_docker(self):
        """Should detect docker if available."""
        with mock.patch('shutil.which') as mock_which:
            mock_which.side_effect = lambda x: '/usr/bin/docker' if x == 'docker' else None
            result = yolo.get_container_runtime()
            self.assertEqual(result, 'docker')

    def test_get_container_runtime_finds_podman(self):
        """Should detect podman if docker not available."""
        with mock.patch('shutil.which') as mock_which:
            mock_which.side_effect = lambda x: '/usr/bin/podman' if x == 'podman' else None
            result = yolo.get_container_runtime()
            self.assertEqual(result, 'podman')

    def test_get_container_runtime_prefers_docker(self):
        """Should prefer docker over podman."""
        with mock.patch('shutil.which') as mock_which:
            mock_which.return_value = '/usr/bin/something'
            result = yolo.get_container_runtime()
            self.assertEqual(result, 'docker')

    def test_get_container_runtime_returns_none(self):
        """Should return None if no runtime available."""
        with mock.patch('shutil.which', return_value=None):
            result = yolo.get_container_runtime()
            self.assertIsNone(result)


class TestListAllDevcontainers(unittest.TestCase):
    """Test global devcontainer listing."""

    def test_list_all_returns_empty_without_runtime(self):
        """Should return empty list if no container runtime."""
        with mock.patch('yolo.get_container_runtime', return_value=None):
            result = yolo.list_all_devcontainers()
            self.assertEqual(result, [])

    def test_list_all_parses_docker_output(self):
        """Should parse docker ps output correctly."""
        mock_output = "mycontainer\t/home/user/project\trunning\n"
        with mock.patch('yolo.get_container_runtime', return_value='docker'):
            with mock.patch('subprocess.run') as mock_run:
                mock_run.return_value = mock.Mock(returncode=0, stdout=mock_output)
                result = yolo.list_all_devcontainers()
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0], ('mycontainer', '/home/user/project', 'running'))


class TestStopMode(unittest.TestCase):
    """Test --stop functionality."""

    def test_stop_flag(self):
        """--stop should set stop to True."""
        args = yolo.parse_args(['--stop'])
        self.assertTrue(args.stop)

    def test_stop_default_false(self):
        """--stop should default to False."""
        args = yolo.parse_args([])
        self.assertFalse(args.stop)


class TestGetContainerForWorkspace(unittest.TestCase):
    """Test container lookup by workspace."""

    def test_returns_none_without_runtime(self):
        """Should return None if no container runtime."""
        with mock.patch('yolo.get_container_runtime', return_value=None):
            result = yolo.get_container_for_workspace(Path('/some/path'))
            self.assertIsNone(result)

    def test_returns_container_name(self):
        """Should return container name from docker output."""
        with mock.patch('yolo.get_container_runtime', return_value='docker'):
            with mock.patch('subprocess.run') as mock_run:
                mock_run.return_value = mock.Mock(returncode=0, stdout='my-container\n')
                result = yolo.get_container_for_workspace(Path('/home/user/project'))
                self.assertEqual(result, 'my-container')

    def test_returns_none_when_no_container(self):
        """Should return None when no container found."""
        with mock.patch('yolo.get_container_runtime', return_value='docker'):
            with mock.patch('subprocess.run') as mock_run:
                mock_run.return_value = mock.Mock(returncode=0, stdout='')
                result = yolo.get_container_for_workspace(Path('/home/user/project'))
                self.assertIsNone(result)


class TestStopContainer(unittest.TestCase):
    """Test container stopping."""

    def test_stop_returns_false_without_runtime(self):
        """Should return False if no container runtime."""
        with mock.patch('yolo.get_container_runtime', return_value=None):
            result = yolo.stop_container(Path('/some/path'))
            self.assertFalse(result)

    def test_stop_returns_false_when_no_container(self):
        """Should return False when no container found."""
        with mock.patch('yolo.get_container_runtime', return_value='docker'):
            with mock.patch('yolo.get_container_for_workspace', return_value=None):
                result = yolo.stop_container(Path('/some/path'))
                self.assertFalse(result)

    def test_stop_returns_true_on_success(self):
        """Should return True when container stopped successfully."""
        with mock.patch('yolo.get_container_runtime', return_value='docker'):
            with mock.patch('yolo.get_container_for_workspace', return_value='my-container'):
                with mock.patch('subprocess.run') as mock_run:
                    mock_run.return_value = mock.Mock(returncode=0)
                    result = yolo.stop_container(Path('/some/path'))
                    self.assertTrue(result)


class TestPruneMode(unittest.TestCase):
    """Test --prune functionality."""

    def test_prune_flag(self):
        """--prune should set prune to True."""
        args = yolo.parse_args(['--prune'])
        self.assertTrue(args.prune)

    def test_prune_default_false(self):
        """--prune should default to False."""
        args = yolo.parse_args([])
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

        result = yolo.find_stale_worktrees(Path(self.tmpdir))
        self.assertEqual(result, [])


class TestRemoveContainer(unittest.TestCase):
    """Test container removal."""

    def test_remove_returns_false_without_runtime(self):
        """Should return False if no container runtime."""
        with mock.patch('yolo.get_container_runtime', return_value=None):
            result = yolo.remove_container('my-container')
            self.assertFalse(result)

    def test_remove_returns_true_on_success(self):
        """Should return True when container removed successfully."""
        with mock.patch('yolo.get_container_runtime', return_value='docker'):
            with mock.patch('subprocess.run') as mock_run:
                mock_run.return_value = mock.Mock(returncode=0)
                result = yolo.remove_container('my-container')
                self.assertTrue(result)


class TestRemoveWorktree(unittest.TestCase):
    """Test worktree removal."""

    def test_remove_worktree_calls_git(self):
        """Should call git worktree remove."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(returncode=0)
            result = yolo.remove_worktree(Path('/project'), Path('/project-worktrees/foo'))
            self.assertTrue(result)
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            self.assertIn('worktree', args)
            self.assertIn('remove', args)


class TestAttachMode(unittest.TestCase):
    """Test --attach functionality."""

    def test_attach_flag(self):
        """--attach should set attach to True."""
        args = yolo.parse_args(['--attach'])
        self.assertTrue(args.attach)

    def test_attach_default_false(self):
        """--attach should default to False."""
        args = yolo.parse_args([])
        self.assertFalse(args.attach)


class TestDetachMode(unittest.TestCase):
    """Test --detach functionality."""

    def test_detach_flag(self):
        """--detach should set detach to True."""
        args = yolo.parse_args(['--detach'])
        self.assertTrue(args.detach)

    def test_detach_short_flag(self):
        """-d should set detach to True."""
        args = yolo.parse_args(['-d'])
        self.assertTrue(args.detach)

    def test_detach_default_false(self):
        """--detach should default to False."""
        args = yolo.parse_args([])
        self.assertFalse(args.detach)

    def test_detach_with_tree(self):
        """--detach can combine with --tree."""
        args = yolo.parse_args(['--detach', '--tree', 'test'])
        self.assertTrue(args.detach)
        self.assertEqual(args.tree, 'test')


class TestFromBranch(unittest.TestCase):
    """Test --from BRANCH functionality."""

    def test_from_flag(self):
        """--from should set from_branch."""
        args = yolo.parse_args(['--tree', 'test', '--from', 'main'])
        self.assertEqual(args.from_branch, 'main')

    def test_from_default_none(self):
        """--from should default to None."""
        args = yolo.parse_args(['--tree', 'test'])
        self.assertIsNone(args.from_branch)

    def test_from_with_tree(self):
        """--from can combine with --tree."""
        args = yolo.parse_args(['--tree', 'feature', '--from', 'develop'])
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
        result = yolo.branch_exists(Path(self.tmpdir), 'master')
        self.assertTrue(result)

    def test_branch_exists_for_nonexistent_branch(self):
        """Should return False for nonexistent branch."""
        result = yolo.branch_exists(Path(self.tmpdir), 'nonexistent')
        self.assertFalse(result)


class TestVerboseMode(unittest.TestCase):
    """Test --verbose functionality."""

    def test_verbose_flag(self):
        """--verbose should set verbose to True."""
        args = yolo.parse_args(['--verbose'])
        self.assertTrue(args.verbose)

    def test_verbose_short_flag(self):
        """-v should set verbose to True."""
        args = yolo.parse_args(['-v'])
        self.assertTrue(args.verbose)

    def test_verbose_default_false(self):
        """--verbose should default to False."""
        args = yolo.parse_args([])
        self.assertFalse(args.verbose)


if __name__ == '__main__':
    unittest.main()
