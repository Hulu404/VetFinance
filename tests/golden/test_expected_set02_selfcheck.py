"""Internal consistency of set02/expected.json (runs without the engine)."""
from set02_support import EXPECTED, INITIAL, TRUTH


def test_summary_balance_is_income_minus_expense_and_breakdowns_add_up():
    for key in ("summary_after_file1", "summary_final"):
        s = EXPECTED[key]
        assert s["balance"] == s["income"] - s["expense"]
        assert sum(s["income_breakdown"].values()) == s["income"]
        assert sum(s["expense_breakdown"].values()) == s["expense"]
    assert EXPECTED["summary_final"] == EXPECTED["summary_final_after_reupload"]


def test_statement_sections_are_self_consistent():
    for st in EXPECTED["statements"].values():
        for s in st["sections"]:
            assert s["opening_balance"] + s["total_in"] - s["total_out"] == s["closing_balance"]


def test_reuploads_create_nothing_and_counts_add_up():
    steps = EXPECTED["steps"]
    for first, again in (("import_file1", "reimport_file1"), ("import_file2", "reimport_file2")):
        assert steps[again]["created"] == 0
        assert steps[again]["skipped_existing"] == steps[first]["unique_legs"]
    assert steps["import_file1"]["created"] + steps["import_file2"]["created"] + len(INITIAL["existing_transactions"]) + 1 \
        + len(EXPECTED["vetmanager"]["cash_transactions"]) == EXPECTED["total_rows_final"]


def test_labels_and_expected_agree_on_every_leg():
    for lab, t in TRUTH["legs"].items():
        for key, row in EXPECTED["rows_final"].items():
            if key == lab or key.startswith(lab + "/"):
                assert (row["status"], row["category"], row["duplicate_of"]) == (t["status"], t["category"], t["dup_of"])


def test_acquiring_expected_covers_all_card_money():
    days = EXPECTED["acquiring"]
    assert sum(d["card_total"] for d in days) == EXPECTED["vetmanager"]["card_payments_total"]
    assert {d["status"] for d in days} == {"matched", "mismatch", "waiting"}
    for d in days:
        assert d["card_total"] - d["expected_commission"] == d["expected_credit"]
