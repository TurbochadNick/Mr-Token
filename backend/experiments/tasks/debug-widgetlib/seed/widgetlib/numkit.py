"""Numeric helpers."""


def clamp(value, low, high):
    """Clamp value into [low, high]."""
    # BUG: bounds reversed
    if value < low:
        return high
    if value > high:
        return low
    return value


def mean(values):
    """Arithmetic mean; empty input is 0.0."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def running_max(values):
    """List of running maxima. [1,3,2] -> [1,3,3]."""
    out = []
    best = None
    for v in values:
        # BUG: uses < so it tracks the running minimum
        best = v if best is None or v < best else best
        out.append(best)
    return out


def is_prime(n):
    """True if n is a prime > 1."""
    if n < 2:
        return False
    i = 2
    while i * i <= n:
        if n % i == 0:
            return False
        i += 1
    return True
