"""Text helpers. Some functions have bugs the test suite catches."""


def slugify(text):
    """Lowercase, non-alphanumeric runs to single hyphens, stripped."""
    import re
    s = re.sub(r"[^a-z0-9]+", "-", text.lower())
    # BUG: does not strip leading/trailing hyphens
    return s


def truncate(text, limit):
    """Truncate to `limit` chars including a trailing ellipsis when shortened."""
    if len(text) <= limit:
        return text
    # BUG: ignores the room needed for the ellipsis
    return text[:limit] + "..."


def word_count(text):
    """Count whitespace-separated words; runs of spaces do not add words."""
    # BUG: split(" ") yields empties on runs of spaces
    return len(text.split(" "))


def initials(name):
    """First letter of each word, uppercased, joined. 'ada lovelace' -> 'AL'."""
    return "".join(part[0].upper() for part in name.split())
