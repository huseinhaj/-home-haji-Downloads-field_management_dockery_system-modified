"""
Custom Django template filters for the curriculum (TLM) app.
"""
import math

from django import template

register = template.Library()


@register.filter
def compact_number(value):
    """
    Format large numbers compactly for stat cards:
        999   -> 999
        1000  -> 1K
        1100  -> 1.1K
        1500  -> 1.5K
        10500 -> 10.5K
        1000000 -> 1M
        1500000 -> 1.5M

    Rounding is half-up (math.floor(v * 10 + 0.5) / 10) to stay consistent
    with the JS compactNumber() used by the landing page counters.
    """
    try:
        n = float(value)
    except (TypeError, ValueError):
        return value

    if abs(n) >= 1_000_000:
        v = n / 1_000_000
        suffix = 'M'
    elif abs(n) >= 1000:
        v = n / 1000
        suffix = 'K'
    else:
        return str(int(n)) if n == int(n) else f"{n:g}"

    # One decimal, half-up rounding, trailing ".0" trimmed (1.0 -> 1)
    rounded = math.floor(v * 10 + 0.5) / 10
    text = str(int(rounded)) if rounded == int(rounded) else f"{rounded:.1f}"
    return f"{text}{suffix}"
