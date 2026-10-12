"""Parser of bank statements in the 1CClientBankExchange format (version 1.03) and
conversion of documents into account operations.

`parse_1c_statement` is a pure function over bytes. It keeps everything the file says (including the
names of individuals): the parsed statement must never be stored. `statement_to_operations` is the
only way out: it drops personal data (names of individuals, their INN and accounts), see engine/pii.py.
"""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from engine.money import rub_to_kopecks
from engine.pii import public_counterparty, strip_personal_names

HEADER = "1CClientBankExchange"
DOC_TYPES_SECTION = "СекцияДокумент"
FORMAT_ERROR = "Файл не в формате 1С. Нужна выписка «Выгрузка для 1С» (1CClientBankExchange) из интернет-банка."
_INN_PREFIX = re.compile(r"^ИНН\s*(\d{10,12})\s+(.*)$", re.DOTALL)
_ENCODINGS = ("cp1251", "cp866")


class StatementFormatError(ValueError):
    """The file is not a 1C bank statement (message in Russian, safe to show)."""


class UnknownAccountError(ValueError):
    """The statement contains an account that does not belong to the clinic."""

    def __init__(self, account_number: str) -> None:
        super().__init__("В выписке есть счёт, которого нет в клинике.")
        self.account_number = account_number

    @property
    def account_tail(self) -> str:
        return self.account_number[-4:]


@dataclass(frozen=True)
class Section:
    account_number: str
    date_from: date | None
    date_to: date | None
    opening_balance: int
    total_in: int
    total_out: int
    closing_balance: int


@dataclass(frozen=True)
class BankDocument:
    doc_type: str
    number: str
    doc_date: date | None
    debit_date: date | None
    credit_date: date | None
    amount: int
    payer_account: str
    payer_name: str
    payer_inn: str
    receiver_account: str
    receiver_name: str
    receiver_inn: str
    purpose: str


@dataclass(frozen=True)
class ParsedStatement:
    sections: tuple[Section, ...]
    documents: tuple[BankDocument, ...]
    skipped: int  # documents that could not be read (no number, amount or account)


@dataclass(frozen=True)
class NewOperation:
    account_number: str
    date: date
    amount: int  # signed kopecks
    kind: str  # "in" | "out" | "transfer"
    description: str  # purpose without names of individuals
    counterparty_inn: str  # "" for individuals and transfers
    number: str
    external_id: str
    transfer_group: str | None
    counterparty_name: str = ""  # only legal entities and sole proprietors


# ------------------------------------------------------------------ parsing
def _decode(raw: bytes) -> str:
    if b"\x00" in raw:
        raise StatementFormatError(FORMAT_ERROR)
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = ""
    if text.lstrip().startswith(HEADER):
        return text
    for encoding in _ENCODINGS:
        candidate = raw.decode(encoding, errors="replace")
        declared = _declared_encoding(candidate)
        if declared == encoding:
            return candidate
    return raw.decode("cp1251", errors="replace")


def _declared_encoding(text: str) -> str | None:
    for line in text.splitlines()[:30]:
        key, _, value = line.partition("=")
        if key.strip() == "Кодировка":
            value = value.strip().casefold()
            if value.startswith("dos"):
                return "cp866"
            if value.startswith("win"):
                return "cp1251"
    return None


def _parse_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d.%m.%Y").date()
    except ValueError:
        return None


def _parse_amount(value: str) -> int | None:
    value = value.strip().replace(" ", "").replace(" ", "").replace(",", ".")
    if not value:
        return None
    try:
        return rub_to_kopecks(Decimal(value))
    except (InvalidOperation, ValueError):
        return None


def _split_line(line: str) -> tuple[str, str]:
    key, _, value = line.partition("=")
    return key.strip(), value.strip()


def _party(fields: Mapping[str, str], prefix: str) -> tuple[str, str]:
    """(name without the 'ИНН ...' prefix, inn) of the payer or the receiver."""
    name = fields.get(prefix + "1", "") or fields.get(prefix, "")
    inn = fields.get(prefix + "ИНН", "")
    match = _INN_PREFIX.match(name)
    if match:
        inn = inn or match.group(1)
        name = match.group(2)
    if not inn:
        match = _INN_PREFIX.match(fields.get(prefix, ""))
        if match:
            inn = match.group(1)
    return name.strip(), inn.strip()


def _section_from(fields: Mapping[str, str]) -> Section | None:
    number = fields.get("РасчСчет", "")
    if not number:
        return None
    return Section(
        account_number=number,
        date_from=_parse_date(fields.get("ДатаНачала", "")),
        date_to=_parse_date(fields.get("ДатаКонца", "")),
        opening_balance=_parse_amount(fields.get("НачальныйОстаток", "")) or 0,
        total_in=_parse_amount(fields.get("ВсегоПоступило", "")) or 0,
        total_out=_parse_amount(fields.get("ВсегоСписано", "")) or 0,
        closing_balance=_parse_amount(fields.get("КонечныйОстаток", "")) or 0,
    )


def _document_from(doc_type: str, fields: Mapping[str, str]) -> BankDocument | None:
    amount = _parse_amount(fields.get("Сумма", ""))
    number = fields.get("Номер", "")
    payer_account = fields.get("ПлательщикСчет", "") or fields.get("ПлательщикРасчСчет", "")
    receiver_account = fields.get("ПолучательСчет", "") or fields.get("ПолучательРасчСчет", "")
    if amount is None or amount <= 0 or not number or not (payer_account or receiver_account):
        return None
    payer_name, payer_inn = _party(fields, "Плательщик")
    receiver_name, receiver_inn = _party(fields, "Получатель")
    return BankDocument(
        doc_type=doc_type,
        number=number,
        doc_date=_parse_date(fields.get("Дата", "")),
        debit_date=_parse_date(fields.get("ДатаСписано", "")),
        credit_date=_parse_date(fields.get("ДатаПоступило", "")),
        amount=amount,
        payer_account=payer_account,
        payer_name=payer_name,
        payer_inn=payer_inn,
        receiver_account=receiver_account,
        receiver_name=receiver_name,
        receiver_inn=receiver_inn,
        purpose=fields.get("НазначениеПлатежа", ""),
    )


def parse_1c_statement(raw: bytes) -> ParsedStatement:
    """Parse a 1C statement. Repeated documents are kept as they are in the file."""
    text = _decode(raw)
    lines = [line.strip("﻿") for line in text.splitlines()]
    first = next((line.strip() for line in lines if line.strip()), "")
    if first.casefold() != HEADER.casefold():
        raise StatementFormatError(FORMAT_ERROR)
    sections: list[Section] = []
    documents: list[BankDocument] = []
    skipped = 0
    block: str | None = None
    doc_type = ""
    fields: dict[str, str] = {}
    for line in lines:
        key, value = _split_line(line)
        if block is None:
            if key == "СекцияРасчСчет":
                block, fields = "account", {}
            elif key == DOC_TYPES_SECTION:
                block, doc_type, fields = "document", value, {}
            continue
        if key in ("КонецРасчСчет", "КонецДокумента"):
            if block == "account":
                section = _section_from(fields)
                if section is None:
                    raise StatementFormatError(FORMAT_ERROR)
                sections.append(section)
            else:
                document = _document_from(doc_type, fields)
                if document is None:
                    skipped += 1
                else:
                    documents.append(document)
            block = None
        elif key:
            fields[key] = value
    if block is not None or not sections:
        raise StatementFormatError(FORMAT_ERROR)
    return ParsedStatement(tuple(sections), tuple(documents), skipped)


# ------------------------------------------------------------------ operations
def _digest(text: str, length: int) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def external_id_for(
    account: str, number: str, op_date: date, amount: int, counterparty_inn: str
) -> str:
    key = f"{account}|{number}|{op_date.isoformat()}|{amount}|{counterparty_inn}"
    return "1c:" + _digest(key, 32)


def _transfer_group(doc: BankDocument) -> str:
    key = "|".join(
        (
            doc.number,
            str(doc.amount),
            str(doc.debit_date or doc.doc_date),
            str(doc.credit_date or doc.doc_date),
            doc.payer_account,
            doc.receiver_account,
        )
    )
    return "tg:" + _digest(key, 16)


def _leg(
    doc: BankDocument, account: str, outgoing: bool, is_transfer: bool, group: str | None
) -> NewOperation | None:
    op_date = (doc.debit_date if outgoing else doc.credit_date) or doc.doc_date
    if op_date is None:
        return None
    raw_name, raw_inn = (
        (doc.receiver_name, doc.receiver_inn) if outgoing else (doc.payer_name, doc.payer_inn)
    )
    if is_transfer:
        name, inn, individuals = "", "", []
    else:
        name, inn = public_counterparty(raw_name, raw_inn)
        individuals = [] if name else [raw_name]
    description = strip_personal_names(doc.purpose, individuals)
    signed = -doc.amount if outgoing else doc.amount
    return NewOperation(
        account_number=account,
        date=op_date,
        amount=signed,
        kind="transfer" if is_transfer else ("out" if outgoing else "in"),
        description=description,
        counterparty_inn=inn,
        number=doc.number,
        external_id=external_id_for(account, doc.number, op_date, signed, inn),
        transfer_group=group if is_transfer else None,
        counterparty_name=name,
    )


def statement_to_operations(
    parsed: ParsedStatement, own_accounts: Mapping[str, str]
) -> list[NewOperation]:
    """Operations of the clinic accounts in the statement, in file order.

    `own_accounts` maps an account number to the clinic's identifier of that account. A leg is made
    for every clinic account that has a section in the file; a payment between two clinic accounts
    is a transfer (two legs with the same `transfer_group`, one if only one account is in the file).
    """
    file_accounts = {s.account_number for s in parsed.sections}
    for number in sorted(file_accounts):
        if number not in own_accounts:
            raise UnknownAccountError(number)
    operations: list[NewOperation] = []
    for doc in parsed.documents:
        outgoing = doc.payer_account in file_accounts
        incoming = doc.receiver_account in file_accounts
        if doc.payer_account == doc.receiver_account:
            continue
        is_transfer = doc.payer_account in own_accounts and doc.receiver_account in own_accounts
        group = _transfer_group(doc) if is_transfer else None
        for account, is_out in ((doc.payer_account, True), (doc.receiver_account, False)):
            if (is_out and not outgoing) or (not is_out and not incoming):
                continue
            leg = _leg(doc, account, is_out, is_transfer, group)
            if leg is not None:
                operations.append(leg)
    return operations
