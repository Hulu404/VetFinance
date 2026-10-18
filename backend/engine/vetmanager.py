"""Normalisation of Vetmanager REST responses into visits, sales, doctors and payments.

The input is `{entity: full JSON response}`; the response format is `{"data": {"<entity>": [ ... ]}}`
with numbers and ids as strings. NOTE: the format follows the Vetmanager REST API as remembered, it has
to be checked against a real account (the normaliser is the only place that depends on it).

Personal data never leave this module: the entities `client` and `pet` are not read at all, and a
visit keeps only its date and the doctor (free text of the visit is dropped). Doctors keep a short code
(`D1`, `D2`, ...) next to the name; the name is for the clinic's own screens and never goes to the AI layer.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from engine.money import rub_to_kopecks

PREFIX = "vetmanager"
STATUS_EXEC = "exec"
STATUS_DRAFT = "save"
VISIT_DELETED = "delete"
PAYMENT_DROPPED = frozenset({"delete", "deleted", "cancel", "canceled"})
KIND_SERVICE = "service"
KIND_GOOD = "good"
METHOD_CASH = "cash"
METHOD_CARD = "card"


@dataclass(frozen=True)
class Doctor:
    external_id: str
    code: str
    name: str


@dataclass(frozen=True)
class Visit:
    external_id: str
    date: date
    doctor_external_id: str | None


@dataclass(frozen=True)
class Service:
    """A service of the clinic: a `good` of Vetmanager with `is_service = 1` (name and group, no personal data)."""

    external_id: str
    name: str
    group: str | None


@dataclass(frozen=True)
class SaleLine:
    kind: str  # "service" | "good"
    amount: int  # kopecks, quantity x price
    # stage 5: what the line sold. Old rows have none of it.
    service_external_id: str | None = None  # `Service.external_id` of a "service" line
    name: str = ""  # the title of the service
    qty: Decimal = Decimal(1)
    price: int = 0  # kopecks per unit


@dataclass(frozen=True)
class Sale:
    external_id: str
    date: date
    status: str  # "exec" | "save"
    amount: int
    lines: tuple[SaleLine, ...]


@dataclass(frozen=True)
class Payment:
    external_id: str
    date: date
    amount: int
    method: str  # "cash" | "card"
    invoice_external_id: str | None


@dataclass(frozen=True)
class NormalizedVetmanager:
    doctors: tuple[Doctor, ...]
    visits: tuple[Visit, ...]
    sales: tuple[Sale, ...]
    payments: tuple[Payment, ...]
    skipped: int  # records that could not be read or whose cash desk is unknown
    services: tuple[Service, ...] = ()  # stage 5: the services that appear in the sales


def _items(raw: Mapping[str, Any], entity: str) -> list[Mapping[str, Any]]:
    response = raw.get(entity)
    if not isinstance(response, Mapping):
        return []
    data = response.get("data")
    items = data.get(entity) if isinstance(data, Mapping) else None
    return [item for item in items if isinstance(item, Mapping)] if isinstance(items, list) else []


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(_text(value)[:10])
    except ValueError:
        return None


def _kopecks(value: Any) -> int | None:
    try:
        return rub_to_kopecks(Decimal(_text(value)))
    except (InvalidOperation, ValueError):
        return None


def _line_amount(quantity: Any, price: Any) -> int | None:
    try:
        return rub_to_kopecks(Decimal(_text(quantity)) * Decimal(_text(price)))
    except (InvalidOperation, ValueError):
        return None


def _doctors(users: Sequence[Mapping[str, Any]]) -> tuple[Doctor, ...]:
    ordered = sorted(users, key=lambda u: (len(_text(u.get("id"))), _text(u.get("id"))))
    doctors: list[Doctor] = []
    for number, user in enumerate(ordered, start=1):
        name = " ".join(
            part
            for part in (
                _text(user.get("last_name")),
                _text(user.get("first_name")),
                _text(user.get("middle_name")),
            )
            if part
        )
        doctors.append(
            Doctor(f"{PREFIX}:user:{_text(user.get('id'))}", f"D{number}", name or f"D{number}")
        )
    return tuple(doctors)


def _visits(admissions: Sequence[Mapping[str, Any]]) -> tuple[list[Visit], int]:
    visits: list[Visit] = []
    skipped = 0
    for item in admissions:
        if _text(item.get("status")).casefold() == VISIT_DELETED:
            continue
        day = _day(item.get("admission_date"))
        if day is None or not _text(item.get("id")):
            skipped += 1
            continue
        user_id = _text(item.get("user_id"))
        doctor = f"{PREFIX}:user:{user_id}" if user_id else None
        visits.append(Visit(f"{PREFIX}:admission:{_text(item['id'])}", day, doctor))
    return visits, skipped


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(_text(value))
    except InvalidOperation:
        return None


def _lines_by_invoice(
    documents: Sequence[Mapping[str, Any]], goods: Mapping[str, bool], titles: Mapping[str, str]
) -> dict[str, list[SaleLine]]:
    lines: dict[str, list[SaleLine]] = {}
    for item in documents:
        amount = _line_amount(item.get("quantity"), item.get("price"))
        if amount is None:
            continue
        good_id = _text(item.get("good_id"))
        qty, price = _decimal(item.get("quantity")), _kopecks(item.get("price"))
        if goods.get(good_id, False):
            line = SaleLine(
                KIND_SERVICE, amount, f"{PREFIX}:good:{good_id}", titles.get(good_id, ""),
                qty if qty is not None and qty > 0 else Decimal(1), price or 0,
            )  # fmt: skip
        else:
            line = SaleLine(KIND_GOOD, amount)
        lines.setdefault(_text(item.get("invoice_id")), []).append(line)
    return lines


def _services(
    goods: Sequence[Mapping[str, Any]], groups: Mapping[str, str], used: set[str]
) -> tuple[Service, ...]:
    """Services that are sold (appear in invoice lines) and have a title."""
    found = []
    for g in goods:
        ext = f"{PREFIX}:good:{_text(g.get('id'))}"
        title = _text(g.get("title")) or _text(g.get("name"))
        if _text(g.get("is_service")) == "1" and ext in used and title:
            found.append(Service(ext, title, groups.get(_text(g.get("group_id"))) or None))
    return tuple(sorted(found, key=lambda x: x.external_id))


def _sales(
    invoices: Sequence[Mapping[str, Any]], lines: Mapping[str, list[SaleLine]]
) -> tuple[list[Sale], int]:
    sales: list[Sale] = []
    skipped = 0
    for item in invoices:
        status = _text(item.get("status")).casefold()
        if status not in (STATUS_EXEC, STATUS_DRAFT):
            continue  # deleted invoices are dropped
        day, amount = _day(item.get("invoice_date")), _kopecks(item.get("amount"))
        if day is None or amount is None or not _text(item.get("id")):
            skipped += 1
            continue
        invoice_id = _text(item["id"])
        sales.append(
            Sale(
                f"{PREFIX}:invoice:{invoice_id}",
                day,
                status,
                amount,
                tuple(lines.get(invoice_id, [])),
            )
        )
    return sales, skipped


def _payments(
    payments: Sequence[Mapping[str, Any]], cash_desks: Mapping[str, str]
) -> tuple[list[Payment], int]:
    result: list[Payment] = []
    skipped = 0
    for item in payments:
        if _text(item.get("status")).casefold() in PAYMENT_DROPPED:
            continue
        method = cash_desks.get(_text(item.get("cassa_id")))
        day, amount = _day(item.get("create_date")), _kopecks(item.get("amount"))
        if method is None or day is None or amount is None or not _text(item.get("id")):
            skipped += 1
            continue
        invoice = _text(item.get("invoice_id"))
        result.append(
            Payment(
                f"{PREFIX}:payment:{_text(item['id'])}",
                day,
                amount,
                method,
                f"{PREFIX}:invoice:{invoice}" if invoice else None,
            )
        )
    return result, skipped


def normalize_vetmanager(raw: Mapping[str, Mapping[str, Any]]) -> NormalizedVetmanager:
    """Visits, sales (with service/good lines), payments and doctors from the raw API responses."""
    goods = {_text(g.get("id")): _text(g.get("is_service")) == "1" for g in _items(raw, "good")}
    cash_desks = {
        _text(c.get("id")): _text(c.get("type")).casefold()
        for c in _items(raw, "cassa")
        if _text(c.get("type")).casefold() in (METHOD_CASH, METHOD_CARD)
    }
    visits, skipped_visits = _visits(_items(raw, "admission"))
    good_items = _items(raw, "good")
    titles = {_text(g.get("id")): _text(g.get("title")) or _text(g.get("name")) for g in good_items}
    lines = _lines_by_invoice(_items(raw, "invoiceDocument"), goods, titles)
    groups = {_text(g.get("id")): _text(g.get("title")) for g in _items(raw, "goodGroup")}
    used = {x.service_external_id for ls in lines.values() for x in ls if x.service_external_id}
    sales, skipped_sales = _sales(_items(raw, "invoice"), lines)
    payments, skipped_payments = _payments(_items(raw, "payment"), cash_desks)
    return NormalizedVetmanager(
        doctors=_doctors(_items(raw, "user")),
        visits=tuple(visits),
        sales=tuple(sales),
        payments=tuple(payments),
        skipped=skipped_visits + skipped_sales + skipped_payments,
        services=_services(good_items, groups, {u for u in used if u}),
    )
