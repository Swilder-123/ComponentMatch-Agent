"""Expose editable fields for the existing clarification messages."""

from componentmatch_contracts.agent import FieldName


def clarification_fields(questions):
    text = " ".join(questions)
    fields = {name for name in FieldName.__args__ if name in text}
    for keyword, names in (
        ("料号", ("part_number",)),
        ("制造商", ("manufacturer",)),
        ("厂家", ("manufacturer",)),
        ("数量", ("quantity",)),
        ("交期", ("delivery_mode", "max_delivery_days")),
        ("到货", ("delivery_mode", "max_delivery_days")),
        ("资质", ("required_certifications",)),
        ("ISO9001", ("required_certifications",)),
    ):
        if keyword in text:
            fields.update(names)
    return tuple(name for name in FieldName.__args__ if name in fields)
