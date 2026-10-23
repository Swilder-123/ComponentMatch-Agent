from datetime import timedelta

import pytest

from componentmatch.core.clock import business_date
from componentmatch.scoring.constraints import hard_failures
from componentmatch.scoring.engine import score_candidate
from componentmatch.scoring.weights import weights_for


@pytest.mark.parametrize(
    "updates,code",
    [
        ({"available_quantity": 999}, "INSUFFICIENT_STOCK"),
        ({"available_quantity": None}, "OFFER_DATA_MISSING"),
        ({"unit_price_cents": None}, "OFFER_DATA_MISSING"),
        ({"lead_time_days": None}, "OFFER_DATA_MISSING"),
        ({"unit_price_cents": 0}, "OFFER_DATA_INVALID"),
        ({"min_order_quantity": 1001}, "MOQ_NOT_MET"),
        ({"order_multiple": 300}, "ORDER_MULTIPLE_MISMATCH"),
        ({"lead_time_days": 8}, "DELIVERY_TOO_SLOW"),
        ({"component_id": 2}, "COMPONENT_MISMATCH"),
        ({"status": "withdrawn"}, "OFFER_INACTIVE"),
        ({"currency": "USD"}, "CURRENCY_UNSUPPORTED"),
        ({"supplier_id": 999}, "SUPPLIER_MISMATCH"),
    ],
)
def test_hard_failures_never_enter_scoring(candidate, build_requirement, now, updates, code):
    modified = candidate.model_copy(update={"offer": candidate.offer.model_copy(update=updates)})
    assert code in {r.code for r in hard_failures(modified, build_requirement(), now)}
    with pytest.raises(ValueError, match="must never be scored"):
        score_candidate(modified, build_requirement(), now, weights_for("balanced"))


@pytest.mark.parametrize(
    "age,expired,code",
    [
        (timedelta(days=7, microseconds=1), False, "OFFER_STALE"),
        (timedelta(days=1), True, "OFFER_EXPIRED"),
        (timedelta(microseconds=-1), False, "FUTURE_DATA"),
    ],
)
def test_time_failures(candidate, build_requirement, now, age, expired, code):
    modified = candidate.model_copy(
        update={
            "offer": candidate.offer.model_copy(
                update={
                    "observed_at": now - age,
                    "valid_until": now - timedelta(microseconds=1)
                    if expired
                    else now + timedelta(days=1),
                }
            )
        }
    )
    assert code in {r.code for r in hard_failures(modified, build_requirement(), now)}


def test_inclusive_hard_boundaries(candidate, build_requirement, now):
    offer = candidate.offer.model_copy(
        update={
            "available_quantity": 1000,
            "min_order_quantity": 1000,
            "order_multiple": 1000,
            "observed_at": now - timedelta(days=7),
            "valid_until": now,
            "lead_time_days": 7,
        }
    )
    certs = tuple(
        c.model_copy(
            update={
                "valid_from": business_date(now),
                "expires_on": business_date(now),
                "verified_at": now,
            }
        )
        for c in candidate.certifications
    )
    modified = candidate.model_copy(update={"offer": offer, "certifications": certs})
    req = build_requirement(max_unit_price_cents=120, total_budget_cents=120000)
    assert hard_failures(modified, req, now) == ()


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"verification_status": "unverified", "verified_at": None}, "CERT_UNVERIFIED"),
        ({"verification_status": "revoked"}, "CERT_REVOKED"),
        ({"verified_at": None}, "CERT_VERIFICATION_MISSING"),
        ({"expires_on": "expired"}, "CERT_EXPIRED"),
        ({"valid_from": "future"}, "CERT_NOT_YET_VALID"),
        ({"verified_at": "future"}, "CERT_VERIFICATION_FUTURE"),
    ],
)
def test_certificate_states_are_distinct(candidate, build_requirement, now, changes, code):
    values = dict(changes)
    if values.get("expires_on") == "expired":
        values["expires_on"] = business_date(now) - timedelta(days=1)
    if values.get("valid_from") == "future":
        values["valid_from"] = business_date(now) + timedelta(days=1)
    if values.get("verified_at") == "future":
        values["verified_at"] = now + timedelta(seconds=1)
    cert = candidate.certifications[0].model_copy(update=values)
    modified = candidate.model_copy(update={"certifications": (cert,)})
    assert code in {r.code for r in hard_failures(modified, build_requirement(), now)}


def test_missing_certificate_differs_from_unverified(candidate, build_requirement, now):
    modified = candidate.model_copy(update={"certifications": ()})
    assert {r.code for r in hard_failures(modified, build_requirement(), now)} == {"CERT_MISSING"}


def test_one_valid_certificate_satisfies_code_despite_another_expired(
    candidate, build_requirement, now
):
    expired = candidate.certifications[0].model_copy(
        update={"id": 99, "expires_on": business_date(now) - timedelta(days=1)}
    )
    modified = candidate.model_copy(update={"certifications": (*candidate.certifications, expired)})
    assert hard_failures(modified, build_requirement(), now) == ()
