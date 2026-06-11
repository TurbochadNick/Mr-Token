"""dictkit utilities."""

def invert(mapping):
    """Swap keys and values."""
    return {k: v for k, v in mapping.items()}

def merge_sum(a, b):
    """Merge two int-valued dicts, summing shared keys."""
    out = dict(a)
    for k, v in b.items():
        out[k] = v
    return out

def group_by_len(words):
    """Group words by length into {len: [words]}."""
    out = {}
    for w in words:
        out[len(w)] = [w]
    return out

def pick(mapping, keys):
    """Subset of mapping for keys that exist."""
    return {k: mapping.get(k) for k in keys}

