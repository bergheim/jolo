#!/usr/bin/env python3
"""Tests for container lifecycle."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import jolo
except ImportError:
    jolo = None


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
        mock_output = "mycontainer\t/home/user/project\trunning\timg123\n"
        with mock.patch('jolo.get_container_runtime', return_value='docker'):
            with mock.patch('subprocess.run') as mock_run:
                mock_run.return_value = mock.Mock(returncode=0, stdout=mock_output)
                result = jolo.list_all_devcontainers()
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0], ('mycontainer', '/home/user/project', 'running', 'img123'))


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
        with mock.patch('_jolo.container.get_container_runtime', return_value='docker'):
            with mock.patch('_jolo.container.get_container_for_workspace', return_value=None):
                result = jolo.stop_container(Path('/some/path'))
                self.assertFalse(result)

    def test_stop_returns_true_on_success(self):
        """Should return True when container stopped successfully."""
        with mock.patch('_jolo.container.get_container_runtime', return_value='docker'):
            with mock.patch('_jolo.container.get_container_for_workspace', return_value='my-container'):
                with mock.patch('subprocess.run') as mock_run:
                    mock_run.return_value = mock.Mock(returncode=0)
                    result = jolo.stop_container(Path('/some/path'))
                    self.assertTrue(result)


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


if __name__ == '__main__':
    unittest.main()
