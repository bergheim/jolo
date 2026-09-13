import pytest


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Tests must never write to the real ~/.config/jolo."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
