"""Presentation-only transformations: labels, unit formatting, and chart rows."""

import re
from decimal import Decimal

import altair as alt

METRICS = {
    "price": "价格",
    "delivery": "交期",
    "quality": "质量",
    "on_time": "准时交付",
    "response": "响应服务",
}
PROFILES = {
    "balanced": "综合平衡",
    "cost": "成本优先",
    "delivery": "交期优先",
    "quality": "质量优先",
}
BASE_TEXT = "采购TI的LM358DR，1000片，7天内到货，单价不超过1.2元，总预算不超过1200元，必须ISO9001，"
PRESETS = {
    "正常匹配": BASE_TEXT + "综合优先。",
    "成本优先": BASE_TEXT + "成本优先。",
    "质量优先": BASE_TEXT + "质量优先。",
    "信息缺失": "采购TI的LM358DR",
    "约束过严": BASE_TEXT.replace("1.2元", "1分") + "质量优先。",
}
NODES = {
    "parse_request": "需求解析",
    "validate_request": "参数校验",
    "retrieve_candidates": "供应商查询",
    "filter_candidates": "硬约束筛选",
    "score_and_rank": "综合评分与排序",
    "explain_results": "证据约束解释",
    "request_clarification": "请求补充条件",
    "build_no_match": "汇总无匹配原因",
    "handle_error": "处理异常",
    "finalize_response": "组织最终响应",
}
NODE_PURPOSES = {
    "parse_request": "提取采购条件及原文依据",
    "validate_request": "核对缺失、冲突和不支持条件",
    "retrieve_candidates": "按精确型号读取供应商报价",
    "filter_candidates": "检查库存、交期、预算、资质及时效",
    "score_and_rank": "按既定权重计算并返回排名",
    "explain_results": "选择证据解释，失败时回退模板",
    "request_clarification": "返回需要用户补充的问题",
    "build_no_match": "汇总无匹配及排除原因",
    "handle_error": "组织安全的异常信息",
    "finalize_response": "校验并返回完整结果",
}
ERROR_HINTS = {
    "CONFIG_MISSING": "后端未配置模型凭据，请在后端本地配置后重试。",
    "LLM_AUTH_ERROR": "模型认证失败，请检查后端凭据与账户权限。",
    "LLM_BALANCE_ERROR": "模型账户余额不足，请检查服务商账户。",
    "LLM_RATE_LIMIT": "模型服务限流，请稍后手动重试。",
    "LLM_TIMEOUT": "模型调用超时，请稍后手动重试。",
    "AGENT_TIMEOUT": "本次处理超过后端时间预算，请稍后手动重试。",
    "UNSUPPORTED_CONSTRAINT": "存在当前无法验证的硬条件，请核对条件说明并修订需求。",
    "DATABASE_ERROR": "后端数据库不可用，请检查初始化及数据库路径。",
}

FIELDS = {
    "part_number": "元器件型号",
    "manufacturer": "制造商",
    "quantity": "采购数量",
    "delivery_mode": "交期要求类型",
    "max_delivery_days": "最长交期",
    "max_unit_price_cents": "单价预算上限",
    "total_budget_cents": "总预算上限",
    "max_unit_price": "单价预算",
    "total_budget": "总预算",
    "required_certifications": "必需资质",
    "preference_profile": "采购偏好",
    "currency": "货币单位",
    "supplier_id": "供应商编号",
    "offer_id": "报价编号",
    "component_id": "元器件编号",
    "risk_code": "风险类型",
    "reason_code": "原因类型",
    "evidence_id": "证据编号",
    "unit_price_cents": "含税单价",
    "goods_total_cents": "货款总额",
    "available_quantity": "可用库存",
    "min_order_quantity": "最小起订量",
    "order_multiple": "订购倍数",
    "lead_time_days": "到货交期",
    "observed_at": "采集时间",
    "valid_until": "报价有效期至",
    "status": "状态",
    "supplier.status": "供应商状态",
    "offer.status": "报价状态",
    "name": "名称",
    "part_number_key": "型号标准索引",
    "manufacturer_key": "制造商标准索引",
    "reference_unit_price_cents": "模拟参考单价",
    "reference_currency": "参考币种",
    "reference_observed_at": "参考价采集时间",
    "certification_code": "证书类型",
    "valid_from": "证书生效日期",
    "expires_on": "证书到期日期",
    "verified_at": "模拟核验时间",
    "verification_status": "模拟核验状态",
    "period_start": "统计期开始",
    "period_end": "统计期结束",
    "quality_evaluated_orders": "质量评估订单数",
    "inspected_units": "检验片数",
    "accepted_units": "合格片数",
    "orders_due": "到期订单数",
    "orders_on_time": "准时交付订单数",
    "response_minutes_total": "累计响应分钟数",
    "response_samples": "响应样本数",
}
TABLES = {
    "offers": "报价",
    "components": "元器件",
    "suppliers": "供应商",
    "supplier_certifications": "资质记录",
    "performance_records": "历史绩效",
    "certification": "资质记录",
}
VALUES = {
    "CNY": "人民币",
    "balanced": "综合平衡",
    "cost": "成本优先",
    "quality": "质量优先",
    "delivery": "交期优先",
    "within_days": "限定自然日",
    "unconstrained": "交期不限",
    "unspecified": "未明确",
    "active": "可用",
    "inactive": "停用",
    "suspended": "暂停供货",
    "withdrawn": "已撤回",
    "verified": "已核验（模拟）",
    "unverified": "未核验",
    "revoked": "已撤销",
    "pending": "待核验",
    "valid verified certificate": "有效且已核验的模拟证书",
    "()": "未指定",
    "text": "用户原文",
    "confirmed_fields": "用户确认",
    "success": "成功",
    "error": "失败",
    "running": "继续处理",
    "needs_clarification": "需要澄清",
    "no_match": "无匹配",
}
CODES = {
    "EXPLANATION_NO_SUPPORTED_REASONS": "可用解释理由不足，直接使用事实模板",
    "CURRENCY_UNSUPPORTED": "不支持该货币单位",
    "SUPPLIER_MISMATCH": "报价与供应商身份不一致",
    "COMPONENT_MISMATCH": "完整型号或制造商不匹配",
    "SUPPLIER_INACTIVE": "供应商当前不可用",
    "OFFER_INACTIVE": "报价已撤回",
    "OFFER_DATA_MISSING": "报价必要数据缺失",
    "OFFER_DATA_INVALID": "报价数据无效",
    "FUTURE_DATA": "数据采集时间在业务时间之后",
    "OFFER_EXPIRED": "报价已过有效期",
    "OFFER_STALE": "报价数据超过七日时效限制",
    "INSUFFICIENT_STOCK": "库存不足",
    "MOQ_NOT_MET": "未达到最小起订量",
    "ORDER_MULTIPLE_MISMATCH": "采购数量不符合订购倍数",
    "DELIVERY_TOO_SLOW": "超出交期要求",
    "UNIT_PRICE_OVER_LIMIT": "超出单价预算",
    "TOTAL_BUDGET_EXCEEDED": "超出采购总预算",
    "CERT_MISSING": "缺少必需资质",
    "CERT_REVOKED": "资质已撤销",
    "CERT_UNVERIFIED": "供应商资质未通过核验",
    "CERT_VERIFICATION_MISSING": "缺少资质核验记录",
    "CERT_VERIFICATION_FUTURE": "资质核验时间在未来",
    "CERT_EXPIRED": "资质已到期",
    "CERT_NOT_YET_VALID": "资质尚未生效",
    "MOCK_DATA_ONLY": "仅供 DEMO 演示的模拟数据",
    "LOW_PRICE_REVIEW": "模拟报价偏低，需人工复核",
    "PRICE_REFERENCE_UNAVAILABLE": "参考价缺失或失效",
    "HISTORY_ROW_INVALID": "无效或重复历史已剔除",
    "HISTORY_STALE": "历史绩效数据过期",
    "HISTORY_MISSING": "历史绩效数据缺失",
    "HISTORY_PARTIAL_WINDOW": "六个月历史记录不齐全",
    "QUALITY_HISTORY_MISSING": "缺少质量历史样本",
    "QUALITY_SAMPLE_SMALL": "质量历史样本不足",
    "DELIVERY_HISTORY_MISSING": "缺少准时交付历史样本",
    "DELIVERY_SAMPLE_SMALL": "准时交付历史样本不足",
    "RESPONSE_HISTORY_MISSING": "缺少响应历史样本",
    "RESPONSE_SAMPLE_SMALL": "响应历史样本不足",
    "STOCK_TIGHT": "模拟库存余量较少",
    "NO_DELIVERY_BUFFER": "交期没有余量",
    "CERT_EXPIRING_SOON": "模拟证书即将到期",
    "CATALOG_NOT_FOUND": "目录未找到精确型号",
    "NO_OFFERS": "该型号无报价记录",
    "NO_ELIGIBLE_OFFERS": "全部报价未通过硬约束",
    "CONFIG_MISSING": "后端未配置模型凭据",
    "LLM_CONFIG_ERROR": "模型配置不正确",
    "LLM_AUTH_ERROR": "模型认证失败",
    "LLM_BALANCE_ERROR": "模型账户余额不足",
    "LLM_RATE_LIMIT": "模型服务限流",
    "LLM_TIMEOUT": "模型调用超时",
    "LLM_UNAVAILABLE": "模型服务暂不可用",
    "LLM_CONNECTION_ERROR": "模型连接失败",
    "LLM_SCHEMA_INVALID": "模型输出字段校验失败",
    "LLM_JSON_INVALID": "模型输出不是有效 JSON",
    "LLM_CALL_FAILED": "模型调用失败",
    "LLM_TRUNCATED": "模型输出被截断",
    "LLM_FINISH_INVALID": "模型输出未正常结束",
    "LLM_EMPTY_CONTENT": "模型返回空内容",
    "LLM_EVIDENCE_INVALID": "模型提取缺少有效原文依据",
    "EXPLANATION_EVIDENCE_INVALID": "模型解释未通过证据校验",
    "AGENT_TIMEOUT": "处理超过后端时间预算",
    "UNSUPPORTED_CONSTRAINT": "存在无法验证的硬条件",
    "DATABASE_ERROR": "数据库读取失败",
    "DATA_INVALID": "数据或结果契约无效",
    "INTERNAL_ERROR": "工作流内部错误",
    "WORKFLOW_ERROR": "工作流执行失败",
    "EXPLANATION_FAILED": "推荐解释失败",
    "UI_CONFIG_ERROR": "前端连接配置无效",
    "API_TIMEOUT": "后端响应超时",
    "API_UNAVAILABLE": "无法连接后端",
    "HEALTH_FAILED": "后端健康检查未通过",
    "INPUT_INVALID": "采购输入无效",
    "REQUEST_REJECTED": "请求未通过后端校验",
    "INVALID_RESPONSE": "后端响应契约不符",
    "HTTP_ERROR": "后端响应异常",
}


def code_label(code):
    return CODES.get(code, "未分类情况，请查看技术详情")


def field_label(field):
    return FIELDS.get(field, "其他条件")


def evidence_ref(ref):
    table, _, number = ref.partition(":")
    return f"{TABLES.get(table, '证据')} #{number}"


def business_value(field, value):
    if value is None:
        return "未提供"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (tuple, list)):
        return "、".join(map(str, value)) or "未指定"
    if field.endswith("_cents"):
        try:
            return money(Decimal(str(value)))
        except ArithmeticError:
            pass
    return VALUES.get(str(value), str(value))


def localized_text(text):
    # Translate only known backend tokens, leaving original user quotes untouched elsewhere.
    text = re.sub(
        r"原值([0-9.]+)（(CNY cents/pcs|calendar days|ratio|hours)）",
        lambda m: (
            "原值"
            + raw_metric(Decimal(m[1]), m[2])[0]
            + "（"
            + raw_metric(Decimal(m[1]), m[2])[1]
            + "）"
        ),
        text,
    )
    for token, label in sorted((CODES | FIELDS).items(), key=lambda p: -len(p[0])):
        text = re.sub(
            r"(?<![A-Za-z_])" + re.escape(token) + r"(?![A-Za-z_])", lambda _: label, text
        )
    return text.replace("人民币CNY", "人民币").replace("分/pcs", "分/片")


def raw_metric(value, unit):
    units = {
        "CNY cents/pcs": "元/片",
        "calendar days": "自然日",
        "ratio": "百分比",
        "hours": "小时",
    }
    if value is None:
        return "缺失", units.get(unit, "未知单位")
    if unit == "CNY cents/pcs":
        return f"{value / 100:.2f}", "元/片"
    if unit == "ratio":
        return f"{value:.2%}", "百分比"
    return str(value), units.get(unit, "未知单位")


def duration_label(ms):
    # Backend rounds monotonic elapsed time to 0.001 ms; zero is below that precision.
    if ms < 1:
        return "<1 毫秒"
    return f"{ms:g} 毫秒"


def default_label(default):
    field, _, value = default.partition("=")
    return f"{field_label(field)}：{business_value(field, value)}（后端默认，非用户明确要求）"


def extraction_value(result, field):
    if result.requirement:
        return business_value(field, getattr(result.requirement, field, None))
    if result.draft:
        if field in {"max_unit_price_cents", "total_budget_cents"}:
            name = {"max_unit_price_cents": "max_unit_price", "total_budget_cents": "total_budget"}[
                field
            ]
            return draft_money(getattr(result.draft, name))
        return business_value(field, getattr(result.draft, field, None))
    return "未提供"


def score_chart(result):
    suppliers = [f"#{r.rank} {r.supplier_name}" for r in result.recommendations]
    return (
        alt.Chart(alt.Data(values=chart_rows(result)))
        .mark_bar()
        .encode(
            x=alt.X("得分:Q", scale=alt.Scale(domain=[0, 100], nice=False), title="得分（0～100）"),
            y=alt.Y(
                "评分维度:N",
                sort=list(METRICS.values()),
                title=None,
                axis=alt.Axis(labelAngle=0, labelLimit=100),
            ),
            yOffset=alt.YOffset("供应商:N", sort=suppliers),
            color=alt.Color(
                "供应商:N",
                scale=alt.Scale(
                    domain=suppliers, range=["#2563eb", "#0d9488", "#d97706"][: len(suppliers)]
                ),
                legend=alt.Legend(orient="bottom", columns=1, labelLimit=280, title=None),
            ),
            tooltip=["供应商:N", "评分维度:N", alt.Tooltip("得分:Q", format=".6f")],
        )
        .properties(height=340)
        .configure_axis(labelFontSize=12)
    )


def money(cents):
    return "未提供" if cents is None else f"¥{Decimal(cents) / 100:,.2f}"


def draft_money(mention):
    if mention is None:
        return "未提供"
    unit = "元" if mention.unit == "CNY_yuan" else "分"
    return f"{mention.amount} {unit}（待校验）"


def requirement_fields(result):
    value = result.requirement or result.draft
    if value is None:
        return {}
    delivery = (
        f"{value.max_delivery_days} 个自然日内"
        if value.max_delivery_days is not None
        else "交期不限"
        if value.delivery_mode == "unconstrained"
        else "未明确"
    )
    fields = {
        "制造商": value.manufacturer or "未明确",
        "元器件型号": value.part_number or "未明确",
        "采购数量": f"{value.quantity:,} 片" if value.quantity is not None else "未明确",
        "交期要求": delivery,
        "单价预算": money(value.max_unit_price_cents)
        if result.requirement
        else draft_money(value.max_unit_price),
        "总预算": money(value.total_budget_cents)
        if result.requirement
        else draft_money(value.total_budget),
        "必需证书": "、".join(value.required_certifications or ()) or "未指定",
        "采购偏好": PROFILES.get(value.preference_profile, "未明确"),
    }
    default_fields = {d.partition("=")[0] for d in getattr(result, "applied_defaults", ())}
    for field, label in (
        ("preference_profile", "采购偏好"),
        ("required_certifications", "必需证书"),
    ):
        if field in default_fields and result.requirement:
            fields[label] += "（后端默认）"
    return fields


def chart_rows(result):
    # float conversion is for chart rendering only; no weighted sums or ranking here.
    return [
        {
            "评分维度": METRICS[d.metric],
            "供应商": f"#{r.rank} {r.supplier_name}",
            "得分": float(d.score),
        }
        for r in result.recommendations
        for d in r.dimensions
    ]


def dimension_rows(row):
    return [
        {
            "维度": METRICS[d.metric],
            "原始指标": raw_metric(d.raw_value, d.raw_unit)[0],
            "单位": raw_metric(d.raw_value, d.raw_unit)[1],
            "得分": str(d.score),
            "权重": f"{d.weight:.0%}",
            "加权贡献": str(d.contribution),
            "证据引用": "、".join(evidence_ref(ref) for ref in d.evidence_ids),
        }
        for d in row.dimensions
    ]
