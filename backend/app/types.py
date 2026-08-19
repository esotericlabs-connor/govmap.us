"""Shared parameter and enum types for the API layer.

Every public ID path param is `Annotated` with FastAPI `Path(...)` constraints
so it's length- and charset-bounded before it reaches business logic — defense
in depth on top of the ORM, and a clean 422 (not a 500) on malformed input. The
chamber vocabularies are single `Literal`s reused across routers instead of
being re-spelled in each one.
"""

from typing import Annotated, Literal

from fastapi import Path

# Chamber vocabularies. Members/votes are house|senate; committees add joint.
Chamber = Literal["house", "senate"]
CommitteeChamber = Literal["house", "senate", "joint"]

# Bioguide IDs are one letter followed by six digits (e.g. "A000360").
BioguideId = Annotated[
    str, Path(pattern=r"^[A-Za-z]\d{6}$", description="Bioguide ID, e.g. A000360")
]

# Internal composite IDs (bill "hr1234-119", vote "h119-1-42", committee "HSAG00"):
# bounded, alphanumeric plus hyphen. Kept charset-based rather than an exact
# structural regex so a new bill/committee code shape can't be silently rejected.
BillId = Annotated[str, Path(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9-]+$")]
VoteId = Annotated[str, Path(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9-]+$")]
CommitteeId = Annotated[str, Path(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9-]+$")]
