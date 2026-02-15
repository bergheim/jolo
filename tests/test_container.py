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
        devcontainer_dir = Path(self.tmpdir) / ".devcontainer"
        devcontainer_dir.mkdir()
        (devcontainer_dir / "devcontainer.json").write_text(
            '{"old": "content"}'
        )

        # Sync with new config
        config = {"base_image": "new/image:v2"}
        jolo.sync_devcontainer("myproject", config=config)

        # Verify new content
        json_content = (devcontainer_dir / "devcontainer.json").read_text()
        self.assertIn('"name": "myproject"', json_content)
        self.assertIn('"image": "new/image:v2"', json_content)
        self.assertNotIn("old/image", json_content)

    def test_sync_creates_if_missing(self):
        """--sync should create .devcontainer if it doesn't exist."""
        os.chdir(self.tmpdir)

        config = {"base_image": "test/image:v1"}
        jolo.sync_devcontainer("newproject", config=config)

        devcontainer_dir = Path(self.tmpdir) / ".devcontainer"
        self.assertTrue(devcontainer_dir.exists())
        self.assertTrue((devcontainer_dir / "devcontainer.json").exists())


class TestContainerRuntime(unittest.TestCase):
    """Test container runtime detection."""

    def test_get_container_runtime_finds_docker(self):
        """Should detect docker if available."""
        with mock.patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda x: (
                "/usr/bin/docker" if x == "docker" else None
            )
            result = jolo.get_container_runtime()
            self.assertEqual(result, "docker")

    def test_get_container_runtime_finds_podman(self):
        """Should detect podman if docker not available."""
        with mock.patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda x: (
                "/usr/bin/podman" if x == "podman" else None
            )
            result = jolo.get_container_runtime()
            self.assertEqual(result, "podman")

    def test_get_container_runtime_prefers_docker(self):
        """Should prefer docker over podman."""
        with mock.patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/something"
            result = jolo.get_container_runtime()
            self.assertEqual(result, "docker")

    def test_get_container_runtime_returns_none(self):
        """Should return None if no runtime available."""
        with mock.patch("shutil.which", return_value=None):
            result = jolo.get_container_runtime()
            self.assertIsNone(result)


class TestListAllDevcontainers(unittest.TestCase):
    """Test global devcontainer listing."""

    def test_list_all_returns_empty_without_runtime(self):
        """Should return empty list if no container runtime."""
        with mock.patch("jolo.get_container_runtime", return_value=None):
            result = jolo.list_all_devcontainers()
            self.assertEqual(result, [])

    def test_list_all_parses_docker_output(self):
        """Should parse docker ps output correctly."""
        mock_output = "mycontainer\t/home/user/project\trunning\timg123\n"
        with mock.patch("jolo.get_container_runtime", return_value="docker"):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.Mock(
                    returncode=0, stdout=mock_output
                )
                result = jolo.list_all_devcontainers()
                self.assertEqual(len(result), 1)
                self.assertEqual(
                    result[0],
                    ("mycontainer", "/home/user/project", "running", "img123"),
                )


class TestGetContainerForWorkspace(unittest.TestCase):
    """Test container lookup by workspace."""

    def test_returns_none_without_runtime(self):
        """Should return None if no container runtime."""
        with mock.patch("jolo.get_container_runtime", return_value=None):
            result = jolo.get_container_for_workspace(Path("/some/path"))
            self.assertIsNone(result)

    def test_returns_container_name(self):
        """Should return container name from docker output."""
        with mock.patch("jolo.get_container_runtime", return_value="docker"):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.Mock(
                    returncode=0, stdout="my-container\n"
                )
                result = jolo.get_container_for_workspace(
                    Path("/home/user/project")
                )
                self.assertEqual(result, "my-container")

    def test_returns_none_when_no_container(self):
        """Should return None when no container found."""
        with mock.patch("jolo.get_container_runtime", return_value="docker"):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.Mock(returncode=0, stdout="")
                result = jolo.get_container_for_workspace(
                    Path("/home/user/project")
                )
                self.assertIsNone(result)


class TestStopContainer(unittest.TestCase):
    """Test container stopping."""

    def test_stop_returns_false_without_runtime(self):
        """Should return False if no container runtime."""
        with mock.patch("jolo.get_container_runtime", return_value=None):
            result = jolo.stop_container(Path("/some/path"))
            self.assertFalse(result)

    def test_stop_returns_false_when_no_container(self):
        """Should return False when no container found."""
        with mock.patch(
            "_jolo.container.get_container_runtime", return_value="docker"
        ):
            with mock.patch(
                "_jolo.container.get_container_for_workspace",
                return_value=None,
            ):
                result = jolo.stop_container(Path("/some/path"))
                self.assertFalse(result)

    def test_stop_returns_true_on_success(self):
        """Should return True when container stopped successfully."""
        with mock.patch(
            "_jolo.container.get_container_runtime", return_value="docker"
        ):
            with mock.patch(
                "_jolo.container.get_container_for_workspace",
                return_value="my-container",
            ):
                with mock.patch("subprocess.run") as mock_run:
                    mock_run.return_value = mock.Mock(returncode=0)
                    result = jolo.stop_container(Path("/some/path"))
                    self.assertTrue(result)


class TestRemoveContainer(unittest.TestCase):
    """Test container removal."""

    def test_remove_returns_false_without_runtime(self):
        """Should return False if no container runtime."""
        with mock.patch("jolo.get_container_runtime", return_value=None):
            result = jolo.remove_container("my-container")
            self.assertFalse(result)

    def test_remove_returns_true_on_success(self):
        """Should return True when container removed successfully."""
        with mock.patch("jolo.get_container_runtime", return_value="docker"):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.Mock(returncode=0)
                result = jolo.remove_container("my-container")
                self.assertTrue(result)


class TestRemoveImage(unittest.TestCase):
    """Test image removal."""

    def test_remove_image_returns_false_without_runtime(self):
        """Should return False if no container runtime."""
        with mock.patch(
            "_jolo.container.get_container_runtime", return_value=None
        ):
            from _jolo.container import remove_image

            result = remove_image("img123")
            self.assertFalse(result)

    def test_remove_image_returns_true_on_success(self):
        """Should return True when image removed successfully."""
        with mock.patch(
            "_jolo.container.get_container_runtime", return_value="docker"
        ):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.Mock(returncode=0)
                from _jolo.container import remove_image

                result = remove_image("img123")
                self.assertTrue(result)
                mock_run.assert_called_once_with(
                    ["docker", "rmi", "img123"],
                    capture_output=True,
                    text=True,
                )

    def test_remove_image_returns_false_on_failure(self):
        """Should return False when rmi fails."""
        with mock.patch(
            "_jolo.container.get_container_runtime", return_value="docker"
        ):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.Mock(returncode=1)
                from _jolo.container import remove_image

                result = remove_image("img123")
                self.assertFalse(result)


class TestIsContainerRunning(unittest.TestCase):
    """Test container running check."""

    def test_returns_false_without_runtime(self):
        """Should return False if no container runtime."""
        with mock.patch(
            "_jolo.container.get_container_runtime", return_value=None
        ):
            result = jolo.is_container_running(Path("/some/path"))
            self.assertFalse(result)

    def test_returns_true_when_running(self):
        """Should return True when container is running."""
        with mock.patch(
            "_jolo.container.get_container_runtime", return_value="docker"
        ):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.Mock(
                    returncode=0, stdout="my-container\n"
                )
                result = jolo.is_container_running(Path("/home/user/project"))
                self.assertTrue(result)

    def test_returns_false_when_not_running(self):
        """Should return False when no container running."""
        with mock.patch(
            "_jolo.container.get_container_runtime", return_value="docker"
        ):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.Mock(returncode=0, stdout="")
                result = jolo.is_container_running(Path("/home/user/project"))
                self.assertFalse(result)


class TestFindContainersForProject(unittest.TestCase):
    """Test project container discovery."""

    def test_returns_empty_without_runtime(self):
        """Should return empty list if no container runtime."""
        with mock.patch(
            "_jolo.container.get_container_runtime", return_value=None
        ):
            result = jolo.find_containers_for_project(Path("/home/user/myapp"))
            self.assertEqual(result, [])

    def test_finds_main_container(self):
        """Should find container for the main project directory."""
        containers = [
            ("myapp", "/home/user/myapp", "running", "img1"),
            ("other", "/home/user/other", "running", "img2"),
        ]
        with mock.patch(
            "_jolo.container.list_all_devcontainers", return_value=containers
        ):
            with mock.patch(
                "_jolo.container.get_container_runtime", return_value="docker"
            ):
                result = jolo.find_containers_for_project(
                    Path("/home/user/myapp")
                )
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0][0], "myapp")

    def test_finds_worktree_containers(self):
        """Should find containers for project worktrees."""
        containers = [
            ("myapp", "/home/user/myapp", "running", "img1"),
            (
                "myapp-feat",
                "/home/user/myapp-worktrees/feat",
                "running",
                "img2",
            ),
        ]
        with mock.patch(
            "_jolo.container.list_all_devcontainers", return_value=containers
        ):
            with mock.patch(
                "_jolo.container.get_container_runtime", return_value="docker"
            ):
                result = jolo.find_containers_for_project(
                    Path("/home/user/myapp")
                )
                self.assertEqual(len(result), 2)

    def test_state_filter(self):
        """Should filter by state when specified."""
        containers = [
            ("myapp", "/home/user/myapp", "running", "img1"),
            (
                "myapp-old",
                "/home/user/myapp-worktrees/old",
                "exited",
                "img2",
            ),
        ]
        with mock.patch(
            "_jolo.container.list_all_devcontainers", return_value=containers
        ):
            with mock.patch(
                "_jolo.container.get_container_runtime", return_value="docker"
            ):
                result = jolo.find_containers_for_project(
                    Path("/home/user/myapp"), state_filter="running"
                )
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0][0], "myapp")


class TestFindStoppedContainersForProject(unittest.TestCase):
    """Test stopped container discovery."""

    def test_returns_only_stopped(self):
        """Should return only non-running containers."""
        containers = [
            ("myapp", "/home/user/myapp", "running", "img1"),
            (
                "myapp-old",
                "/home/user/myapp-worktrees/old",
                "exited",
                "img2",
            ),
        ]
        with mock.patch(
            "_jolo.container.list_all_devcontainers", return_value=containers
        ):
            with mock.patch(
                "_jolo.container.get_container_runtime", return_value="docker"
            ):
                result = jolo.find_stopped_containers_for_project(
                    Path("/home/user/myapp")
                )
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0][0], "myapp-old")


class TestReassignPort(unittest.TestCase):
    """Test port reassignment."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ws = Path(self.tmpdir) / "project"
        self.ws.mkdir()
        (self.ws / ".devcontainer").mkdir()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def _write_config(self, config):
        path = self.ws / ".devcontainer" / "devcontainer.json"
        path.write_text(json.dumps(config, indent=4) + "\n")

    def _read_config(self):
        path = self.ws / ".devcontainer" / "devcontainer.json"
        return json.loads(path.read_text())

    def test_reassign_updates_port_in_env(self):
        """Should update PORT in containerEnv."""
        self._write_config(
            {
                "containerEnv": {"PORT": "4500"},
                "runArgs": ["-p", "4500:4500"],
            }
        )

        from _jolo.container import reassign_port

        with mock.patch("_jolo.container.random_port", return_value=4777):
            with mock.patch(
                "_jolo.container.is_port_available", return_value=True
            ):
                result = reassign_port(self.ws)

        self.assertEqual(result, 4777)
        config = self._read_config()
        self.assertEqual(config["containerEnv"]["PORT"], "4777")

    def test_reassign_updates_run_args(self):
        """Should update -p flag in runArgs."""
        self._write_config(
            {
                "containerEnv": {"PORT": "4500"},
                "runArgs": ["--name", "myapp", "-p", "4500:4500"],
            }
        )

        from _jolo.container import reassign_port

        with mock.patch("_jolo.container.random_port", return_value=4888):
            with mock.patch(
                "_jolo.container.is_port_available", return_value=True
            ):
                reassign_port(self.ws)

        config = self._read_config()
        self.assertIn("4888:4888", config["runArgs"])
        self.assertNotIn("4500:4500", config["runArgs"])

    def test_reassign_retries_until_available(self):
        """Should retry random_port when port is unavailable."""
        self._write_config(
            {
                "containerEnv": {"PORT": "4500"},
                "runArgs": ["-p", "4500:4500"],
            }
        )

        from _jolo.container import reassign_port

        with mock.patch(
            "_jolo.container.random_port", side_effect=[4001, 4002, 4003]
        ):
            with mock.patch(
                "_jolo.container.is_port_available",
                side_effect=[False, False, True],
            ):
                result = reassign_port(self.ws)

        self.assertEqual(result, 4003)


if __name__ == "__main__":
    unittest.main()
