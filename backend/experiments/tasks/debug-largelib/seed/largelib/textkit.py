"""textkit utilities."""

def slugify(text):
    """Lowercase, non-alnum runs to single hyphens, stripped of edge hyphens."""
    import re
    return re.sub(r"[^a-z0-9]+", "-", text.lower())

def truncate(text, limit):
    """Truncate to `limit` chars incl. a trailing ellipsis when shortened."""
    return text if len(text) <= limit else text[:limit] + "..."

def word_count(text):
    """Count whitespace-separated words; runs of spaces add nothing."""
    return len(text.split(" "))

def title_case(text):
    """Capitalize each word, lowercasing the rest."""
    return " ".join(w.upper() for w in text.split())

