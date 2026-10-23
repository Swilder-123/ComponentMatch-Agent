"""Conservative lexical checks for polarity and comparison direction.

These guards supplement model extraction. They deliberately do not claim to parse
arbitrary Chinese sentences or infer an unsupported delivery lower bound.
"""

import re


def is_optional(text: str, start: int, end: int) -> bool:
    """Recognize a local waiver; a negation in an earlier clause does not carry over."""
    prefix = re.split(r"[，,。；;\n]|但是|但|不过", text[:start])[-1]
    suffix = text[end:]
    before = re.search(
        r"(?:不强制要求|不强制|不要求|不需要|无需|无须|不必)\s*"
        r"(?:供应商)?(?:具备|提供|满足|具有|通过|符合|取得|拥有|要求|有)?\s*$",
        prefix,
    )
    after = re.match(r"\s*(?:认证|证书|资质)?\s*(?:不作要求|无要求|不要求|不限|可选)", suffix)
    return bool(before or after)


def quote_is_optional(text: str, quote: str) -> bool:
    matches = list(re.finditer(re.escape(quote), text))
    if not matches:
        return False
    terms = list(
        re.finditer(
            r"原厂授权|原厂认证|授权代理|授权经销|车规|RoHS|REACH|ISO\s*\d+|AEC[- ]?Q\d+",
            quote,
            re.IGNORECASE,
        )
    )
    if len(terms) == 1:
        term = terms[0]
        return all(
            is_optional(text, m.start() + term.start(), m.start() + term.end()) for m in matches
        )
    return all(is_optional(text, m.start(), m.end()) for m in matches)


def duration_direction(text: str, start: int, end: int) -> str:
    prefix = re.split(r"[，,。；;\n]", text[:start])[-1]
    suffix = text[end:].lstrip()
    if re.search(
        r"至少|不早于|不得早于|最早|(?<!不)(?<!不得)晚于|(?<!不)(?<!不得)超过|不少于|(?<!不)大于|[≥>]",
        prefix,
    ) or re.match(r"之后|以后|后|以上|以外|外|起", suffix):
        return "lower"
    if re.match(r"之前|以前|前", suffix):
        return "strict_upper"
    if re.match(r"以内|之内|内", suffix) or re.search(
        r"不超过|不得超过|最多|不晚于|不得晚于|不大于|[≤]", prefix
    ):
        return "upper"
    # Bare lead-time statements retain the established whole-day upper-bound meaning.
    return "upper" if re.search(r"交期|到货|交货|送达|交付", prefix + suffix) else "unknown"
