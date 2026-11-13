from sqlalchemy import SQLColumnExpression, and_, false, or_
from sqlalchemy.sql.elements import ColumnElement


LIKE_ESCAPE = "\\"


def escape_like(term: str) -> str:
    """Escape LIKE metacharacters so the whole term matches literally.

    Pair with ``.ilike(pattern, escape=LIKE_ESCAPE)`` so the escape character is
    explicit rather than relying on the database default."""
    return (
        term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )


def substring_pattern(term: str) -> str:
    """Escape LIKE metacharacters so a substring search treats input literally."""
    return f"%{escape_like(term)}%"


def match_words(term: str, *columns: SQLColumnExpression[str | None]) -> ColumnElement[bool]:
    """Require every literal word in any supplied column, in any order."""
    words = dict.fromkeys(term.replace(",", " ").split())
    if not words or not columns:
        return false()
    return and_(
        *(
            or_(*(column.ilike(substring_pattern(word), escape=LIKE_ESCAPE) for column in columns))
            for word in words
        )
    )
