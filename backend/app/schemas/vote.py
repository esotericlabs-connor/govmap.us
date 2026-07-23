from datetime import date

from pydantic import BaseModel, ConfigDict

# --- Layer 3: API response shape ---
# The roll-call sources are XML (House Clerk EVS / Senate LIS), parsed manually
# in the pipelines into canonical dicts, so there is no Pydantic *Raw model here
# (unlike the bulk-file / keyed-REST sources). Only the response shape is typed.


class VoteOut(BaseModel):
    vote_id: str
    chamber: str
    congress: int
    session: int
    roll_number: int
    date: date | None
    question: str | None
    result: str | None
    bill_id: str | None
    totals: dict | None

    model_config = ConfigDict(from_attributes=True)
