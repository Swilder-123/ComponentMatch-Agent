"""Exact numeric and money parsing, independent of model extraction."""

import re
from decimal import Decimal

_SIGN = r"(?:[+\-−－﹣–—＋±负正]\s*)*"

_TOKEN = r"(?:\d+(?:,\d{3})*(?:\.\d+)?(?:[kK千万])?|[零〇一二两三四五六七八九十百千万]+)"

_NUMBER = re.compile(rf"({_SIGN})({_TOKEN})")

_DIGITS = dict(zip("零〇一二两三四五六七八九", (0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9), strict=True))


def number_value(text):
    found = _NUMBER.search(text)
    if not found:
        return None
    sign = number_sign(found[1])
    token = found[2]
    if token[0].isdigit():
        numeric = re.match(r"\d+(?:,\d{3})*(?:\.\d+)?", token).group()
        value = Decimal(numeric.replace(",", ""))
        tail = (token[len(numeric) :] + text[found.end() :]).lstrip()
        if tail.startswith(("k", "K", "千")):
            value *= 1000
        elif tail.startswith("万"):
            value *= 10000
        return sign * value
    section = total = digit = 0
    for char in token:
        if char in _DIGITS:
            digit = _DIGITS[char]
        elif char == "万":
            total += (section + digit) * 10000
            section = digit = 0
        else:
            section += (digit or 1) * {"十": 10, "百": 100, "千": 1000}[char]
            digit = 0
    return sign * Decimal(total + section + digit)


def number_sign(text):
    signs = re.sub(r"\s", "", text)
    if len(signs) > 1 or signs == "±":
        raise ValueError("数值有冲突或重复符号，请确认")
    return -1 if signs in {"-", "−", "－", "﹣", "–", "—", "负"} else 1


def money_cents(mention):
    # Parse the quoted numeric token and unit again; never trust a pre-converted model amount.
    pattern = rf"({_SIGN})(\d+(?:,\d{{3}})*(?:\.\d+)?)\s*(万)?\s*(元|分)"
    matches = list(re.finditer(pattern, mention.quote))
    if len(matches) != 1:
        raise ValueError("金额必须有唯一数字和明确人民币元/分单位")
    match = matches[0]
    if number_sign(match[1]) < 0:
        raise ValueError("预算不能为负数，请确认原文符号")
    if Decimal(match[2].replace(",", "")) != Decimal(mention.amount):
        raise ValueError("模型金额与原文不一致，请确认金额")
    unit = "CNY_yuan" if match[4] == "元" else "CNY_cent"
    if unit != mention.unit:
        raise ValueError("模型单位与原文不一致，请确认元或分")
    value = (
        Decimal(mention.amount) * (10000 if match[3] else 1) * (100 if unit == "CNY_yuan" else 1)
    )
    if value != value.to_integral_value():
        raise ValueError("金额精度超过人民币分，请确认")
    return int(value)
