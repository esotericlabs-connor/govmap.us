"""Response shape for GET /api/sources, the public data-pipeline status page.

Only what is already public in the source registry plus when each source last
refreshed successfully. Run outcomes, record counts and error detail stay on
the authenticated /internal endpoints.
"""

from datetime import datetime

from pydantic import BaseModel


class SourceEndpointOut(BaseModel):
    url: str
    # True when the publisher is the government body that produces the record.
    official: bool


class SourceStatusOut(BaseModel):
    name: str
    title: str
    publisher: str
    # Last successful refresh; null when it has never succeeded.
    last_success: datetime | None
    # Whether the publisher requires an access key; the key itself is never exposed.
    requires_key: bool
    endpoints: list[SourceEndpointOut]


class SourcesOut(BaseModel):
    generated_at: datetime
    sources: list[SourceStatusOut]
