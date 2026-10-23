import json

import httpx
import pytest

from componentmatch_frontend.api_client import APIClient, APIError, UIConfig
from componentmatch_frontend.presentation import PRESETS, chart_rows, money, requirement_fields
from scripts.start_demo import check_database, database_freshness, frontend_environment
from tests.phase4_fakes import response_for


@pytest.mark.parametrize("scenario", list(PRESETS))
def test_all_presets_follow_real_graph_and_matching_contract(service, scenario):
    result, code = response_for(service, scenario)
    expected = {"信息缺失": "needs_clarification", "约束过严": "no_match"}.get(scenario, "success")
    assert code == 200 and result.status == expected
    if expected == "success":
        assert result.recommendations == service.match(result.requirement).recommendations
        assert (
            result.requirement.preference_profile
            == {
                "正常匹配": "balanced",
                "成本优先": "cost",
                "质量优先": "quality",
            }[scenario]
        )


@pytest.mark.parametrize(
    "scenario,error,status",
    [
        ("质量优先", False, "success"),
        ("信息缺失", False, "needs_clarification"),
        ("约束过严", False, "no_match"),
        ("质量优先", True, "error"),
    ],
)
def test_http_contract_all_outcomes(service, scenario, error, status):
    result, code = response_for(service, scenario, error=error)
    requests = []

    def handle(request):
        requests.append(request)
        assert request.method == "POST" and request.url.path == "/api/v1/agent/matches"
        assert "authorization" not in request.headers
        assert json.loads(request.content) == {"text": PRESETS[scenario]}
        assert request.extensions["timeout"]["read"] == 210
        return httpx.Response(code, json=result.model_dump(mode="json"))

    actual = APIClient(UIConfig(), transport=httpx.MockTransport(handle)).match(PRESETS[scenario])
    assert actual == result and actual.status == status
    assert len(requests) == 1
    if status == "success":
        assert actual.recommendations[0].total_score == result.recommendations[0].total_score
        assert actual.metadata.business_time == result.metadata.business_time


@pytest.mark.parametrize(
    "exception,code",
    [
        (httpx.ConnectError, "API_UNAVAILABLE"),
        (httpx.ReadTimeout, "API_TIMEOUT"),
    ],
)
def test_http_failures_safe_and_not_retried(exception, code):
    attempts = []

    def handle(request):
        attempts.append(True)
        raise exception("private-test-detail")

    with pytest.raises(APIError) as caught:
        APIClient(UIConfig(), transport=httpx.MockTransport(handle)).match("采购需求")
    assert caught.value.code == code
    assert "private-test-detail" not in str(caught.value)
    assert len(attempts) == 1


@pytest.mark.parametrize(
    "status,body",
    [(200, "not json"), (500, "private-error-body"), (422, '{"detail":"private-error-body"}')],
)
def test_invalid_response_is_not_rendered(status, body):
    client = APIClient(
        UIConfig(), transport=httpx.MockTransport(lambda request: httpx.Response(status, text=body))
    )
    with pytest.raises(APIError) as caught:
        client.match("采购需求")
    assert body not in str(caught.value)


def test_tampered_score_rejected_by_existing_contract(service):
    result, _ = response_for(service)
    payload = result.model_dump(mode="json")
    payload["recommendations"][0]["total_score"] = "99.999999"
    client = APIClient(
        UIConfig(), transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    with pytest.raises(APIError, match="无法识别"):
        client.match(PRESETS["质量优先"])


@pytest.mark.parametrize("text", ["", "   ", "长" * 2001])
def test_invalid_input_rejected_before_transport(text):
    with pytest.raises(APIError) as caught:
        APIClient(UIConfig()).match(text)
    assert caught.value.code == "INPUT_INVALID"


@pytest.mark.parametrize(
    "url",
    [
        "https://remote.example",
        "http://secret@127.0.0.1:8000",
        "http://127.0.0.1:8000/?key=private-value",
        "not-a-url",
    ],
)
def test_invalid_config_does_not_echo_url(monkeypatch, url):
    monkeypatch.setenv("COMPONENTMATCH_API_URL", url)
    with pytest.raises(APIError) as caught:
        UIConfig.from_env()
    assert url not in str(caught.value)


@pytest.mark.parametrize("seconds", ["90", "nan", "inf", "private-value"])
def test_timeout_must_cover_backend_budget(monkeypatch, seconds):
    monkeypatch.setenv("COMPONENTMATCH_HTTP_TIMEOUT_SECONDS", seconds)
    with pytest.raises(APIError):
        UIConfig.from_env()


def test_health_never_posts():
    def handle(request):
        assert request.method == "GET" and request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok"})

    assert APIClient(UIConfig(), transport=httpx.MockTransport(handle)).health()


def test_display_preserves_values_and_optional_fields(service):
    result, _ = response_for(service)
    rows = chart_rows(result)
    assert len(rows) == 15
    assert [r["得分"] for r in rows] == [
        float(d.score) for r in result.recommendations for d in r.dimensions
    ]
    assert money(0) == "¥0.00" and money(None) == "未提供"
    assert requirement_fields(result)["单价预算"] == "¥1.20"
    missing, _ = response_for(service, "信息缺失")
    assert requirement_fields(missing)["采购数量"] == "未明确"
    assert requirement_fields(missing)["总预算"] == "未提供"


def test_frontend_process_does_not_inherit_credentials():
    env = frontend_environment(
        {
            "PATH": "local-path",
            "DEEPSEEK_API_KEY": "private-key",
            "LANGSMITH_API_KEY": "private-trace",
            "DATABASE_URL": "private-db",
            "CUSTOM_SECRET": "private-secret",
        },
        8123,
    )
    assert env["COMPONENTMATCH_API_URL"] == "http://127.0.0.1:8123"
    assert not any("private" in v for v in env.values())
    assert env["PATH"] == "local-path"


def test_startup_database_check_readonly_and_missing_not_created(engine, tmp_path):
    path = tmp_path / "absent.db"
    with pytest.raises(FileNotFoundError):
        check_database({"DATABASE_URL": f"sqlite:///{path}"})
    assert not path.exists()
    assert len(check_database({"DATABASE_URL": str(engine.url)})) == 6


def test_freshness_check_warns_about_aged_data_without_refreshing_it(engine, now):
    from datetime import timedelta
    from pathlib import Path

    path = Path(engine.url.database)
    before = path.read_bytes()
    env = {"DATABASE_URL": str(engine.url)}
    current = database_freshness(env, now=now)
    later = database_freshness(env, now=now + timedelta(days=10))
    assert current["fresh_active_offers"] > 0
    assert later["fresh_active_offers"] == 0
    assert later["stale_offers"] > current["stale_offers"]
    assert path.read_bytes() == before
