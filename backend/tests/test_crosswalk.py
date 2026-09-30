"""The id_crosswalk row mapping — the Bioguide-keyed join backbone (AGENTS.md).
The Senate vote pipeline resolves LIS->Bioguide through the `lis` column here, so
a mis-mapped field silently drops Senate vote positions. FEC ids must stay an
array.
"""

from app.normalize.crosswalk import to_crosswalk_row
from app.schemas.member import LegislatorRaw


def test_crosswalk_maps_all_ids():
    rec = {
        "id": {
            "bioguide": "C000127",
            "fec": ["S8WA00194"],
            "govtrack": 300018,
            "opensecrets": "N00007836",
            "thomas": "01527",
            "lis": "S275",
            "votesmart": 27122,
            "wikidata": "Q22222",
        },
        "name": {"first": "Maria", "last": "Cantwell"},
        "terms": [
            {"type": "sen", "start": "2019-01-03", "end": "2025-01-03", "state": "WA", "party": "Democrat"}
        ],
    }
    row = to_crosswalk_row(LegislatorRaw.model_validate(rec))
    assert row["bioguide_id"] == "C000127"
    assert row["fec_ids"] == ["S8WA00194"]
    assert row["lis"] == "S275"
    assert row["govtrack"] == 300018
    assert row["opensecrets"] == "N00007836"


def test_crosswalk_defaults_when_ids_absent():
    rec = {
        "id": {"bioguide": "X000001"},
        "name": {"first": "Ada", "last": "Adams"},
        "terms": [
            {"type": "rep", "start": "2023-01-03", "end": "2025-01-03", "state": "WA", "district": 7, "party": "Democrat"}
        ],
    }
    row = to_crosswalk_row(LegislatorRaw.model_validate(rec))
    assert row["fec_ids"] == []
    assert row["lis"] is None
    assert row["opensecrets"] is None
    assert row["govtrack"] is None
