"""The source registry, the refreshers, and the scheduler must describe the
same set of sources: a refresher outside the registry would run without run
history or locking, and a registered source without a job would never refresh."""

import pytest

from app import scheduler
from app.pipelines import refresh
from app.pipelines.runs import TrackedRefresh, tracked
from app.sources import SOURCES


def test_every_refresher_is_tracked_under_a_registered_source() -> None:
    sources = []
    for name, fn in refresh.REFRESHERS.items():
        assert isinstance(fn, TrackedRefresh), name
        assert fn.source in SOURCES, name
        sources.append(fn.source)
    assert len(sources) == len(set(sources)), "two refreshers record the same source"
    assert set(sources) == set(SOURCES)


def test_every_refresher_has_exactly_one_scheduled_job() -> None:
    scheduled = [fn for _job_id, fn, _trigger in scheduler.JOBS]
    assert all(isinstance(fn, TrackedRefresh) for fn in scheduled)
    assert sorted(fn.source for fn in scheduled) == sorted(
        fn.source for fn in refresh.REFRESHERS.values()
    )


def test_registry_entries_are_well_formed() -> None:
    for name, spec in SOURCES.items():
        assert spec.name == name
        assert spec.endpoints, name
        assert all(e.url.startswith("https://") for e in spec.endpoints), name
        assert all(path.parent.name == "staging" for path in spec.staging_files), name
        # Nothing has had its terms of use reviewed yet; a license must never
        # be asserted without that review.
        assert spec.rights is None, name


def test_fec_candidate_catalog_is_registered_as_official_and_keyed() -> None:
    spec = SOURCES["fec_candidates"]
    assert spec.publisher == "Federal Election Commission (OpenFEC API)"
    assert spec.auth_env == "FEC_API_KEY"
    assert len(spec.endpoints) == 1
    assert spec.endpoints[0].official
    assert spec.staging_files[0].name == "fec_candidates_raw.json"


def test_fec_election_calendar_is_registered_as_official_and_keyed() -> None:
    spec = SOURCES["fec_election_calendar"]
    assert spec.publisher == "Federal Election Commission (OpenFEC API)"
    assert spec.auth_env == "FEC_API_KEY"
    assert len(spec.endpoints) == 1
    assert spec.endpoints[0].official
    assert spec.endpoints[0].url.endswith("/calendar-dates/")
    assert spec.staging_files[0].name == "fec_election_calendar_raw.json"


def test_tracking_rejects_an_unregistered_source() -> None:
    async def fn() -> None:
        return None

    with pytest.raises(ValueError, match="not in app.sources"):
        tracked("not_a_source", fn)
