"""Pure deterministic scoring; no database, model, or wall-clock calls."""

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext

from componentmatch_contracts.requirement import ProcurementRequirement
from componentmatch_contracts.result import DimensionScore, Evidence, Recommendation, Risk

from componentmatch.core.clock import business_date, month_offset
from componentmatch.schemas.snapshot import Candidate, PerformanceData, Record
from componentmatch.scoring.constraints import hard_failures, valid_certifications
from componentmatch.scoring.weights import METRICS, validate_weights

SIX_PLACES = Decimal("0.000001")


def quantize(value: Decimal) -> Decimal:
    return value.quantize(SIX_PLACES, rounding=ROUND_HALF_UP)


def normalized(value: Decimal) -> Decimal:
    return quantize(Decimal(100) * min(Decimal(1), max(Decimal(0), value)))


def evidence_for(record: Record, table: str, observed_at: datetime) -> Evidence:
    values = {}
    for field, value in record.model_dump().items():
        if field in {"id", "is_mock", "source_label", "updated_at"}:
            continue
        values[field] = value.isoformat() if isinstance(value, (date, datetime)) else value
    return Evidence(
        evidence_id=f"{table}:{record.id}",
        table=table,
        record_id=record.id,
        source_label=record.source_label,
        observed_at=observed_at,
        fields=values,
    )


def valid_history(record: PerformanceData) -> bool:
    counts = (
        record.quality_evaluated_orders,
        record.inspected_units,
        record.accepted_units,
        record.orders_due,
        record.orders_on_time,
        record.response_minutes_total,
        record.response_samples,
    )
    return (
        all(n >= 0 for n in counts)
        and record.period_start.day == 1
        and record.period_end == month_offset(record.period_start, 1)
        and record.accepted_units <= record.inspected_units
        and record.orders_on_time <= record.orders_due
        and (record.inspected_units == 0 or record.quality_evaluated_orders > 0)
        and (record.response_samples > 0 or record.response_minutes_total == 0)
    )


def score_candidate(candidate, req, now, weights) -> Recommendation:
    """Require hard eligibility even when called outside the matching service."""
    if hard_failures(candidate, req, now):
        raise ValueError("Hard-ineligible offers must never be scored")
    with localcontext() as context:
        context.prec = 40
        return _score(candidate, req, now, validate_weights(weights))


def _score(
    candidate: Candidate, req: ProcurementRequirement, now: datetime, weights
) -> Recommendation:
    offer, supplier, component = candidate.offer, candidate.supplier, candidate.component
    p, d = Decimal(offer.unit_price_cents), Decimal(offer.lead_time_days)
    evidence = [
        evidence_for(offer, "offers", offer.observed_at),
        evidence_for(
            component, "components", component.reference_observed_at or component.updated_at
        ),
        evidence_for(supplier, "suppliers", supplier.updated_at),
    ]
    evidence.extend(
        evidence_for(c, "supplier_certifications", c.verified_at or c.updated_at)
        for c in candidate.certifications
    )
    risks: dict[str, Risk] = {}

    def risk(code, message, refs=()):
        risks[code] = Risk(code=code, message=message, evidence_ids=tuple(refs))

    offer_ref, component_ref = f"offers:{offer.id}", f"components:{component.id}"
    risk("MOCK_DATA_ONLY", "DEMO：所有报价、库存、资质和历史表现均为虚构")
    reference_ok = (
        component.reference_unit_price_cents is not None
        and component.reference_unit_price_cents > 0
        and component.reference_observed_at is not None
        and timedelta(0) <= now - component.reference_observed_at <= timedelta(days=30)
    )
    if reference_ok:
        r = Decimal(component.reference_unit_price_cents)
        price_score = normalized((Decimal("1.5") * r - p) / r)
        if p < Decimal("0.5") * r:
            risk(
                "LOW_PRICE_REVIEW",
                "模拟报价低于参考价的一半，需人工复核",
                (offer_ref, component_ref),
            )
    else:
        price_score = Decimal(0)
        risk(
            "PRICE_REFERENCE_UNAVAILABLE",
            "参考价缺失、无效或过期，价格分为0且不重分配权重",
            (component_ref,),
        )
    day = business_date(now)
    end = day.replace(day=1)
    start = month_offset(end, -6)
    usable = []
    seen = set()
    for row in sorted(candidate.history, key=lambda h: h.id):
        key = (row.period_start, row.period_end)
        if (
            not valid_history(row)
            or key in seen
            or row.supplier_id != supplier.id
            or row.component_id != component.id
        ):
            risk("HISTORY_ROW_INVALID", "无效或重复月度历史已剔除")
            continue
        seen.add(key)
        if row.period_end <= end:
            usable.append(row)
    window = [row for row in usable if start <= row.period_start and row.period_end <= end]
    evidence.extend(evidence_for(row, "performance_records", row.updated_at) for row in window)
    history_refs = tuple(f"performance_records:{row.id}" for row in window)
    stale = bool(usable) and (day - max(row.period_end for row in usable)).days > 62
    if not window or stale:
        code = "HISTORY_STALE" if stale else "HISTORY_MISSING"
        risk(code, "历史数据过期或缺失，质量/准时交付/响应分均为0", history_refs)
        history = []
    else:
        history = window
    if len(window) < 6:
        risk("HISTORY_PARTIAL_WINDOW", "最近六个完整自然月记录不齐全", history_refs)
    sums = {
        field: sum(getattr(row, field) for row in history)
        for field in (
            "quality_evaluated_orders",
            "inspected_units",
            "accepted_units",
            "orders_due",
            "orders_on_time",
            "response_minutes_total",
            "response_samples",
        )
    }
    quality_raw = (
        Decimal(sums["accepted_units"]) / sums["inspected_units"]
        if sums["inspected_units"]
        else None
    )
    on_time_raw = (
        Decimal(sums["orders_on_time"]) / sums["orders_due"] if sums["orders_due"] else None
    )
    response_raw = (
        Decimal(sums["response_minutes_total"]) / sums["response_samples"] / 60
        if sums["response_samples"]
        else None
    )

    def history_score(raw, lower, span, sample_small, prefix):
        if raw is None:
            risk(f"{prefix}_HISTORY_MISSING", "该维度无有效历史分母，分项为0", history_refs)
            return Decimal(0)
        value = normalized((raw - lower) / span)
        if sample_small:
            risk(f"{prefix}_SAMPLE_SMALL", "历史样本不足，分项最高50分", history_refs)
            value = min(value, Decimal(50))
        return value

    quality = history_score(
        quality_raw,
        Decimal("0.95"),
        Decimal("0.05"),
        sums["inspected_units"] < 500 or sums["quality_evaluated_orders"] < 5,
        "QUALITY",
    )
    on_time = history_score(
        on_time_raw, Decimal("0.80"), Decimal("0.20"), sums["orders_due"] < 5, "DELIVERY"
    )
    if response_raw is None:
        response = Decimal(0)
        risk("RESPONSE_HISTORY_MISSING", "无响应样本，响应分为0", history_refs)
    else:
        response = normalized((Decimal(48) - response_raw) / 47)
        if sums["response_samples"] < 5:
            response = min(response, Decimal(50))
            risk("RESPONSE_SAMPLE_SMALL", "响应样本不足，分项最高50分", history_refs)
    if Decimal(offer.available_quantity) / req.quantity < Decimal("1.2"):
        risk("STOCK_TIGHT", "模拟库存余量小于需求的20%", (offer_ref,))
    if req.max_delivery_days is not None and offer.lead_time_days == req.max_delivery_days:
        risk("NO_DELIVERY_BUFFER", "交期恰好达到硬上限，没有余量", (offer_ref,))
    for code in req.required_certifications:
        # Use one deterministic valid certificate as the eligibility evidence.
        cert = min(valid_certifications(candidate, code, now), key=lambda c: c.id)
        if (cert.expires_on - day).days <= 30:
            risk(
                "CERT_EXPIRING_SOON",
                "用于满足硬条件的模拟证书30日内到期",
                (f"supplier_certifications:{cert.id}",),
            )

    scores = {
        "price": price_score,
        "delivery": normalized((30 - d) / 30),
        "quality": quality,
        "on_time": on_time,
        "response": response,
    }
    raw = {
        "price": p,
        "delivery": d,
        "quality": quality_raw,
        "on_time": on_time_raw,
        "response": response_raw,
    }
    units = {
        "price": "CNY cents/pcs",
        "delivery": "calendar days",
        "quality": "ratio",
        "on_time": "ratio",
        "response": "hours",
    }
    dimensions = tuple(
        DimensionScore(
            metric=metric,
            raw_value=raw[metric],
            raw_unit=units[metric],
            score=quantize(scores[metric]),
            weight=weights[metric],
            contribution=quantize(scores[metric] * weights[metric]),
            evidence_ids=(
                (offer_ref, component_ref)
                if metric == "price"
                else (offer_ref,)
                if metric == "delivery"
                else history_refs
            ),
        )
        for metric in METRICS
    )
    return Recommendation(
        rank=1,
        supplier_id=supplier.id,
        supplier_name=supplier.name,
        offer_id=offer.id,
        component_id=component.id,
        manufacturer=component.manufacturer,
        part_number=component.part_number,
        quantity=req.quantity,
        available_quantity=offer.available_quantity,
        unit_price_cents=offer.unit_price_cents,
        goods_total_cents=offer.unit_price_cents * req.quantity,
        lead_time_days=offer.lead_time_days,
        total_score=sum(d.contribution for d in dimensions),
        dimensions=dimensions,
        evidence=tuple(evidence),
        risks=tuple(risks.values()),
    )


def ranking_key(result: Recommendation):
    quality = next(d.score for d in result.dimensions if d.metric == "quality")
    return (
        -result.total_score,
        -quality,
        result.lead_time_days,
        result.goods_total_cents,
        result.supplier_id,
        result.offer_id,
    )
