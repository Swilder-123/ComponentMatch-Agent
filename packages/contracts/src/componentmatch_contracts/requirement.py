"""Structured-only input contract; no natural-language assumptions in phase 2."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

MoneyLimit = Annotated[StrictInt, Field(ge=0, le=9_000_000_000_000_000_000)]
Profile = Literal["balanced", "cost", "delivery", "quality"]


class ProcurementRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    part_number: str = Field(min_length=1, max_length=128, description="完整制造商料号，保留后缀")
    manufacturer: str | None = Field(default=None, min_length=1, max_length=128)
    quantity: Annotated[StrictInt, Field(gt=0, le=1_000_000_000, description="精确采购数量，pcs")]
    delivery_mode: Literal["unspecified", "within_days", "unconstrained"] = "unspecified"
    max_delivery_days: Annotated[StrictInt, Field(ge=0, le=3650)] | None = Field(
        default=None, description="到货自然日上限；0 表示当天"
    )
    max_unit_price_cents: MoneyLimit | None = Field(
        default=None, description="含税单价上限，人民币分/pcs，不含运费"
    )
    total_budget_cents: MoneyLimit | None = Field(
        default=None, description="本需求含税货款总上限，人民币分，不含运费"
    )
    currency: Literal["CNY"] = "CNY"
    required_certifications: tuple[Literal["ISO9001"], ...] = ()
    preference_profile: Profile = "balanced"

    @field_validator("part_number", "manufacturer")
    @classmethod
    def nonblank(cls, value):
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("Must not be blank")
        return value

    @model_validator(mode="after")
    def check_conditions(self) -> Self:
        if (self.delivery_mode == "within_days") != (self.max_delivery_days is not None):
            raise ValueError("Only within_days requires max_delivery_days")
        if len(set(self.required_certifications)) != len(self.required_certifications):
            raise ValueError("Duplicate required certification")
        return self


class MatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_mode: Literal["structured"] = "structured"
    requirement: ProcurementRequirement
