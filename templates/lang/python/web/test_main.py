from fastapi.testclient import TestClient

from {{PROJECT_NAME_UNDERSCORE}}.app import app

client = TestClient(app)


def test_home():
    response = client.get("/")
    assert response.status_code == 200
    assert "Hello, World!" in response.text
