"""List/sequence helpers."""


def chunk(seq, size):
    """Split seq into lists of length `size` (last may be shorter)."""
    # BUG: off-by-one in the step drops/overlaps elements
    return [seq[i:i + size] for i in range(0, len(seq), size - 1)]


def dedupe(seq):
    """Remove duplicates, preserving first-seen order."""
    seen = set()
    out = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def flatten(nested):
    """Flatten one level of nesting. [[1,2],[3]] -> [1,2,3]."""
    out = []
    for group in nested:
        # BUG: appends the group instead of extending
        out.append(group)
    return out


def take(seq, n):
    """First n items as a list."""
    return list(seq[:n])
