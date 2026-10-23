"""Export clearly labeled MOCK HTTP examples using a real graph and isolated test database."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from componentmatch.agent.graph import AgentWorkflow
from componentmatch.api.agent_routes import get_agent_workflow
from componentmatch.api.main import app
from componentmatch.core.clock import FixedClock
from componentmatch.core.config import Settings
from componentmatch.db.seed import seed_demo
from componentmatch.db.session import make_engine
from componentmatch.llm.client import JSONModel
from componentmatch.services.matching import MatchingService
from tests.agent_fakes import TEXT, FakeTransport
from tests.conftest import TEST_TIME


def export():
    destination = Path("docs/examples")
    destination.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="componentmatch-mock-") as folder:
        engine = make_engine(f"sqlite:///{Path(folder) / 'demo.db'}")
        try:
            seed_demo(engine, test_business_time=TEST_TIME)
            service = MatchingService(engine, mode="test", clock=FixedClock(TEST_TIME))
            workflow = AgentWorkflow(
                service, JSONModel(FakeTransport(), Settings(llm_max_retries=0))
            )
            app.dependency_overrides[get_agent_workflow] = lambda: workflow
            with TestClient(app) as client:
                body = {"text": TEXT}
                response = client.post("/api/v1/agent/matches", json=body)
            response.raise_for_status()
            result = response.json()
            if result["status"] != "success" or any(
                c["source"] != "mock" for c in result["llm_calls"]
            ):
                raise ValueError("Expected explicitly MOCK successful example")
            for name, contents in (
                ("agent_request.json", body),
                ("agent_response.mock.json", result),
            ):
                (destination / name).write_text(
                    json.dumps(contents, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
            Path("docs/agent_workflow.mmd").write_text(
                workflow.graph.get_graph().draw_mermaid(), encoding="utf-8"
            )
            print("Exported MOCK examples and actual compiled graph; no provider API calls")
        finally:
            app.dependency_overrides.clear()
            engine.dispose()


if __name__ == "__main__":
    export()
