import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="session")
def test_client() -> TestClient:
    app = create_app()
    return TestClient(app)
