from sqlalchemy import ARRAY, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class IdCrosswalk(Base):
    """Cross-source identifier map keyed on Bioguide ID.

    AGENTS.md: this is the backbone of every cross-source join — Bioguide ID is
    the master key, and this table resolves it to the FEC / OpenSecrets / etc.
    IDs that finance, votes, and bills data arrive under. Populated from the
    `id` block of legislators-current.yaml, which we already stage.
    """

    __tablename__ = "id_crosswalk"

    bioguide_id: Mapped[str] = mapped_column(
        String(7), ForeignKey("members.bioguide_id", ondelete="CASCADE"), primary_key=True
    )
    # Members generate a new FEC candidate ID per cycle — stored as an array
    # (AGENTS.md), never a single value.
    fec_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    govtrack: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opensecrets: Mapped[str | None] = mapped_column(String(20), nullable=True)
    thomas: Mapped[str | None] = mapped_column(String(10), nullable=True)
    lis: Mapped[str | None] = mapped_column(String(10), nullable=True)
    votesmart: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wikidata: Mapped[str | None] = mapped_column(String(20), nullable=True)
