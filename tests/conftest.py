"""Isolated, fixed-time DEMO databases; no production files or external services."""

import socket
from datetime import UTC, datetime

import httpx
import pytest
from componentmatch.core.clock import FixedClock
from componentmatch.db.repositories import candidates, find_components
from componentmatch.db.seed import seed_demo
from componentmatch.db.session import make_engine
from componentmatch.services.matching import MatchingService
from componentmatch_contracts.requirement import ProcurementRequirement

TEST_TIME = datetime(2026, 10, 21, 4, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Default tests must never open an external network connection")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", denied)

    async def async_denied(*args, **kwargs):
        denied()

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", async_denied)


@pytest.fixture
def now():
    return TEST_TIME


@pytest.fixture
def engine(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'isolated-demo.db'}")
    seed_demo(engine, test_business_time=TEST_TIME)
    yield engine
    engine.dispose()


@pytest.fixture
def service(engine):
    return MatchingService(engine, mode="test", clock=FixedClock(TEST_TIME))


@pytest.fixture
def build_requirement():
    def build(**overrides):
        values = dict(
            part_number="LM358DR",
            manufacturer="TI",
            quantity=1000,
            delivery_mode="within_days",
            max_delivery_days=7,
            required_certifications=("ISO9001",),
        )
        return ProcurementRequirement(**(values | overrides))

    return build


@pytest.fixture
def candidate(engine):
    from sqlalchemy.orm import Session

    with Session(engine) as session, session.begin():
        component = find_components(session, "LM358DR", "TI")[0]
        return next(c for c in candidates(session, component) if c.offer.id == 2)
