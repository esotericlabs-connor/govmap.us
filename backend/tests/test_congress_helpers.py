"""The party-bucket collapse that drives the chamber balance bars and map colors.
Anything not clearly D/R buckets to Independent."""

from app.routers.congress import _party_bucket


def test_party_bucket_democrat():
    assert _party_bucket("Democrat") == "D"
    assert _party_bucket("democrat") == "D"


def test_party_bucket_republican():
    assert _party_bucket("Republican") == "R"


def test_party_bucket_independent_and_unknown_default_to_i():
    assert _party_bucket("Independent") == "I"
    assert _party_bucket("Libertarian") == "I"
    assert _party_bucket(None) == "I"
    assert _party_bucket("") == "I"
