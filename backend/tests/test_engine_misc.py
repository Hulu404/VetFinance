from datetime import date, datetime, timedelta, timezone

import pytest

from engine.bank_1c import (
    StatementFormatError,
    UnknownAccountError,
    parse_1c_statement,
    statement_to_operations,
)
from engine.freshness import bank_is_stale, vetmanager_is_stale
from engine.pii import is_legal_entity_name, public_counterparty, strip_personal_names
from engine.sync_counts import sync_counts_figure
from engine.transactions import duplicate_reason, suggestion_text, summarize, transaction_figure
from engine.vetmanager import normalize_vetmanager

STATEMENT = (
    "1CClientBankExchange\r\nВерсияФормата=1.03\r\nКодировка=Windows\r\n"
    "СекцияРасчСчет\r\nДатаНачала=01.09.2026\r\nДатаКонца=05.09.2026\r\nРасчСчет=40702810500000000101\r\n"
    "НачальныйОстаток=1000.00\r\nВсегоПоступило=0.00\r\nВсегоСписано=0.00\r\nКонечныйОстаток=1000.00\r\n"
    "КонецРасчСчет\r\n"
    "СекцияДокумент=Платежное поручение\r\nНомер=7\r\nДата=02.09.2026\r\nСумма=1500,50\r\n"
    "ПлательщикСчет=40702810500000000101\r\nДатаСписано=03.09.2026\r\nПлательщик=ООО Клиника\r\n"
    "ПолучательСчет=40702810999999999999\r\nПолучатель=ИНН 7702000022 ООО Вет-Снаб\r\n"
    "НазначениеПлатежа=Оплата по счёту 5 от Иванов Иван Иванович\r\nКонецДокумента\r\nКонецФайла\r\n"
)
OWN = {"40702810500000000101": "acc-1"}


# ------------------------------------------------------------------ bank statement
def test_statement_parses_comma_amounts_and_cuts_the_name_of_an_individual() -> None:
    parsed = parse_1c_statement(STATEMENT.encode("cp1251"))
    (operation,) = statement_to_operations(parsed, OWN)
    assert operation.amount == -150050 and operation.date == date(2026, 9, 3)
    assert operation.counterparty_inn == "7702000022"
    assert "Иванов" not in operation.description and "Оплата по счёту 5" in operation.description


def test_statement_in_dos_encoding_and_utf8_with_bom() -> None:
    dos = STATEMENT.replace("Кодировка=Windows", "Кодировка=DOS").encode("cp866")
    assert len(parse_1c_statement(dos).documents) == 1
    assert len(parse_1c_statement(b"\xef\xbb\xbf" + STATEMENT.encode("utf-8")).documents) == 1


def test_unknown_account_is_reported_with_its_tail() -> None:
    parsed = parse_1c_statement(STATEMENT.encode("cp1251"))
    with pytest.raises(UnknownAccountError) as error:
        statement_to_operations(parsed, {"40702810500000000999": "acc-2"})
    assert error.value.account_tail == "0101"


@pytest.mark.parametrize("raw", [b"", b"\x00\x01", b"plain text", b"1CClientBankExchange"])
def test_not_a_statement_is_rejected_in_russian(raw: bytes) -> None:
    with pytest.raises(StatementFormatError) as error:
        parse_1c_statement(raw)
    assert "1С" in str(error.value)


def test_pii_helpers() -> None:
    assert is_legal_entity_name('ООО "Вет-Снаб"') and is_legal_entity_name(
        "ИП Козлов Андрей Викторович"
    )
    assert not is_legal_entity_name("Иванов Иван Иванович")
    assert public_counterparty("Иванов Иван Иванович", "123456789012") == ("", "")
    cleaned = strip_personal_names("Оплата приёма, Петрова А.И., тел. +7 916 123-45-67, a@b.ru")
    assert "Петрова" not in cleaned and "916" not in cleaned and "@" not in cleaned
    assert (
        strip_personal_names("за ИП Козлов Андрей Викторович") == "за ИП Козлов Андрей Викторович"
    )


# ------------------------------------------------------------------ summary and texts
def row(
    day: int,
    amount: int,
    kind: str,
    status: str = "ok",
    category: str | None = "A",
    source: str = "bank",
) -> dict[str, object]:
    return {
        "date": date(2026, 9, day),
        "amount": amount,
        "kind": kind,
        "status": status,
        "category": category,
        "source": source,
    }


def test_summary_rules_and_identity() -> None:
    rows = [
        row(1, 1000, "in"),
        row(2, 500, "in", "check", None, "manual"),
        row(3, -300, "out", "check", None),
        row(4, -200, "out", category="Аренда"),
        row(5, 9999, "in", "duplicate"),
        row(6, 777, "transfer"),
        row(7, 5000, "in", category="Октябрь").copy() | {"date": date(2026, 10, 1)},
    ]
    result = summarize(rows, "2026-09")
    assert (result.income.value, result.expense.value, result.balance.value) == (1500, 500, 1000)
    assert [(i.label, i.value) for i in result.expense.breakdown] == [
        ("Аренда", 200),
        ("Без статьи", 300),
    ]
    assert sum(i.value for i in result.income.breakdown) == 1500
    assert sum(i.value for i in result.balance.breakdown) == result.balance.value
    assert result.income.source == ("bank", "manual") and "сентябрь 2026" in result.income.note
    assert result.expense.breakdown[-1].label == "Без статьи"


def test_empty_month_has_a_placeholder_breakdown_and_manual_source() -> None:
    result = summarize([], "2026-09")
    assert result.income.value == 0 and result.income.breakdown[0].label == "Нет операций"
    assert result.income.source == ("manual",)


def test_transaction_figure_notes() -> None:
    def note(**kw: object) -> str:
        base = dict(
            amount=-5000, op_date=date(2026, 9, 9), source="bank", account_name="Касса", kind="out",
            status="ok", category_source="rule", category_name="Аренда", rule_name="ИП Волков",
        )  # fmt: skip
        return transaction_figure(**{**base, **kw}).note  # type: ignore[arg-type]

    assert "правилом «ИП Волков»" in note()
    assert "выбрана вручную" in note(category_source="manual")
    assert "ждёт проверки" in note(category_name=None, category_source=None)
    assert "Перевод между своими счетами" in note(kind="transfer")
    assert "не входит в остаток" in note(status="duplicate")
    figure = transaction_figure(
        amount=-5000, op_date=date(2026, 9, 9), source="manual", account_name="Касса", kind="out",
        status="ok", category_source=None, category_name=None, rule_name=None,
    )  # fmt: skip
    assert figure.breakdown[0].value == figure.value and figure.source == ("manual",)


def test_duplicate_reason_and_suggestion_text() -> None:
    assert duplicate_reason(-540000, date(2026, 9, 6), date(2026, 9, 6)) == (
        "одинаковая сумма 5 400 ₽, дата 6 сен, разные источники"
    )
    assert "даты 6 и 8 сен" in duplicate_reason(540000, date(2026, 9, 8), date(2026, 9, 6))
    assert "даты 30 авг и 1 сен" in duplicate_reason(1, date(2026, 8, 30), date(2026, 9, 1))
    assert (
        suggestion_text("similar", 1, "ИП Волков") == "так же разнесена 1 операция по «ИП Волков»"
    )
    assert (
        suggestion_text("similar", 3, "ИП Волков") == "так же разнесено 3 операции по «ИП Волков»"
    )
    assert suggestion_text("similar", 5, "") == "так же разнесено 5 операций по этому контрагенту"
    assert suggestion_text("rule", 0, "ИП Волков") == "по правилу для «ИП Волков»"


def test_sync_counts_figure_sums_to_value() -> None:
    figure = sync_counts_figure(21, 3, 2)
    assert figure.value == 24 and sum(i.value for i in figure.breakdown) == 24
    assert (
        figure.unit == "count"
        and "как дубли" in figure.note
        and "дубли (уже были, без изменений): 2" in figure.note
    )


# ------------------------------------------------------------------ freshness
def test_freshness_thresholds() -> None:
    now = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)  # noqa: UP017
    assert not vetmanager_is_stale(True, now - timedelta(hours=36), now)
    assert vetmanager_is_stale(True, now - timedelta(hours=36, minutes=1), now)
    assert not vetmanager_is_stale(False, now - timedelta(days=9), now)
    assert not vetmanager_is_stale(True, None, now)
    assert not bank_is_stale(date(2026, 9, 23), date(2026, 9, 30))
    assert bank_is_stale(date(2026, 9, 22), date(2026, 9, 30))
    assert not bank_is_stale(None, date(2026, 9, 30))


# ------------------------------------------------------------------ Vetmanager
def entity(name: str, items: list[dict[str, str]]) -> dict[str, object]:
    return {"success": True, "data": {"totalCount": str(len(items)), name: items}}


def test_vetmanager_normaliser_edge_cases() -> None:
    raw = {
        "user": entity("user", [{"id": "11", "last_name": "Б", "first_name": "Б"}, {"id": "10", "last_name": "А", "first_name": "А"}]),
        "good": entity("good", [{"id": "1", "is_service": "1"}, {"id": "2", "is_service": "0"}]),
        "cassa": entity("cassa", [{"id": "1", "type": "cash"}, {"id": "2", "type": "card"}, {"id": "3", "type": "bonus"}]),
        "admission": entity("admission", [
            {"id": "1", "user_id": "10", "admission_date": "2026-09-01 09:00:00", "status": "save", "description": "секрет"},
            {"id": "2", "user_id": "10", "admission_date": "2026-09-01 10:00:00", "status": "delete"},
            {"id": "3", "user_id": "10", "admission_date": "битая дата", "status": "save"},
        ]),
        "invoice": entity("invoice", [
            {"id": "5", "invoice_date": "2026-09-01 09:00:00", "amount": "300.10", "status": "exec"},
            {"id": "6", "invoice_date": "2026-09-01 09:00:00", "amount": "10", "status": "deleted"},
            {"id": "7", "invoice_date": "2026-09-02 09:00:00", "amount": "oops", "status": "exec"},
        ]),
        "invoiceDocument": entity("invoiceDocument", [
            {"invoice_id": "5", "good_id": "1", "quantity": "1.5", "price": "100.00"},
            {"invoice_id": "5", "good_id": "2", "quantity": "3", "price": "50.0333"},
        ]),
        "payment": entity("payment", [
            {"id": "9", "invoice_id": "5", "cassa_id": "1", "amount": "100.5", "status": "exec", "create_date": "2026-09-01 10:00:00"},
            {"id": "10", "cassa_id": "3", "amount": "1", "status": "exec", "create_date": "2026-09-01 10:00:00"},
            {"id": "11", "cassa_id": "2", "amount": "1", "status": "deleted", "create_date": "2026-09-01 10:00:00"},
        ]),
        "client": entity("client", [{"id": "1", "last_name": "Секретов"}]),
    }  # fmt: skip
    result = normalize_vetmanager(raw)
    assert [d.code for d in result.doctors] == ["D1", "D2"] and result.doctors[
        0
    ].external_id.endswith(":10")
    assert [v.external_id for v in result.visits] == [
        "vetmanager:admission:1"
    ] and result.skipped == 3
    (sale,) = result.sales
    assert sale.amount == 30010 and [(ln.kind, ln.amount) for ln in sale.lines] == [
        ("service", 15000),
        ("good", 15010),
    ]
    assert [(p.external_id, p.method, p.amount) for p in result.payments] == [
        ("vetmanager:payment:9", "cash", 10050)
    ]
    assert "Секретов" not in repr(result) and "секрет" not in repr(result)
    assert normalize_vetmanager({}).visits == ()
