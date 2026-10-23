import json
from pathlib import Path

import httpx
import pytest
from componentmatch_frontend.api_client import APIClient
from componentmatch_frontend.presentation import PRESETS
from streamlit.testing.v1 import AppTest

from tests.phase4_fakes import response_for


def mock_http(monkeypatch, responses):
    sent = []
    original = APIClient.__init__

    def handle(request):
        assert request.method == "POST"
        assert request.url.path == "/api/v1/agent/matches"
        sent.append(json.loads(request.content))
        result, code = responses[min(len(sent) - 1, len(responses) - 1)]
        return httpx.Response(code, json=result.model_dump(mode="json"))

    def init(self, config=None, **kwargs):
        original(self, config, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(APIClient, "__init__", init)
    return sent


def app():
    path = Path(__file__).resolve().parents[2] / "frontend" / "app.py"
    return AppTest.from_file(path, default_timeout=15).run()


def test_initial_page_and_presets_never_submit():
    page = app()
    assert not page.exception
    for index, text in enumerate(PRESETS.values()):
        page.button(key=f"preset_{index}").click().run()
        assert page.text_area(key="request_text").value == text
        assert page.session_state["result"] is None
    page.button(key="clear").click().run()
    assert page.text_area(key="request_text").value == ""
    assert not page.exception


@pytest.mark.parametrize(
    "scenario,error,status",
    [
        ("质量优先", False, "success"),
        ("信息缺失", False, "needs_clarification"),
        ("约束过严", False, "no_match"),
        ("质量优先", True, "error"),
    ],
)
def test_ui_four_outcomes_mock_http(service, monkeypatch, scenario, error, status):
    result = response_for(service, scenario, error=error)
    sent = mock_http(monkeypatch, [result])
    page = app()
    page.text_area(key="request_text").set_value(PRESETS[scenario])
    page.button(key="submit").click().run()
    assert not page.exception
    assert page.session_state["result"].status == status
    assert len(sent) == 1
    assert not page.session_state["busy"]
    page.run()  # Display reruns must not repeat a paid POST.
    assert len(sent) == 1
    if status == "success":
        assert len(page.get("vega_lite_chart")) == 1
        assert any("Mock" in w.value for w in page.warning)
        scores = [m.value for m in page.metric if m.label == "综合评分"]
        assert scores == [f"{r.total_score:.2f}" for r in result[0].recommendations]
    elif status == "no_match":
        assert not any(m.label == "综合评分" for m in page.metric)
    elif status == "error":
        assert any("超时" in e.value for e in page.error)


def test_clarification_preserves_original_and_never_confirms_implicitly(service, monkeypatch):
    responses = [response_for(service, "信息缺失"), response_for(service, "质量优先")]
    sent = mock_http(monkeypatch, responses)
    page = app()
    page.button(key="preset_3").click().run()
    page.button(key="submit").click().run()
    original = page.text_area(key="request_text").value
    assert original == PRESETS["信息缺失"]
    page.text_area(key="clarification_text").set_value("1000片，7天内到货")
    page.button(key="clarify_submit").click().run()
    assert not page.exception
    assert len(sent) == 2
    assert sent[-1] == {"text": original + "\n补充需求：1000片，7天内到货"}
    assert page.text_area(key="request_text").value == sent[-1]["text"]


def test_explicit_confirmation_uses_fields_without_appending_conflicting_text(service, monkeypatch):
    sent = mock_http(monkeypatch, [response_for(service, "信息缺失"), response_for(service)])
    page = app()
    page.button(key="preset_3").click().run()
    page.button(key="submit").click().run()
    original = page.text_area(key="request_text").value
    page.multiselect(key="confirmation_fields").set_value(["quantity", "delivery_mode"]).run()
    page.number_input(key="confirm_value_quantity").set_value(1000)
    page.selectbox(key="confirm_value_delivery_mode").set_value("within_days").run()
    page.number_input(key="confirm_value_max_delivery_days").set_value(7)
    page.button(key="confirm_submit").click().run()
    assert not page.exception
    assert sent[-1] == {
        "text": original,
        "confirmed_fields": {
            "quantity": 1000,
            "delivery_mode": "within_days",
            "max_delivery_days": 7,
        },
    }
    page.button(key="submit").click().run()
    assert sent[-1]["confirmed_fields"]["quantity"] == 1000
    page.text_area(key="request_text").set_value("采购全新需求").run()
    page.button(key="submit").click().run()
    assert sent[-1] == {"text": "采购全新需求"}


def test_missing_selected_confirmation_value_sends_no_request(service, monkeypatch):
    sent = mock_http(monkeypatch, [response_for(service, "信息缺失")])
    page = app()
    page.button(key="preset_3").click().run()
    page.button(key="submit").click().run()
    page.multiselect(key="confirmation_fields").set_value(["quantity"]).run()
    page.button(key="confirm_submit").click().run()
    assert len(sent) == 1 and page.error and not page.exception


def test_supplementation_does_not_silently_reuse_old_confirmation(service, monkeypatch):
    sent = mock_http(monkeypatch, [response_for(service, "信息缺失")])
    page = app()
    page.button(key="preset_3").click().run()
    page.button(key="submit").click().run()
    page.multiselect(key="confirmation_fields").set_value(["quantity"]).run()
    page.number_input(key="confirm_value_quantity").set_value(1000)
    page.button(key="confirm_submit").click().run()
    assert sent[-1]["confirmed_fields"] == {"quantity": 1000}
    page.text_area(key="clarification_text").set_value("改为2000片，7天内到货")
    page.button(key="clarify_submit").click().run()
    assert not page.exception and "confirmed_fields" not in sent[-1]
    assert sent[-1]["text"].endswith("改为2000片，7天内到货")


def test_template_visible_and_edit_does_not_mislabel_previous_result(service, monkeypatch):
    sent = mock_http(monkeypatch, [response_for(service, template=True)])
    page = app()
    page.button(key="preset_2").click().run()
    page.button(key="submit").click().run()
    assert any("证据模板" in w.value for w in page.warning)
    page.text_area(key="request_text").set_value("新的采购需求").run()
    assert any("上次提交" in i.value for i in page.info)
    assert len(sent) == 1
    page.button(key="clear").click().run()
    assert page.session_state["result"] is None
    assert not page.exception


def test_connection_error_releases_submit_and_hides_exception(monkeypatch):
    original = APIClient.__init__

    def handle(request):
        raise httpx.ConnectError("private-exception")

    def init(self, config=None, **kwargs):
        original(self, config, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(APIClient, "__init__", init)
    page = app()
    page.button(key="preset_0").click().run()
    page.button(key="submit").click().run()
    assert not page.exception
    assert any("FastAPI" in e.value for e in page.error)
    assert not any("private-exception" in e.value for e in page.error)
    assert not page.button(key="submit").disabled


def test_busy_state_disables_actions():
    page = app()
    page.session_state["busy"] = True
    page.run()
    assert page.button(key="submit").disabled
    assert page.button(key="clear").disabled
    assert all(page.button(key=f"preset_{i}").disabled for i in range(5))


def test_only_natural_language_entry_and_no_rule_state():
    page = app()
    assert not page.exception
    assert len(page.text_area) == 1
    assert page.text_area[0].key == "request_text"
    assert not page.radio and not page.selectbox and not page.multiselect
    assert not page.number_input and not page.text_input and not page.toggle and not page.checkbox
    keys = page.session_state.keys()
    assert "mode" not in keys
    assert not any(k.startswith("rule_") or k in {"pending_rule", "submitted_rule"} for k in keys)
    assert all(page.button(key=f"preset_{i}") for i in range(5))


def test_mock_source_and_template_fallback_never_claim_real_success(service, monkeypatch):
    mock_http(monkeypatch, [response_for(service, template=True)])
    page = app()
    page.button(key="preset_2").click().run()
    page.button(key="submit").click().run()
    assert any("离线 Mock" in w.value for w in page.warning)
    assert any("证据模板" in w.value for w in page.warning)
    assert not any("模型调用来源：DeepSeek" in c.value for c in page.caption)
    assert any("实际执行轨迹" in e.label for e in page.expander)
    assert not page.exception
