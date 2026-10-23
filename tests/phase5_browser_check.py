"""Desktop/mobile checks against opt-in offline backend, not a real DeepSeek test."""

import json
import os
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    out = Path("logs/refactor")
    checks = {}
    with sync_playwright() as p:
        candidates = [
            Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
            Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
            Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
            Path(os.getenv("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ]
        chrome = next((path for path in candidates if path.is_file()), None)
        assert chrome, "Install Chrome or Edge before the manual browser check"
        browser = p.chromium.launch(headless=True, executable_path=str(chrome))
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page.route(
            "**/*",
            lambda route: (
                route.continue_()
                if route.request.url.startswith(
                    ("http://127.0.0.1:", "ws://127.0.0.1:", "data:", "blob:")
                )
                else route.abort()
            ),
        )
        page.goto("http://127.0.0.1:18510", wait_until="domcontentloaded")
        expect(page.get_by_role("heading", name="ComponentMatch Agent", exact=True)).to_be_visible()

        def assert_ai_only():
            expect(page.get_by_role("textbox", name="自然语言采购需求")).to_have_count(1)
            expect(page.get_by_role("radio")).to_have_count(0)
            expect(page.get_by_role("combobox")).to_have_count(0)
            expect(page.get_by_text("规则匹配", exact=False)).to_have_count(0)
            expect(page.get_by_text("运行模式", exact=False)).to_have_count(0)

        assert_ai_only()
        checks["single_natural_language_entry"] = True
        page.screenshot(path=str(out / "initial_ai_only.png"), full_page=True)

        def submit(label, expected):
            page.get_by_role("button", name=label, exact=True).click()
            phrase = {
                "正常匹配": "综合优先",
                "成本优先": "成本优先",
                "质量优先": "质量优先",
                "信息缺失": "^采购TI的LM358DR$",
                "约束过严": "1分",
            }[label]
            expect(page.get_by_role("textbox", name="自然语言采购需求")).to_have_value(
                re.compile(phrase)
            )
            page.get_by_role("button", name="开始匹配", exact=True).click()
            expect(page.get_by_text(expected, exact=False)).to_be_visible(timeout=20000)
            assert page.locator('[data-testid="stException"]').count() == 0
            checks[label] = True

        for label in ("正常匹配", "成本优先", "质量优先"):
            submit(label, "匹配完成，请核对需求")
            expect(page.get_by_text("综合评分", exact=True)).to_have_count(3)
        page.screenshot(path=str(out / "desktop_ai_mock.png"), full_page=True)
        page.get_by_text("指标、证据与风险", exact=True).first.click()
        page.get_by_text("Agent 工作流 · 实际执行轨迹", exact=True).click()
        page.get_by_text("查看原文依据与后端默认项", exact=True).click()
        page.screenshot(path=str(out / "evidence_mock.png"), full_page=True)
        checks["evidence_trace"] = True
        submit("信息缺失", "需要补充或澄清采购条件")
        expect(page.get_by_text("请补充采购数量", exact=False)).to_be_visible()
        page.get_by_role("textbox", name="补充采购条件", exact=True).fill("1000片，7天内到货")
        page.get_by_role("button", name="补充并重新匹配", exact=True).click()
        expect(page.get_by_text("匹配完成，请核对需求", exact=False)).to_be_visible(timeout=20000)
        checks["clarification_resubmit"] = True
        submit("约束过严", "当前条件下没有合格供应商")
        expect(page.get_by_text("综合评分", exact=True)).to_have_count(0)
        page.screenshot(path=str(out / "no_match_mock.png"), full_page=True)
        for suffix, expected in (
            ("测试超时", "模型调用超时，请稍后手动重试。"),
            ("测试解释降级", "解释模式：证据模板"),
        ):
            submit("质量优先", "匹配完成，请核对需求")
            box = page.get_by_role("textbox", name="自然语言采购需求")
            expect(box).to_have_value(re.compile("质量优先。$"))
            box.fill(box.input_value() + suffix)
            box.press("Tab")
            expect(page.get_by_text("输入已修改", exact=False)).to_be_visible()
            page.get_by_role("button", name="重新执行", exact=True).click()
            expect(page.get_by_text(expected, exact=False).first).to_be_visible(timeout=20000)
            checks[suffix] = True

        submit("正常匹配", "匹配完成，请核对需求")
        assert_ai_only()
        expect(page.get_by_text("Agent 工作流 · 实际执行轨迹", exact=True)).to_be_visible()
        expect(page.get_by_text("离线 Mock 响应", exact=False)).to_be_visible()
        checks["actual_trace_and_mock_source_visible"] = True
        page.get_by_text("供应商推荐 · 前 3 名", exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(out / "cards_ai_mock.png"))
        chart = page.locator('[data-testid="stVegaLiteChart"]')
        expect(chart).to_be_visible()
        chart.scroll_into_view_if_needed()
        page.screenshot(path=str(out / "chart_desktop.png"))
        page.set_viewport_size({"width": 390, "height": 844})
        collapse = page.locator('[data-testid="stSidebarCollapseButton"] button')
        if collapse.count() and collapse.is_visible():
            collapse.click()
        page.wait_for_timeout(1000)
        chart.scroll_into_view_if_needed()
        page.screenshot(path=str(out / "chart_mobile.png"))
        checks["mobile_no_horizontal_overflow"] = page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth + 2"
        )
        assert checks["mobile_no_horizontal_overflow"]
        page.screenshot(path=str(out / "mobile_ai_mock.png"), full_page=True)
        # Inspect rendered business text; raw JSON is intentionally in a closed technical panel.
        text = page.locator("body").inner_text()
        for token in (
            "UNIT_PRICE_OVER_LIMIT",
            "ratio",
            "calendar days",
            "CNY cents/pcs",
            "supplier_id",
        ):
            assert token not in text, token
        checks["business_text_chinese"] = True
        browser.close()
    report = {"mode": "real_local_http_with_explicit_mock_llm", "paid_calls": 0, "checks": checks}
    (out / "browser_result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
