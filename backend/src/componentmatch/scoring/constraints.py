"""Hard rules precede scoring. Every failure is retained with exact field evidence."""

from datetime import datetime, timedelta

from componentmatch.core.clock import business_date
from componentmatch.core.identity import manufacturer_key, part_key
from componentmatch.schemas.snapshot import Candidate, CertificationData
from componentmatch_contracts.requirement import ProcurementRequirement
from componentmatch_contracts.result import ExclusionReason


def valid_certifications(
    candidate: Candidate, code: str, now: datetime
) -> tuple[CertificationData, ...]:
    day = business_date(now)
    return tuple(
        c
        for c in candidate.certifications
        if c.certification_code == code
        and c.verification_status == "verified"
        and c.verified_at is not None
        and c.verified_at <= now
        and c.valid_from <= day <= c.expires_on
    )


def hard_failures(
    candidate: Candidate, req: ProcurementRequirement, now: datetime
) -> tuple[ExclusionReason, ...]:
    offer, supplier, component = candidate.offer, candidate.supplier, candidate.component
    failures: list[ExclusionReason] = []

    def fail(code, message, field, actual=None, expected=None):
        failures.append(
            ExclusionReason(
                code=code, message=message, field=field, actual=actual, expected=expected
            )
        )

    if offer.currency != req.currency or component.reference_currency != req.currency:
        fail(
            "CURRENCY_UNSUPPORTED",
            "币种不支持，禁止隐式换算",
            "currency",
            offer.currency,
            req.currency,
        )
    if offer.supplier_id != supplier.id:
        fail(
            "SUPPLIER_MISMATCH",
            "报价与供应商身份不一致",
            "supplier_id",
            offer.supplier_id,
            supplier.id,
        )
    if (
        offer.component_id != component.id
        or part_key(req.part_number) != component.part_number_key
        or part_key(component.part_number) != component.part_number_key
        or manufacturer_key(component.manufacturer) != component.manufacturer_key
        or (
            req.manufacturer is not None
            and manufacturer_key(req.manufacturer) != component.manufacturer_key
        )
    ):
        fail(
            "COMPONENT_MISMATCH",
            "完整型号或制造商不匹配，禁止替代",
            "component_id",
            offer.component_id,
            component.id,
        )
    if supplier.status != "active":
        fail("SUPPLIER_INACTIVE", "供应商已停用", "supplier.status", supplier.status, "active")
    if offer.status != "active":
        fail("OFFER_INACTIVE", "报价已撤回", "offer.status", offer.status, "active")
    for field in ("unit_price_cents", "available_quantity", "lead_time_days"):
        if getattr(offer, field) is None:
            fail("OFFER_DATA_MISSING", "供货必要数据缺失", field)
    for field, lower in (
        ("unit_price_cents", 1),
        ("available_quantity", 0),
        ("lead_time_days", 0),
        ("min_order_quantity", 1),
        ("order_multiple", 1),
    ):
        value = getattr(offer, field)
        if value is not None and value < lower:
            fail("OFFER_DATA_INVALID", "供货数据无效", field, value, f">={lower}")
    if offer.observed_at > now:
        fail(
            "FUTURE_DATA",
            "供货快照时间在业务时间之后",
            "observed_at",
            offer.observed_at.isoformat(),
        )
    if offer.valid_until < offer.observed_at:
        fail("OFFER_DATA_INVALID", "报价时间区间无效", "valid_until")
    if now > offer.valid_until:
        fail("OFFER_EXPIRED", "报价已过有效期", "valid_until", offer.valid_until.isoformat())
    if now - offer.observed_at > timedelta(days=7):
        fail("OFFER_STALE", "供货快照超过7日时效", "observed_at", offer.observed_at.isoformat())
    if offer.available_quantity is not None and offer.available_quantity < req.quantity:
        fail(
            "INSUFFICIENT_STOCK",
            "单条报价库存不足，不合并或拆单",
            "available_quantity",
            offer.available_quantity,
            req.quantity,
        )
    if req.quantity < offer.min_order_quantity:
        fail(
            "MOQ_NOT_MET",
            "需求数量低于起订量",
            "min_order_quantity",
            offer.min_order_quantity,
            req.quantity,
        )
    if offer.order_multiple > 0 and req.quantity % offer.order_multiple:
        fail(
            "ORDER_MULTIPLE_MISMATCH",
            "需求数量不是包装下单倍数",
            "order_multiple",
            offer.order_multiple,
            req.quantity,
        )
    if (
        req.max_delivery_days is not None
        and offer.lead_time_days is not None
        and offer.lead_time_days > req.max_delivery_days
    ):
        fail(
            "DELIVERY_TOO_SLOW",
            "交期超过硬性上限",
            "lead_time_days",
            offer.lead_time_days,
            req.max_delivery_days,
        )
    if offer.unit_price_cents is not None:
        if (
            req.max_unit_price_cents is not None
            and offer.unit_price_cents > req.max_unit_price_cents
        ):
            fail(
                "UNIT_PRICE_OVER_LIMIT",
                "含税单价超过上限（分/pcs，不含运费）",
                "unit_price_cents",
                offer.unit_price_cents,
                req.max_unit_price_cents,
            )
        total = offer.unit_price_cents * req.quantity
        if req.total_budget_cents is not None and total > req.total_budget_cents:
            fail(
                "TOTAL_BUDGET_EXCEEDED",
                "含税货款合计超过预算（分，不含运费）",
                "goods_total_cents",
                total,
                req.total_budget_cents,
            )
    day = business_date(now)
    for code in req.required_certifications:
        if valid_certifications(candidate, code, now):
            continue
        certs = [c for c in candidate.certifications if c.certification_code == code]
        if not certs:
            fail("CERT_MISSING", "所需证书缺失", code, None, "valid verified certificate")
        for cert in certs:
            ref = f"certification:{cert.id}"
            if cert.verification_status != "verified":
                reason = (
                    "CERT_REVOKED" if cert.verification_status == "revoked" else "CERT_UNVERIFIED"
                )
                fail(reason, "证书已撤销或尚未核验", ref, cert.verification_status, "verified")
            if cert.verified_at is None:
                fail("CERT_VERIFICATION_MISSING", "证书缺少核验时间", ref)
            elif cert.verified_at > now:
                fail("CERT_VERIFICATION_FUTURE", "证书核验时间在未来", ref)
            if cert.expires_on < day:
                fail("CERT_EXPIRED", "证书已到期", ref, cert.expires_on.isoformat())
            if cert.valid_from > day:
                fail("CERT_NOT_YET_VALID", "证书尚未生效", ref, cert.valid_from.isoformat())
    return tuple(failures)
