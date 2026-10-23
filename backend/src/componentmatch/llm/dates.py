"""Explicit delivery date parsing with Shanghai business-date boundaries."""

import re
from datetime import date, datetime, timedelta

from componentmatch.core.clock import business_date, utc

_DATE = re.compile(
    r"(?<![A-Za-z0-9])(?P<day>\d{4}(?:-\d{1,2}-\d{1,2}|/\d{1,2}/\d{1,2}|年\d{1,2}月\d{1,2}日))"
    r"(?P<time>[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?)?"
    r"(?!\d)"
)


def delivery_dates(text, now):
    """Known date syntax only: date-only uses Shanghai; timed cutoffs require an offset."""
    limits, quotes = [], []
    if _DATE.search(text) and re.search(
        r"(?<![A-Za-z])(?:UTC|GMT|PST|EST)(?![A-Za-z])|纽约|东京|伦敦|America/|Europe/",
        text,
        re.IGNORECASE,
    ):
        raise ValueError("请将时区写成完整ISO到货时刻的Z或±HH:MM，不猜测时区名称")
    for match in _DATE.finditer(text):
        suffix = text[match.end() :].lstrip()
        prefix = re.split(r"[，,。；;\n]", text[: match.start()])[-1]
        if suffix.startswith(("之后", "以后", "后")) or re.search(
            r"不得早于|不早于|最早|(?<!不)(?<!不得)晚于", prefix
        ):
            raise ValueError("到货日期下限不能当成截止上限，请确认")
        day_text = re.sub(r"[年/月]", "-", match["day"]).removesuffix("日")
        target = date(*map(int, day_text.split("-")))
        if match["time"]:
            offset = re.search(r"[+-](\d{2}):(\d{2})$", match["time"])
            if offset and (int(offset[1]) >= 24 or int(offset[2]) >= 60):
                raise ValueError("到货时刻的时区偏移无效")
            stamp = datetime.fromisoformat(target.isoformat() + "T" + match["time"][1:])
            if stamp.tzinfo is None:
                raise ValueError("具体到货时刻必须提供Z或±HH:MM时区")
            seconds = (utc(stamp) - utc(now)).total_seconds()
            if seconds < 0:
                raise ValueError("到货时刻已过去，请确认")
            # Whole-day lead times cannot promise a fractional day; round conservatively down.
            days = int(seconds // 86400)
            if suffix.startswith(("之前", "以前", "前")) and seconds % 86400 == 0:
                days -= 1
        else:
            if suffix.startswith("T"):
                raise ValueError("到货时刻格式无效，请提供完整ISO格式和时区")
            if re.match(r"[+-]\d{2}:\d{2}", suffix):
                raise ValueError("带时区偏移的截止日期必须同时提供具体时刻")
            if re.match(r"上午|下午|中午|晚上|凌晨|\d{1,2}[点时]", suffix):
                raise ValueError("具体时刻请使用带时区的ISO格式")
            exclusive = suffix.startswith(("之前", "以前", "前"))
            if exclusive:
                target -= timedelta(days=1)
            days = (target - business_date(now)).days
        if days < 0:
            raise ValueError("到货日期已过去，请确认")
        limits.append(days)
        quotes.append(match.group())
    if not limits:
        if re.search(r"\d{1,2}月\d{1,2}日|\d{1,2}[-/]\d{1,2}|明天|后天", text):
            raise ValueError("请提供含年份的完整到货日期")
        return None, ()
    if len(set(limits)) != 1:
        raise ValueError("存在多个不同到货日期，请确认唯一截止日期")
    return limits[0], tuple(quotes)
