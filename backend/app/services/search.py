def substring_pattern(term: str) -> str:
    """Escape LIKE metacharacters so a substring search treats input literally."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
