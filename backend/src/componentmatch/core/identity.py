"""Conservative catalog keys: never remove part-number suffixes or punctuation."""

_ASCII_UPPER = str.maketrans("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_MANUFACTURERS = {"TI": "TEXAS INSTRUMENTS", "TEXAS INSTRUMENTS": "TEXAS INSTRUMENTS"}


def part_key(value: str) -> str:
    return value.strip().translate(_ASCII_UPPER)


def manufacturer_key(value: str) -> str:
    key = part_key(value)
    return _MANUFACTURERS.get(key, key)
