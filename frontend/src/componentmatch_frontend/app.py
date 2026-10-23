"""Chinese procurement workbench. All business results come from FastAPI."""

import streamlit as st

from componentmatch_contracts.agent import AgentRequest
from componentmatch_frontend.api_client import APIClient, APIError, UIConfig
from componentmatch_frontend.clarification import (
    collect_confirmations,
    render_confirmations,
    reset_confirmation_widgets,
)
from componentmatch_frontend.presentation import (
    ERROR_HINTS,
    METRICS,
    NODE_PURPOSES,
    NODES,
    PRESETS,
    TABLES,
    VALUES,
    business_value,
    code_label,
    default_label,
    dimension_rows,
    duration_label,
    evidence_ref,
    extraction_value,
    field_label,
    localized_text,
    money,
    requirement_fields,
    score_chart,
)

CSS = """
<style>
.block-container {max-width:1440px; padding-top:1rem; padding-bottom:2rem;}
[data-testid="stSidebar"] {border-right:1px solid #dde5f0;}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius:14px;}
[data-testid="stMetricValue"] {font-variant-numeric:tabular-nums;}
.eyebrow {color:#2563eb; font-size:.76rem; font-weight:700; letter-spacing:.16em;}
.hero {background:#132642; color:#fff; padding:16px 24px; border-radius:16px; margin-bottom:12px;}
.hero h1 {color:#fff; font-size:1.9rem; padding:0 0 8px;}
.hero p {color:#c5d5eb; margin:0;}
.demo-tag {display:inline-block; color:#bfdbfe; background:#254467;
  font-size:.72rem; padding:3px 9px; border-radius:5px; margin-bottom:12px;}
@media(max-width:700px) {.block-container {padding:1rem;} .hero {padding:20px;}}
</style>
"""


def init_state():
    defaults = {
        "request_text": "",
        "clarification_text": "",
        "result": None,
        "submitted_text": "",
        "ui_error": None,
        "pending_text": None,
        "busy": False,
        "health_message": None,
        "confirmed_fields": {},
        "pending_confirmed_fields": {},
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def set_request(text):
    if st.session_state.busy:
        return
    st.session_state.request_text = text
    st.session_state.clarification_text = ""
    st.session_state.result = None
    st.session_state.ui_error = None
    st.session_state.submitted_text = ""
    st.session_state.confirmed_fields = {}
    reset_confirmation_widgets()


def queue_request(supplement=False, confirm=False):
    if st.session_state.busy:
        return
    text = st.session_state.request_text
    same_input = text == st.session_state.submitted_text
    confirmed = dict(st.session_state.confirmed_fields) if same_input else {}
    if supplement:
        extra = st.session_state.clarification_text.strip()
        if not extra:
            st.session_state.ui_error = "请先填写需要补充的条件。"
            return
        text += "\n补充需求：" + extra
        # Supplementation changes the source text; discard old overrides.
        confirmed = {}
    try:
        if confirm:
            confirmed.update(collect_confirmations())
        AgentRequest(text=text, confirmed_fields=confirmed)
    except ValueError:
        st.session_state.ui_error = (
            "请填写有效采购需求和所选确认字段；数量须为正整数，交期须为非负整数。"
        )
        return
    st.session_state.request_text = text
    st.session_state.submitted_text = text
    st.session_state.clarification_text = ""
    st.session_state.result = None
    st.session_state.ui_error = None
    st.session_state.pending_text = text
    st.session_state.pending_confirmed_fields = confirmed
    st.session_state.confirmed_fields = confirmed
    reset_confirmation_widgets()
    st.session_state.busy = True


def render_sidebar(client):
    with st.sidebar:
        st.markdown('<div class="eyebrow">采购决策工作台</div>', unsafe_allow_html=True)
        st.header("采购需求")
        st.caption("先选一个案例，或直接描述你的采购条件。")
        for index, (label, text) in enumerate(PRESETS.items()):
            st.button(
                label,
                key=f"preset_{index}",
                width="stretch",
                disabled=st.session_state.busy,
                on_click=set_request,
                args=(text,),
            )
        st.text_area(
            "自然语言采购需求",
            key="request_text",
            height=210,
            max_chars=2000,
            placeholder="例如：采购 TI 的 LM358DR，1000片，7天内到货……",
            disabled=st.session_state.busy,
        )
        st.button(
            "重新执行" if st.session_state.result else "开始匹配",
            key="submit",
            type="primary",
            width="stretch",
            disabled=st.session_state.busy,
            on_click=queue_request,
        )
        st.button(
            "清空需求",
            key="clear",
            width="stretch",
            disabled=st.session_state.busy,
            on_click=set_request,
            args=("",),
        )
        st.caption("每次提交会请求后端模型服务，可能产生 API 费用。切换案例不会提交。")
        with st.expander("服务连接"):
            st.caption(f"后端：{client.config.api_url}")
            st.caption(f"响应等待上限：{client.config.timeout_seconds:g} 秒；不自动重试。")
            if st.button("检查后端连接", key="health", disabled=st.session_state.busy):
                try:
                    client.health()
                    st.session_state.health_message = "后端可连接；此检查不验证模型或数据库。"
                except APIError as exc:
                    st.session_state.health_message = exc.message
            if st.session_state.health_message:
                st.caption(st.session_state.health_message)


def render_workflow(result=None):
    if result and result.node_trace:
        with st.expander("Agent 工作流 · 实际执行轨迹"):
            st.caption("以下为后端本次请求结束后返回的节点记录，并非实时进度。")
            st.caption("状态表示节点返回时的工作流状态；不足 1 毫秒按后端记录显示。")
            states = {
                "running": "继续处理",
                "success": "匹配成功",
                "no_match": "无匹配",
                "needs_clarification": "需要澄清",
                "error": "错误",
            }
            st.dataframe(
                [
                    {
                        "节点": NODES.get(t.node, "其他节点"),
                        "节点职责": NODE_PURPOSES.get(t.node, "详见技术详情"),
                        "耗时": duration_label(t.duration_ms),
                        "节点返回状态": states.get(t.status, "未分类状态"),
                    }
                    for t in result.node_trace
                ],
                hide_index=True,
                width="stretch",
            )
    else:
        st.caption("需求解析 → 参数校验 → 供应商查询 → 硬约束筛选 → 综合评分与排序 → 证据约束解释")
        st.caption("流程架构示意；未提供节点轨迹时，不显示执行进度或耗时。")


def render_requirement(result):
    fields = requirement_fields(result)
    if not fields:
        return
    st.subheader("需求解析")
    st.caption(
        "后端结构化需求 · 请核对以下条件"
        if result.requirement
        else "已识别草稿 · 尚未通过完整业务校验"
    )
    with st.container(border=True):
        columns = st.columns(4)
        for index, (label, value) in enumerate(fields.items()):
            with columns[index % 4]:
                st.caption(label)
                st.text(value)
    st.caption("预算为人民币含税货款，不含运费；未提供的预算不会被前端补全。")
    if getattr(result, "extraction_evidence", ()) or getattr(result, "applied_defaults", ()):
        with st.expander("查看原文依据与后端默认项"):
            for item in result.extraction_evidence:
                st.text(f"{field_label(item.field)}：{extraction_value(result, item.field)}")
                st.caption(
                    "原文依据：" + item.quote
                    if item.source == "text"
                    else "用户确认依据：" + item.quote
                )
            for default in result.applied_defaults:
                st.text(default_label(default))


def render_exclusions(result):
    summary = result.exclusion_summary
    with st.expander("硬约束筛选与排除明细", expanded=result.status == "no_match"):
        columns = st.columns(4)
        columns[0].metric("检索报价", summary.retrieved_offers)
        columns[1].metric("合格报价", summary.eligible_offers)
        columns[2].metric("合格供应商", summary.eligible_suppliers)
        columns[3].metric("排除报价", len(result.rejected_offers))
        if summary.reason_counts:
            st.dataframe(
                [
                    {"排除原因": code_label(k), "涉及报价数": v}
                    for k, v in summary.reason_counts.items()
                ],
                hide_index=True,
                width="stretch",
            )
        st.caption(summary.note)
        rows = [
            {
                "供应商": offer.supplier_name,
                "报价编号": offer.offer_id,
                "原因": code_label(reason.code),
                "检查字段": field_label(reason.field)
                if ":" not in reason.field
                else evidence_ref(reason.field),
                "实际记录": business_value(reason.field, reason.actual),
                "规则参照": business_value(reason.field, reason.expected),
            }
            for offer in result.rejected_offers
            for reason in offer.reasons
        ]
        if rows:
            st.dataframe(rows, hide_index=True, width="stretch")
        elif result.status == "no_match":
            st.info("后端未返回逐条排除记录，请查看本次警示中的目录或报价说明。")


def render_evidence(row):
    st.caption("所有证据均为 DEMO 数据库快照，不是实时市场报价或真实资质核验。")
    for evidence in row.evidence:
        st.markdown(f"**{evidence_ref(evidence.evidence_id)}**")
        st.caption(
            f"记录类型：{TABLES.get(evidence.table, '其他记录')} · "
            f"采集时间：{evidence.observed_at.isoformat()}"
        )
        st.dataframe(
            [
                {"业务字段": field_label(k), "记录值": business_value(k, v)}
                for k, v in evidence.fields.items()
            ],
            hide_index=True,
            width="stretch",
        )


def render_recommendations(result):
    st.subheader(f"供应商推荐 · 前 {len(result.recommendations)} 名")
    if result.explanation_mode == "template":
        st.warning("解释模式：证据模板 · 本次使用 Python 事实模板，评分与排名保留。")
        st.caption("降级原因：" + code_label(result.explanation_fallback_reason))
    elif result.explanation_mode == "llm":
        st.caption("解释模式：模型选择证据 · 分数、排名和事实均由后端确定。")
    else:
        st.caption("后端未提供推荐解释；以下展示已有评分与证据。")
    columns = st.columns(len(result.recommendations))
    explanations = {e.supplier_id: e for e in getattr(result, "explanations", ())}
    for column, row in zip(columns, result.recommendations, strict=True):
        with column, st.container(border=True):
            st.caption(f"第 {row.rank} 名 · DEMO")
            st.subheader(row.supplier_name)
            st.caption(f"{row.manufacturer} · {row.part_number}")
            st.metric("综合评分", f"{row.total_score:.2f}")
            st.text(f"含税单价  {money(row.unit_price_cents)} / 片")
            st.text(f"货款总额  {money(row.goods_total_cents)}")
            st.text(f"交期  {row.lead_time_days} 个自然日")
            st.text(f"可用库存  {row.available_quantity:,} 片")
            risks = [r for r in row.risks if r.code != "MOCK_DATA_ONLY"]
            st.caption("风险提示：" + (code_label(risks[0].code) if risks else "仅供模拟采购评估"))
            with st.expander("指标、证据与风险"):
                st.caption(f"后端完整综合评分：{row.total_score}")
                explanation = explanations.get(row.supplier_id)
                if explanation:
                    for reason in explanation.reasons:
                        st.write(localized_text(reason))
                    st.caption(
                        "解释引用："
                        + "、".join(evidence_ref(ref) for ref in explanation.evidence_ids)
                    )
                st.dataframe(dimension_rows(row), hide_index=True, width="stretch")
                for risk in row.risks:
                    st.warning(code_label(risk.code) + "：" + localized_text(risk.message))
                    st.caption(
                        "证据："
                        + (
                            "、".join(evidence_ref(ref) for ref in risk.evidence_ids)
                            or "通用数据声明"
                        )
                    )
                render_evidence(row)
    st.subheader("五维评分对比")
    st.caption("直接展示后端五项得分，固定为 0～100 分；图表不重新计算评分或排名。")
    st.altair_chart(score_chart(result), width="stretch")
    if result.metadata:
        st.caption(
            "本次评分权重 · "
            + " / ".join(f"{METRICS[k]} {v:.0%}" for k, v in result.metadata.weights.items())
        )
    render_exclusions(result)


def render_result(result):
    sources = {c.source for c in getattr(result, "llm_calls", ())}
    if "mock" in sources:
        st.warning("离线 Mock 响应 · 用于界面测试，不代表当前真实 DeepSeek 调用成功。")
    elif sources == {"deepseek"}:
        st.caption("模型调用来源：DeepSeek（依据本次后端调用记录）")
    st.caption(f"请求 ID：{result.request_id}")
    render_workflow(result)
    messages = {
        "success": "匹配完成，请核对需求、推荐依据与风险。",
        "needs_clarification": "需要补充或澄清采购条件。",
        "no_match": "当前条件下没有合格供应商，未放宽任何约束。",
    }
    if result.status == "success":
        st.success(messages[result.status])
    elif result.status in messages:
        st.warning(messages[result.status])
    else:
        code = result.error.code
        st.error(
            ERROR_HINTS.get(code, "后端未能完成本次匹配，请核对需求或检查后端服务后手动重试。")
        )
        st.caption("处理结果：" + code_label(code))
    render_requirement(result)
    for issue in getattr(result, "unsupported_constraints", ()):
        st.warning(localized_text(issue.message))
        st.text(f"原文：{issue.quote}")
    if result.status == "needs_clarification":
        for question in result.clarification_questions:
            st.info(localized_text(question))
        render_confirmations(result, queue_request)
        st.text_area(
            "补充采购条件",
            key="clarification_text",
            height=110,
            placeholder="例如：1000片，7天内到货。",
            disabled=st.session_state.busy,
        )
        st.caption("补充内容将附加到左侧原文后重新提交。冲突或不支持的条件请直接修订左侧原文。")
        st.button(
            "补充并重新匹配",
            key="clarify_submit",
            type="primary",
            on_click=queue_request,
            args=(True,),
            disabled=st.session_state.busy,
        )
    elif result.status == "success":
        render_recommendations(result)
    elif result.status == "no_match":
        render_exclusions(result)
    for warning in result.warnings:
        st.caption(localized_text(warning))
    with st.expander("本次请求与运行信息"):
        st.text(st.session_state.submitted_text)
        if result.metadata:
            st.text(
                f"数据集：{result.metadata.dataset_version} · 规则：{result.metadata.rule_version}"
            )
            st.text(f"业务时间：{result.metadata.business_time.isoformat()}")
            st.text(f"数据快照：{result.metadata.dataset_snapshot_time.isoformat()}")
        st.caption(f"后端记录模型尝试：{len(result.llm_calls)} 次")
        if result.llm_calls:
            st.dataframe(
                [
                    {
                        "阶段": "需求解析" if c.phase == "parse" else "推荐解释",
                        "来源": "DeepSeek" if c.source == "deepseek" else "离线模拟",
                        "模型": c.model_name,
                        "尝试序号": c.attempt,
                        "结果": VALUES.get(c.outcome, "未分类"),
                        "耗时": duration_label(c.duration_ms),
                        "异常说明": code_label(c.error_code) if c.error_code else "无",
                        "输入词元数": c.input_tokens,
                        "输出词元数": c.output_tokens,
                    }
                    for c in result.llm_calls
                ],
                hide_index=True,
                width="stretch",
            )
    with st.expander("技术详情（原始接口字段与代码）"):
        st.caption("用于核对原始响应；业务展示保留的精度、来源和原始代码可在此查阅。")
        st.json(result.model_dump(mode="json"), expanded=False)


def main():
    st.set_page_config(page_title="ComponentMatch Agent", page_icon="◈", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    init_state()
    try:
        client = APIClient(UIConfig.from_env())
    except APIError as exc:
        st.error(exc.message)
        st.stop()
    render_sidebar(client)
    st.markdown(
        '<div class="hero"><span class="demo-tag">DEMO · 模拟业务数据</span>'
        "<h1>ComponentMatch Agent</h1><p>电子元器件智能供应商匹配系统</p></div>",
        unsafe_allow_html=True,
    )
    st.caption("AI 智能匹配 · DeepSeek 理解需求，LangGraph 编排，Python 确定评分。")
    st.caption("DEMO：全部供应商、报价、库存、资质与历史表现均为模拟数据。")
    if st.session_state.pending_text is not None:
        # Consume the queued submit once; unrelated reruns do not resend HTTP requests.
        text = st.session_state.pop("pending_text", None)
        try:
            with st.status("正在等待后端完成采购条件校验与供应商匹配……", expanded=True):
                st.write("处理期间已禁用提交。完成后展示实际结果和节点轨迹。")
                st.session_state.result = client.match(
                    text, confirmed_fields=st.session_state.pending_confirmed_fields
                )
        except APIError as exc:
            st.session_state.ui_error = exc.message
        finally:
            st.session_state.busy = False
        st.rerun()
    if st.session_state.ui_error:
        st.error(st.session_state.ui_error)
    result = st.session_state.result
    if result:
        changed = st.session_state.request_text != st.session_state.submitted_text
        if changed:
            st.info("输入已修改，下方仍为上次提交的结果；点击重新执行后更新。")
        render_result(result)
    else:
        st.subheader("填写采购条件，开始供应商匹配")
        st.write("描述型号、数量、交期和预算，让 Agent 为你筛选供应商，并展示可核对的评分与证据。")
        render_workflow()
        with st.container(border=True):
            st.markdown("**演示操作**")
            st.write("1. 在左侧选择一个案例，或输入采购需求。")
            st.write("2. 点击开始匹配，核对解析出的条件。")
            st.write("3. 对比供应商评分，展开查看证据与风险。")
        st.info("所有库存、报价、资质、历史表现和供应商均为模拟数据，不构成采购承诺。")


if __name__ == "__main__":
    main()
