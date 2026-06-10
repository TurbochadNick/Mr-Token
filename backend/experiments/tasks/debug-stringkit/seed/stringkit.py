"""Small string utilities. Several functions have bugs that make the test
suite fail. The task: make the tests pass WITHOUT editing test_stringkit.py."""


def slugify(text):
    """Lowercase, spaces to hyphens, drop non-alphanumeric, collapse repeats,
    and strip leading/trailing hyphens. e.g. '  Hello, World!  ' -> 'hello-world'."""
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch.isspace():
            out.append("-")
        # BUG: punctuation is dropped but leaves no separator; also no collapse/strip
    return "".join(out)


def truncate(text, limit):
    """Truncate to `limit` characters, adding '...' if it was shortened.
    The returned string (including '...') must not exceed `limit`."""
    if len(text) <= limit:
        return text
    # BUG: off-by-one / ignores the room needed for the ellipsis
    return text[:limit] + "..."


def word_count(text):
    """Number of whitespace-separated words. Multiple spaces don't count extra."""
    # BUG: split(" ") yields empty strings on runs of spaces
    return len(text.split(" "))


def is_palindrome(text):
    """Case-insensitive, ignoring spaces. 'Never odd or even' -> True."""
    cleaned = text.lower()
    # BUG: spaces not removed
    return cleaned == cleaned[::-1]


def title_case(text):
    """Capitalize the first letter of each word, lowercase the rest."""
    return " ".join(w.capitalize() for w in text.split())
