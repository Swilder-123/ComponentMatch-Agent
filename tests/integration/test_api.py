from fastapi.testclient import TestClient

from componentmatch.api.main import app
from componentmatch.api.routes import get_matching_service
from componentmatch.db.session import make_engine
from componentmatch.services.matching import MatchingService


def test_structured_endpoint_and_openapi(service, build_requirement):
    app.dependency_overrides[get_matching_service] = lambda: service
    try:
        with TestClient(app) as client:
            body = {
                "input_mode": "structured",
                "requirement": build_requirement().model_dump(mode="json"),
            }
            response = client.post("/api/v1/matches", json=body)
            assert response.status_code == 200
            assert len(response.json()["recommendations"]) == 3
            assert response.json()["metadata"]["data_label"] == "DEMO"
            assert client.get("/health").json()["stage"] == "agent_matching"
            assert "/api/v1/matches" in client.get("/openapi.json").json()["paths"]
            body["requirement"]["quantity"] = True
            assert client.post("/api/v1/matches", json=body).status_code == 422
            body["input_mode"] = "natural_language"
            assert client.post("/api/v1/matches", json=body).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_uninitialized_database_is_500_not_no_match(tmp_path, build_requirement):
    engine = make_engine(f"sqlite:///{tmp_path / 'not-initialized.db'}")
    app.dependency_overrides[get_matching_service] = lambda: MatchingService(engine)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/matches", json={"requirement": build_requirement().model_dump(mode="json")}
            )
            assert response.status_code == 500
            assert response.json()["error"]["code"] == "DATABASE_ERROR"
            assert "Traceback" not in response.text
            assert response.json()["recommendations"] == []
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
