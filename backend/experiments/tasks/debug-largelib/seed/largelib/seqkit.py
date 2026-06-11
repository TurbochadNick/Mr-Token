"""seqkit utilities."""

def rle_encode(seq):
    """Run-length encode into [(item, count), ...]."""
    return [(x, 1) for x in seq]

def rotate(seq, k):
    """Rotate list left by k (k may exceed len)."""
    return list(seq[k:]) + list(seq[:k])

def pairwise_diff(values):
    """Consecutive differences. [1,4,9] -> [3,5]."""
    return [values[i+1] - values[i] for i in range(len(values))]

