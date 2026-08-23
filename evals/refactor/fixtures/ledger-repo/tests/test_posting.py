from __future__ import annotations

from decimal import Decimal

from ledger.export import to_csv
from ledger.posting import post, trial_balance


def entry(account, amount, side="debit"):
    return {"account": account, "amount": Decimal(amount), "side": side}


def test_a_debit_opens_an_account():
    assert post({}, [entry("cash", "10.00")]) == {"cash": Decimal("10.00")}


def test_a_credit_opens_an_account_negative():
    assert post({}, [entry("cash", "10.00", "credit")]) == {"cash": Decimal("-10.00")}


def test_postings_accumulate():
    book = post({}, [entry("cash", "10.00"), entry("cash", "5.00")])
    assert book["cash"] == Decimal("15.00")


def test_a_credit_reduces_an_existing_balance():
    book = post({"cash": Decimal("10.00")}, [entry("cash", "4.00", "credit")])
    assert book["cash"] == Decimal("6.00")


def test_entries_without_an_account_are_ignored():
    assert post({}, [{"amount": Decimal("1.00")}]) == {}


def test_entries_without_an_amount_are_ignored():
    assert post({}, [{"account": "cash"}]) == {}


def test_the_input_book_is_not_mutated():
    book = {"cash": Decimal("10.00")}
    post(book, [entry("cash", "5.00")])
    assert book == {"cash": Decimal("10.00")}


def test_trial_balance_splits_debits_from_credits():
    book = {"cash": Decimal("10.00"), "revenue": Decimal("-10.00")}
    assert trial_balance(book) == {
        "debit": Decimal("10.00"),
        "credit": Decimal("10.00"),
        "balanced": True,
    }


def test_an_unbalanced_book_is_reported_as_such():
    assert trial_balance({"cash": Decimal("10.00")})["balanced"] is False


def test_csv_has_a_header_and_one_row_per_account():
    csv = to_csv({"cash": Decimal("10.00"), "revenue": Decimal("-10.00")})
    assert csv.splitlines()[0] == "account,debit,credit"
    assert csv.splitlines()[1] == "cash,10.00,"
    assert csv.splitlines()[2] == "revenue,,10.00"


def test_csv_rows_are_sorted_by_account():
    csv = to_csv({"z": Decimal("1.00"), "a": Decimal("1.00")})
    assert csv.splitlines()[1].startswith("a,")
