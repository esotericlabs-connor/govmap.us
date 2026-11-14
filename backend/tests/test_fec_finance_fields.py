from app.pipelines.fec_finance import _row
from app.schemas.finance import CandidateTotalRaw


def test_candidate_totals_preserve_current_openfec_balance_fields() -> None:
    total = CandidateTotalRaw.model_validate(
        {
            "cycle": 2026,
            "receipts": 100.25,
            "last_cash_on_hand_end_period": 42.50,
            "last_debts_owed_by_committee": 12.75,
        }
    )

    row = _row("A000001", "H0CA00001", total)
    assert row["cash_on_hand"] == 42.50
    assert row["debts"] == 12.75
    assert row["receipts"] == 100.25


def test_candidate_totals_prefer_publisher_fields_over_legacy_names() -> None:
    total = CandidateTotalRaw.model_validate(
        {
            "last_cash_on_hand_end_period": None,
            "cash_on_hand_end_period": 99.0,
            "last_debts_owed_by_committee": 12.0,
            "debts_owed_by_committee": 88.0,
        }
    )
    assert total.cash_on_hand_end_period is None
    assert total.debts_owed_by_committee == 12.0


def test_candidate_totals_still_accept_legacy_field_names() -> None:
    total = CandidateTotalRaw.model_validate(
        {"cash_on_hand_end_period": 42.5, "debts_owed_by_committee": 12.75}
    )
    assert total.cash_on_hand_end_period == 42.5
    assert total.debts_owed_by_committee == 12.75
