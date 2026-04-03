from fastapi.testclient import TestClient


def test_health_check_returns_ok(test_client: TestClient) -> None:
    response = test_client.get("/api/v1/health")
    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "ok"
    assert "service" in body
    assert "environment" in body


def test_health_check_content_type(test_client: TestClient) -> None:
    response = test_client.get("/api/v1/health")
    assert "application/json" in response.headers["content-type"]
