from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ZipDistrict(Base):
    """ZIP(-code tabulation area) → congressional district crosswalk.

    Powers the "find your representatives" ZIP lookup. One ZIP can span
    multiple (state, district) pairs, so the row grain is one intersection —
    the composite primary key is (zip, state, district). Keyed off the public
    Census ZCTA→CD relationship file (see app/pipelines/zip_crosswalk.py);
    ZCTA ≈ ZIP for lookup purposes (the well-understood caveat documented in
    that pipeline). district 0 = at-large.
    """

    __tablename__ = "zip_districts"

    zip: Mapped[str] = mapped_column(String(5), primary_key=True)
    state: Mapped[str] = mapped_column(String(2), primary_key=True)
    district: Mapped[int] = mapped_column(Integer, primary_key=True)
