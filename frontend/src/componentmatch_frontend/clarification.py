"""Explicit field confirmation controls; values are validated before HTTP submission."""

import streamlit as st

from componentmatch_contracts.agent import AgentRequest
from componentmatch_frontend.presentation import VALUES, field_label


def reset_confirmation_widgets():
    for key in list(st.session_state):
        if key == "confirmation_fields" or key.startswith("confirm_value_"):
            del st.session_state[key]


def collect_confirmations():
    fields = st.session_state.get("confirmation_fields", [])
    if not fields:
        raise ValueError("请先选择需要确认的字段。")
    output = {}
    numeric = {"quantity", "max_unit_price_cents", "total_budget_cents"}
    for field in fields:
        if field in {"delivery_mode", "max_delivery_days"}:
            mode = st.session_state.get("confirm_value_delivery_mode")
            if not mode:
                raise ValueError("请选择交期要求。")
            output["delivery_mode"] = mode
            output["max_delivery_days"] = (
                st.session_state.get("confirm_value_max_delivery_days")
                if mode == "within_days"
                else None
            )
            if mode == "within_days" and output["max_delivery_days"] is None:
                raise ValueError("请填写最长交期。")
        else:
            value = st.session_state.get("confirm_value_" + field)
            if value is None or (isinstance(value, str) and not value.strip()):
                raise ValueError("请填写所选字段：" + field_label(field))
            if field in numeric:
                value = int(value)
            if field == "required_certifications":
                value = ["ISO9001"] if value == "required" else []
            output[field] = value
    # The request contract checks bounds and types before any HTTP request is sent.
    AgentRequest(text=st.session_state.request_text, confirmed_fields=output)
    return output


def render_confirmations(result, on_submit):
    if not result.clarification_fields:
        return
    with st.expander("逐项确认有歧义或缺失的条件"):
        st.caption(
            "仅提交你明确选中并填写的字段。确认值覆盖对应解析值，无法验证的硬条件仍会阻止匹配。"
        )
        selected = st.multiselect(
            "本次明确确认的字段",
            options=result.clarification_fields,
            format_func=field_label,
            key="confirmation_fields",
            disabled=st.session_state.busy,
        )
        for field in selected:
            label = field_label(field)
            key = "confirm_value_" + field
            if field in {"delivery_mode", "max_delivery_days"}:
                continue
            if field in {"quantity", "max_unit_price_cents", "total_budget_cents"}:
                unit = "（片）" if field == "quantity" else "（人民币分，1元=100分）"
                st.number_input(
                    label + unit,
                    min_value=1 if field == "quantity" else 0,
                    value=None,
                    step=1,
                    key=key,
                )
            elif field == "required_certifications":
                st.selectbox(
                    label,
                    options=["required", "optional"],
                    index=None,
                    format_func=lambda v: (
                        "必须具备ISO9001" if v == "required" else "无强制证书要求"
                    ),
                    key=key,
                )
            elif field == "preference_profile":
                st.selectbox(
                    label,
                    options=["balanced", "cost", "delivery", "quality"],
                    index=None,
                    format_func=lambda v: VALUES[v],
                    key=key,
                )
            elif field == "currency":
                st.selectbox(label, options=["CNY"], index=None, key=key)
            else:
                st.text_input(label, key=key)
        if {"delivery_mode", "max_delivery_days"} & set(selected):
            mode = st.selectbox(
                "交期要求",
                options=["within_days", "unconstrained"],
                index=None,
                format_func=lambda v: VALUES[v],
                key="confirm_value_delivery_mode",
            )
            if mode == "within_days":
                st.number_input(
                    "最长交期（自然日）",
                    min_value=0,
                    value=None,
                    step=1,
                    key="confirm_value_max_delivery_days",
                )
        st.button(
            "确认所选条件并重新匹配",
            key="confirm_submit",
            on_click=on_submit,
            args=(False, True),
            disabled=st.session_state.busy,
        )
