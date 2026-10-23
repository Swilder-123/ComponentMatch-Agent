"""Display units, translation completeness, chart contract."""

import ast
import re
from decimal import Decimal
from pathlib import Path

import pytest
from componentmatch_frontend.presentation import (
    CODES,
    FIELDS,
    business_value,
    chart_rows,
    default_label,
    dimension_rows,
    duration_label,
    localized_text,
    raw_metric,
    score_chart,
)

from tests.phase4_fakes import response_for


def test_all_actual_error_and_risk_constants_translated():
    codes = set()
    for path in Path("backend/src").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if re.fullmatch(r"[A-Z]+(?:_[A-Z]+)+", node.value):
                    codes.add(node.value)
    # Engine constructs these names from a dimension prefix at runtime.
    codes.update(
        f"{prefix}_{suffix}"
        for prefix in ("QUALITY", "DELIVERY", "RESPONSE")
        for suffix in ("HISTORY_MISSING", "SAMPLE_SMALL")
    )
    assert codes <= CODES.keys()


def test_all_evidence_fields_have_chinese_business_names(service):
    result, _ = response_for(service)
    fields = {key for r in result.recommendations for e in r.evidence for key in e.fields}
    assert fields <= FIELDS.keys()


@pytest.mark.parametrize(
    "value,unit,expected",
    [
        ("120", "CNY cents/pcs", ("1.20", "元/片")),
        ("0.98", "ratio", ("98.00%", "百分比")),
        ("2", "hours", ("2", "小时")),
        ("7", "calendar days", ("7", "自然日")),
    ],
)
def test_display_unit_conversion(value, unit, expected):
    assert raw_metric(Decimal(value), unit) == expected


@pytest.mark.parametrize(
    "ms,expected", [(0, "<1 毫秒"), (0.999, "<1 毫秒"), (1, "1 毫秒"), (2.123, "2.123 毫秒")]
)
def test_trace_rounding_is_honest(ms, expected):
    assert duration_label(ms) == expected


def test_chart_only_reads_backend_scores_and_has_fixed_axis(service):
    result, _ = response_for(service)
    before = result.model_dump_json()
    spec = score_chart(result).to_dict()
    assert spec["encoding"]["x"]["scale"]["domain"] == [0, 100]
    assert spec["encoding"]["y"]["axis"]["labelAngle"] == 0
    assert spec["encoding"]["yOffset"]["field"] == "供应商"
    assert spec["encoding"]["color"]["scale"]["domain"] == [
        f"#{r.rank} {r.supplier_name}" for r in result.recommendations
    ]
    assert not spec.get("transform")
    assert [r["得分"] for r in chart_rows(result)] == [
        float(d.score) for r in result.recommendations for d in r.dimensions
    ]
    for row in result.recommendations:
        assert all(d["单位"] in {"元/片", "自然日", "百分比", "小时"} for d in dimension_rows(row))
    assert result.model_dump_json() == before


def test_defaults_and_known_backend_text_are_chinese():
    assert "非用户明确要求" in default_label("currency=CNY")
    assert "人民币" in default_label("currency=CNY")
    assert "未指定" in default_label("required_certifications=()")
    assert "采购数量" in localized_text("请补充quantity（完整型号/精确片数）")
    assert localized_text("原值0.98（ratio）") == "原值98.00%（百分比）"
    assert business_value("unit_price_cents", 120) == "¥1.20"
