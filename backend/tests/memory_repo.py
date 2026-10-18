"""In-memory Repository for API tests: the same behaviour as PgRepository, without a database.

Everything is kept per clinic (one clinic per instance). Ids are deterministic UUIDs.
"""

import dataclasses
import json
import uuid
from collections.abc import Collection, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.rows import (
    AccountRow,
    CardPaymentRow,
    CategoryRow,
    ClinicRow,
    ConnectionRow,
    NewTx,
    ReviewRow,
    RuleRow,
    SummaryRow,
    SyncRunRow,
    TxRow,
)
from engine.balance import AccountInput, TransactionInput
from engine.dashboard_inputs import NormsInput, SaleInput, SaleLineInput, VisitInput
from engine.dedup import TxRef
from engine.efficiency_inputs import DoctorInput
from engine.planning_inputs import CounterpartyTermsInput, ObligationInput, PlannedPaymentInput
from engine.reports_inputs import (
    BenchmarkInput,
    ConsumptionInput,
    ObligationChargeInput,
    StockBatchInput,
    StockItemInput,
    WriteoffInput,
)
from engine.vetmanager import Payment, Sale, Visit
from tests.memory_pricing import MemoryPricing

BASE_TIME = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
EDITABLE = {
    "category_id",
    "category_source",
    "rule_id",
    "status",
    "duplicate_of",
    "duplicate_state",
    "duplicate_dismissed",
}


class MemoryRepo(MemoryPricing):
    def __init__(self, clinic: ClinicRow | None = None) -> None:
        self.clinic = clinic or ClinicRow("c1", "Клиника", None, None, "Europe/Moscow", 0)
        self.acquiring_rate_bp = 190
        self.norms = NormsInput("Препараты и расходники", 25, 12)
        self.accounts: list[AccountRow] = []
        self.categories: list[CategoryRow] = []
        self.rules: list[RuleRow] = []
        self.txs: list[TxRow] = []
        self.tx_extra: dict[str, dict[str, Any]] = {}  # external_id, import_id, doc_number, ...
        self.raw_events: list[dict[str, Any]] = []
        self.connections: list[ConnectionRow] = []
        self.secrets: dict[str, str] = {}
        self.runs: list[SyncRunRow] = []
        self.doctors: dict[str, tuple[str, str, str]] = {}
        self.visits: dict[str, tuple[date, str | None]] = {}
        self.sales: dict[str, Sale] = {}
        self.payments: dict[str, tuple[Payment, str | None]] = {}
        self.reviews: dict[date, str | None] = {}
        self.charges: list[ObligationChargeInput] = []
        self.obligations: list[ObligationInput] = []
        self.planned: list[PlannedPaymentInput] = []
        self.terms: dict[str, CounterpartyTermsInput] = {}
        self.benchmarks: list[BenchmarkInput] = []
        self.stock_items: list[StockItemInput] = []
        self.stock_batches: list[StockBatchInput] = []
        self.writeoffs: list[WriteoffInput] = []
        self.consumption: list[ConsumptionInput] = []
        self.init_pricing()
        self.now = BASE_TIME  # "current" time of the data layer (run start, event time)
        self._seq = 0

    # ------------------------------------------------------------ helpers
    def new_id(self) -> str:
        self._seq += 1
        return str(uuid.UUID(int=self._seq))

    def _account(self, account_id: str) -> AccountRow:
        return next(a for a in self.accounts if a.id == account_id)

    def _category_name(self, category_id: str | None) -> str | None:
        if category_id is None:
            return None
        return next(c.name for c in self.categories if c.id == category_id)

    def add_account(self, **fields: Any) -> AccountRow:
        row = AccountRow(
            id=fields.pop("id", None) or self.new_id(),
            name=fields["name"],
            kind=fields["kind"],
            opening_balance=fields.get("opening_balance", 0),
            opening_date=fields.get("opening_date", date(2000, 1, 1)),
            number=fields.get("number"),
            last_statement_to=fields.get("last_statement_to"),
        )
        self.accounts.append(row)
        return row

    def add_category(
        self,
        name: str,
        type_: str = "variable",
        *,
        norm_min_pct: float | None = None,
        norm_max_pct: float | None = None,
        norm_key: str | None = None,
        direction: str | None = None,
        payroll: bool = False,
        in_service_recipes: bool = False,
        doctor_percent: bool = False,
    ) -> CategoryRow:
        row = CategoryRow(
            self.new_id(), name, type_, norm_min_pct, norm_max_pct, norm_key, direction, payroll,
            in_service_recipes, doctor_percent,
        )  # fmt: skip
        self.categories.append(row)
        return row

    def add_rule(
        self,
        match: str,
        value: str,
        direction: str | None,
        category: str,
        display_name: str | None = None,
    ) -> RuleRow:
        row = RuleRow(
            self.new_id(), match, value, display_name, direction, category,
            self._category_name(category) or "", BASE_TIME + timedelta(seconds=self._seq),
        )  # fmt: skip
        self.rules.append(row)
        return row

    def add_connections(self) -> None:
        self.connections = [
            ConnectionRow(self.new_id(), "vetmanager", None, None),
            ConnectionRow(self.new_id(), "bank", None, None),
        ]

    def add_tx(
        self,
        account_id: str,
        day: date,
        amount: int,
        *,
        source: str = "bank",
        status: str = "ok",
        category_id: str | None = None,
        kind: str | None = None,
        description: str = "",
        inn: str = "",
        counterparty_name: str = "",
    ) -> TxRow:
        new_id = self.new_id()
        row = TxRow(
            id=new_id, date=day, description=description, amount=amount,
            kind=kind or ("in" if amount > 0 else "out"), source=source, status=status,
            account_id=account_id, account_name=self._account(account_id).name,
            category_id=category_id, category_name=self._category_name(category_id),
            category_source=None, rule_id=None, counterparty_inn=inn, counterparty_name=counterparty_name,
            duplicate_of=None, duplicate_state=None, duplicate_dismissed=False,
            created_at=BASE_TIME + timedelta(seconds=self._seq),
        )  # fmt: skip
        self.txs.append(row)
        self.tx_extra[new_id] = {"external_id": None, "import_id": None}
        return row

    def tx(self, tx_id: str) -> TxRow:
        return next(t for t in self.txs if t.id == tx_id)

    def _refresh(self, row: TxRow) -> TxRow:
        return dataclasses.replace(
            row,
            account_name=self._account(row.account_id).name,
            category_name=self._category_name(row.category_id),
        )

    # ------------------------------------------------------------ clinic and accounts
    async def get_clinic(self) -> ClinicRow:
        return self.clinic

    async def update_clinic(self, changes: dict[str, Any]) -> ClinicRow:
        self.clinic = dataclasses.replace(self.clinic, **changes)
        return self.clinic

    async def get_acquiring_rate_bp(self) -> int:
        return self.acquiring_rate_bp

    async def list_accounts(self) -> list[AccountInput]:
        return [
            AccountInput(a.id, a.name, a.kind, a.opening_balance, a.opening_date)
            for a in sorted(self.accounts, key=lambda a: (a.name, a.id))
        ]

    async def list_account_rows(self) -> list[AccountRow]:
        return sorted(self.accounts, key=lambda a: (a.name, a.id))

    async def set_last_statement_to(self, account_id: str, day: date) -> None:
        for i, a in enumerate(self.accounts):
            if a.id == account_id:
                latest = max(day, a.last_statement_to) if a.last_statement_to else day
                self.accounts[i] = dataclasses.replace(a, last_statement_to=latest)

    # ------------------------------------------------------------ balance
    async def list_transactions(self, as_of: date) -> list[TransactionInput]:
        return [
            TransactionInput(
                t.account_id,
                t.date,
                t.amount,
                t.status,
                t.source,
                t.kind,
                t.category_name,
                t.counterparty_inn,
                t.counterparty_name,
            )
            for t in self.txs
            if t.date <= as_of and t.status != "duplicate"
        ]

    async def last_data_at(self) -> datetime | None:
        return max((t.created_at for t in self.txs), default=None)

    # ------------------------------------------------------------ dashboard
    async def get_norms(self) -> NormsInput:
        return self.norms

    async def list_sales(self, first: date, last: date) -> list[SaleInput]:
        return [
            SaleInput(
                s.date, s.status, tuple(SaleLineInput(line.kind, line.amount) for line in s.lines)
            )
            for s in self.sales.values()
            if first <= s.date <= last
        ]

    async def list_visits(self, first: date, last: date) -> list[VisitInput]:
        names = {d[0]: d[2] for d in self.doctors.values()}
        return [
            VisitInput(day, names.get(doctor_id or "", ""), doctor_id)
            for day, doctor_id in self.visits.values()
            if first <= day <= last
        ]

    # ------------------------------------------------------------ categories and rules
    async def list_categories(self) -> list[CategoryRow]:
        order = ("income", "variable", "fixed", "tax", "obligation", "capex", "owner_draw")
        return sorted(self.categories, key=lambda c: (order.index(c.type), c.name))

    # ------------------------------------------------------------ reports (stage 3)
    async def list_obligation_charges(self) -> list[ObligationChargeInput]:
        return list(self.charges)

    async def list_benchmarks(self) -> list[BenchmarkInput]:
        return sorted(self.benchmarks, key=lambda b: (b.sort, b.key))

    async def list_stock_items(self) -> list[StockItemInput]:
        return sorted(self.stock_items, key=lambda i: (i.name, i.id))

    async def list_stock_batches(self) -> list[StockBatchInput]:
        return [b for b in self.stock_batches if b.qty > 0]

    async def list_writeoffs(self, first: date, last: date) -> list[WriteoffInput]:
        return [w for w in self.writeoffs if first <= w.date <= last]

    async def list_stock_consumption(self, first: date, last: date) -> list[ConsumptionInput]:
        return [c for c in self.consumption if first <= c.date <= last]

    async def list_rules(self) -> list[RuleRow]:
        return list(self.rules)

    async def insert_rule(
        self,
        *,
        match: str,
        value: str,
        display_name: str | None,
        direction: str | None,
        category_id: str,
    ) -> RuleRow:
        return self.add_rule(match, value, direction, category_id, display_name)

    async def delete_rule(self, rule_id: str) -> bool:
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.id != rule_id]
        self.txs = [
            dataclasses.replace(t, rule_id=None) if t.rule_id == rule_id else t for t in self.txs
        ]
        return len(self.rules) < before

    async def rule_applied_counts(self, month_start: date) -> dict[str, tuple[int, int]]:
        counts: dict[str, tuple[int, int]] = {}
        for t in self.txs:
            if t.rule_id:
                month, total = counts.get(t.rule_id, (0, 0))
                counts[t.rule_id] = (month + (1 if t.date >= month_start else 0), total + 1)
        return counts

    # ------------------------------------------------------------ transactions
    async def page_transactions(
        self,
        *,
        tab: str,
        date_from: date | None,
        date_to: date | None,
        limit: int,
        after: tuple[date, str] | None,
    ) -> list[TxRow]:
        rows = [self._refresh(t) for t in self.txs]
        if tab == "check":
            rows = [t for t in rows if t.status == "check"]
        elif tab == "duplicates":
            rows = [
                t
                for t in rows
                if t.status == "duplicate" and (t.duplicate_state or "pending") == "pending"
            ]
        if date_from:
            rows = [t for t in rows if t.date >= date_from]
        if date_to:
            rows = [t for t in rows if t.date <= date_to]
        rows.sort(key=lambda t: (t.date, t.id), reverse=True)
        if after:
            rows = [t for t in rows if (t.date, t.id) < after]
        return rows[:limit]

    async def tab_counts(self) -> dict[str, int]:
        return {
            "all": len(self.txs),
            "check": sum(1 for t in self.txs if t.status == "check"),
            "duplicates": sum(
                1
                for t in self.txs
                if t.status == "duplicate" and (t.duplicate_state or "pending") == "pending"
            ),
        }

    async def get_transactions(self, ids: Sequence[str]) -> list[TxRow]:
        wanted = set(ids)
        return [self._refresh(t) for t in self.txs if t.id in wanted]

    async def get_duplicate_partners(self, tx_id: str) -> list[TxRow]:
        rows = [self._refresh(t) for t in self.txs if t.duplicate_of == tx_id]
        return sorted(rows, key=lambda t: (t.date, t.id))

    async def summary_rows(self, first: date, last: date) -> list[SummaryRow]:
        return [
            SummaryRow(
                t.date, t.amount, t.kind, t.status, self._category_name(t.category_id), t.source
            )
            for t in self.txs
            if first <= t.date <= last and t.status != "duplicate" and t.kind != "transfer"
        ]

    async def insert_transactions(self, rows: Sequence[NewTx]) -> list[str]:
        ids: list[str] = []
        for r in rows:
            new_id = self.new_id()
            ids.append(new_id)
            if r.external_id and any(
                self.tx_extra[t.id].get("external_id") == r.external_id and t.source == r.source
                for t in self.txs
            ):
                continue
            account = self._account(r.account_id)
            self.txs.append(
                TxRow(
                    id=new_id,
                    date=r.date,
                    description=r.description,
                    amount=r.amount,
                    kind=r.kind,
                    source=r.source,
                    status=r.status,
                    account_id=r.account_id,
                    account_name=account.name,
                    category_id=r.category_id,
                    category_name=self._category_name(r.category_id),
                    category_source=r.category_source,
                    rule_id=r.rule_id,
                    counterparty_inn=r.counterparty_inn,
                    counterparty_name=r.counterparty_name,
                    duplicate_of=r.duplicate_of,
                    duplicate_state=r.duplicate_state,
                    duplicate_dismissed=False,
                    created_at=BASE_TIME + timedelta(seconds=self._seq),
                )
            )
            self.tx_extra[new_id] = {"external_id": r.external_id, "import_id": r.import_id}
        return ids

    async def update_transaction(self, tx_id: str, changes: Mapping[str, Any]) -> None:
        for i, t in enumerate(self.txs):
            if t.id == tx_id:
                self.txs[i] = dataclasses.replace(
                    t, **{k: v for k, v in changes.items() if k in EDITABLE}
                )

    async def existing_external_ids(self, source: str, ids: Collection[str]) -> set[str]:
        wanted = set(ids)
        return {
            ext
            for t in self.txs
            if t.source == source and (ext := self.tx_extra[t.id].get("external_id")) in wanted
        }

    async def duplicate_candidates(self, first: date, last: date) -> list[TxRef]:
        taken = {t.duplicate_of for t in self.txs if t.duplicate_of}
        rows = [
            t
            for t in self.txs
            if first <= t.date <= last
            and t.status != "duplicate"
            and t.kind != "transfer"
            and not t.duplicate_dismissed
            and t.id not in taken
        ]
        rows.sort(key=lambda t: (t.date, t.created_at, t.id))
        return [TxRef(t.id, t.account_id, t.date, t.amount, t.source, t.kind) for t in rows]

    async def uncategorised_checks(self) -> list[TxRow]:
        rows = [
            self._refresh(t)
            for t in self.txs
            if t.status == "check" and t.category_id is None and t.kind != "transfer"
        ]
        return sorted(rows, key=lambda t: (t.date, t.id))

    async def category_history(self, inns: Collection[str]) -> dict[str, dict[str, int]]:
        history: dict[str, dict[str, int]] = {}
        for t in self.txs:
            if t.counterparty_inn in inns and t.category_id and t.status != "duplicate":
                bucket = history.setdefault(t.counterparty_inn, {})
                bucket[t.category_id] = bucket.get(t.category_id, 0) + 1
        return history

    # ------------------------------------------------------------ imports
    async def add_raw_event(
        self, source: str, file_hash: str | None, byte_size: int | None, payload: Mapping[str, Any]
    ) -> str:
        event_id = self.new_id()
        self.raw_events.append(
            {
                "id": event_id,
                "source": source,
                "hash": file_hash,
                "size": byte_size,
                "payload": json.loads(json.dumps(dict(payload), default=str)),
                "created_at": self.now,
            }
        )
        return event_id

    async def count_recent_raw_events(self, source: str, seconds: int) -> int:
        since = self.now - timedelta(seconds=seconds)
        return sum(1 for e in self.raw_events if e["source"] == source and e["created_at"] > since)

    async def last_raw_event_at(self, source: str) -> datetime | None:
        times = [e["created_at"] for e in self.raw_events if e["source"] == source]
        return max(times) if times else None

    # ------------------------------------------------------------ acquiring
    async def list_card_payments(self) -> list[CardPaymentRow]:
        rows = [(p.external_id, p) for p, _ in self.payments.values() if p.method == "card"]
        rows.sort(key=lambda item: (item[1].date, item[0]))
        return [CardPaymentRow(p.date, p.amount, p.invoice_external_id) for _, p in rows]

    async def list_acquiring_credits(self, category_name: str) -> list[TxRow]:
        rows = [
            self._refresh(t)
            for t in self.txs
            if self._category_name(t.category_id) == category_name
            and t.kind == "in"
            and t.status != "duplicate"
        ]
        return sorted(rows, key=lambda t: (t.date, t.id))

    async def bank_covered_to(self) -> date | None:
        ends = [
            a.last_statement_to for a in self.accounts if a.kind == "bank" and a.last_statement_to
        ]
        return max(ends) if ends else None

    async def list_reviews(self) -> list[ReviewRow]:
        return [ReviewRow(day, note) for day, note in self.reviews.items()]

    async def save_review(self, sale_date: date, note: str | None) -> None:
        self.reviews[sale_date] = note

    # ------------------------------------------------------------ connections and synchronisation
    async def list_connections(self) -> list[ConnectionRow]:
        return list(self.connections)

    async def get_connection(self, connection_id: str) -> ConnectionRow | None:
        return next((c for c in self.connections if c.id == connection_id), None)

    async def update_connection(
        self, connection_id: str, address: str | None, key_hint: str | None
    ) -> None:
        for i, c in enumerate(self.connections):
            if c.id == connection_id:
                self.connections[i] = dataclasses.replace(c, address=address, key_hint=key_hint)

    async def save_connection_secret(self, connection_id: str, cipher: str) -> None:
        self.secrets[connection_id] = cipher

    async def get_connection_secret(self, connection_id: str) -> str | None:
        return self.secrets.get(connection_id)

    async def list_runs(self, connection_id: str, limit: int) -> list[SyncRunRow]:
        rows = [r for r in self.runs if r.connection_id == connection_id]
        rows.sort(key=lambda r: (r.started_at, r.id), reverse=True)
        return rows[:limit]

    async def create_run(self, connection_id: str) -> SyncRunRow:
        run = SyncRunRow(self.new_id(), connection_id, "running", self.now, None, None, None)
        self.runs.append(run)
        return run

    async def get_run(self, run_id: str) -> SyncRunRow | None:
        return next((r for r in self.runs if r.id == run_id), None)

    async def finish_run(
        self, run_id: str, status: str, error_code: str | None, counts: Mapping[str, int] | None
    ) -> None:
        for i, r in enumerate(self.runs):
            if r.id == run_id:
                self.runs[i] = dataclasses.replace(
                    r,
                    status=status,
                    error_code=error_code,
                    finished_at=self.now + timedelta(seconds=30),
                    counts=dict(counts) if counts is not None else None,
                )

    # ------------------------------------------------------------ Vetmanager data
    async def list_doctors(self) -> dict[str, tuple[str, str]]:
        return {ext: (d[0], d[1]) for ext, d in self.doctors.items()}

    async def upsert_doctor(self, external_id: str, code: str, name: str) -> str:
        known = self.doctors.get(external_id)
        doctor_id = known[0] if known else self.new_id()
        self.doctors[external_id] = (doctor_id, known[1] if known else code, name)
        return doctor_id

    async def upsert_visit(self, visit: Visit, doctor_id: str | None) -> str:
        value = (visit.date, doctor_id)
        known = self.visits.get(visit.external_id)
        self.visits[visit.external_id] = value
        return "new" if known is None else ("same" if known == value else "updated")

    async def upsert_sale(self, sale: Sale) -> str:
        known = self.sales.get(sale.external_id)
        self.sales[sale.external_id] = sale
        return "new" if known is None else ("same" if known == sale else "updated")

    async def list_doctor_inputs(self) -> list[DoctorInput]:
        return [
            DoctorInput(d[0], d[1], d[2], self.hours.get(d[0]))
            for d in sorted(self.doctors.values(), key=lambda d: (d[1], d[0]))
        ]

    async def set_doctor_hours(self, hours: dict[str, Decimal | None]) -> None:
        self.hours.update(hours)

    async def upsert_payment(self, payment: Payment, transaction_id: str | None) -> str:
        known = self.payments.get(payment.external_id)
        linked = (known[1] if known else None) or transaction_id
        self.payments[payment.external_id] = (payment, linked)
        if known is None:
            return "new"
        return "same" if known[0] == payment else "updated"

    # ------------------------------------------------------------ stage 4: obligations, planned payments, terms
    async def list_obligation_inputs(self) -> list[ObligationInput]:
        return sorted(self.obligations, key=lambda o: (o.name, o.id))

    async def create_obligation(self, ob: ObligationInput) -> ObligationInput:
        row = dataclasses.replace(ob, id=self.new_id())
        self.obligations.append(row)
        return row

    async def update_obligation(
        self, obligation_id: str, changes: dict[str, Any]
    ) -> ObligationInput | None:
        for i, o in enumerate(self.obligations):
            if o.id == obligation_id and o.closed_from is None:
                self.obligations[i] = dataclasses.replace(o, **changes)
                return self.obligations[i]
        return None

    async def close_obligation(self, obligation_id: str, month: date) -> bool:
        for i, o in enumerate(self.obligations):
            if o.id == obligation_id and o.closed_from is None:
                self.obligations[i] = dataclasses.replace(o, closed_from=month)
                return True
        return False

    async def insert_charges(self, rows: Sequence[ObligationChargeInput]) -> None:
        have = {(c.obligation_id, c.month, c.kind) for c in self.charges}
        for r in rows:
            if (r.obligation_id, r.month, r.kind) not in have:
                self.charges.append(r)

    async def list_planned_payments(self) -> list[PlannedPaymentInput]:
        return sorted(self.planned, key=lambda p: (p.date, p.name, p.id))

    async def add_planned_payment(
        self, day: date, name: str, amount: int, category_id: str | None, max_deferral_days: int
    ) -> PlannedPaymentInput:
        category = next((c.name for c in self.categories if c.id == category_id), None)
        row = PlannedPaymentInput(self.new_id(), day, name, amount, max_deferral_days, category)
        self.planned.append(row)
        return row

    async def delete_planned_payment(self, payment_id: str) -> bool:
        before = len(self.planned)
        self.planned = [p for p in self.planned if p.id != payment_id]
        return len(self.planned) < before

    async def list_counterparty_terms(self) -> list[CounterpartyTermsInput]:
        return sorted(self.terms.values(), key=lambda t: t.inn)

    async def set_counterparty_terms(self, key: str, name: str, days: int) -> None:
        self.terms[key] = CounterpartyTermsInput(key, name, days)
