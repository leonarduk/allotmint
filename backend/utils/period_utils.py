import re


def parse_period_to_days(period: str) -> int:
    """
    Convert a time period string like '1d', '2w', '3mo', '1y' to number of days.
    """
    match = re.fullmatch(r"(?i)(\d+)(d|w|mo|y)", period.strip())
    if not match:
        raise ValueError(f"Unrecognized period format: '{period}'")

    value, unit = int(match[1]), match[2].lower()
    if unit == "d":
        return value
    elif unit == "w":
        return value * 7
    elif unit == "mo":
        return value * 30
    elif unit == "y":
        return value * 365
    else:  # pragma: no cover
        raise ValueError(f"Unsupported time unit: '{unit}'")
